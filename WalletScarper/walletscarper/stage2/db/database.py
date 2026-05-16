from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings, load_stage2_settings
from walletscarper.stage2.db.migrations import MIGRATIONS, Migration


class Stage2Database:
    def __init__(self, settings: Stage2Settings | None = None, clock: Clock | None = None):
        self.settings = settings or load_stage2_settings()
        self.clock = clock or SystemClock()
        self.path = Path(self.settings.database_path)

    async def connect(self) -> aiosqlite.Connection:
        self.settings.ensure_dirs()
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def migrate(self, migrations: list[Migration] | None = None) -> None:
        migration_set = migrations or MIGRATIONS
        conn = await self.connect()
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stage2_schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  applied_at TEXT NOT NULL
                )
                """
            )
            rows = await conn.execute_fetchall("SELECT version FROM stage2_schema_migrations")
            applied = {int(row["version"]) for row in rows}
            for migration in migration_set:
                if migration.version in applied:
                    continue
                await conn.executescript(migration.sql)
                await conn.execute(
                    "INSERT INTO stage2_schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, isoformat_utc(self.clock.now())),
                )
            await conn.commit()
        finally:
            await conn.close()

    async def applied_migrations(self) -> list[dict[str, Any]]:
        if self.path != Path(":memory:") and not self.path.exists():
            return []
        conn = await self.connect()
        try:
            table = await conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='stage2_schema_migrations'"
            )
            if not table:
                return []
            rows = await conn.execute_fetchall(
                "SELECT version, name, applied_at FROM stage2_schema_migrations ORDER BY version"
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        conn = await self.connect()
        try:
            await conn.execute(sql, tuple(params))
            await conn.commit()
        finally:
            await conn.close()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            cur = await conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def table_counts(self, table_names: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        conn = await self.connect()
        try:
            for table_name in table_names:
                rows = await conn.execute_fetchall(f"SELECT COUNT(*) AS count FROM {table_name}")
                counts[table_name] = int(rows[0]["count"])
            return counts
        finally:
            await conn.close()
