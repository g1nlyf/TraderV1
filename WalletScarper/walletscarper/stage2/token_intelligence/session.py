"""ActiveTokenSession lifecycle service.

Manages the lifecycle of active token monitoring sessions in Stage 2.
A session is opened when Hermes decides a token is `active_watch`, and closed
when Hermes downgrades it or the session expires.

Sessions drive adaptive cadence polling in the Stage2Daemon:
  - market_data_cadence_seconds: how often to capture a market snapshot
  - agent_review_cadence_seconds: how often to call Hermes for a review decision
"""

from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


DEFAULT_MARKET_CADENCE_SECONDS = 300       # 5 min — poll market snapshots
DEFAULT_AGENT_REVIEW_CADENCE_SECONDS = 3600  # 1 hour — call Hermes for review


class ActiveTokenSessionService:
    """Create, update, and close ActiveTokenSession rows.

    Sessions are lightweight — just a row in active_token_sessions linking
    a token_mint to an active monitoring window with adaptive cadence state.
    """

    def __init__(self, database: Stage2Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    async def open_session(
        self,
        *,
        token_mint: str,
        pool_address: str | None = None,
        trigger_ref: str | None = None,
        agent_owner: str = "stage2_daemon",
        market_data_cadence_seconds: int = DEFAULT_MARKET_CADENCE_SECONDS,
        agent_review_cadence_seconds: int = DEFAULT_AGENT_REVIEW_CADENCE_SECONDS,
        cadence_policy: dict[str, Any] | None = None,
    ) -> str:
        """Open (or re-open) an active monitoring session for token_mint.

        If an open session already exists for this token_mint, returns its ID
        without creating a duplicate.

        Returns active_token_session_id.
        """
        if not token_mint:
            raise ValueError("token_mint is required")

        existing = await self.database.fetchone(
            "SELECT active_token_session_id FROM active_token_sessions WHERE token_mint = ? AND status = 'watching'",
            (token_mint,),
        )
        if existing:
            return str(existing["active_token_session_id"])

        session_id = new_id("active_token_session")
        now = isoformat_utc(self.clock.now())
        policy = cadence_policy or {
            "market_data_cadence_seconds": market_data_cadence_seconds,
            "agent_review_cadence_seconds": agent_review_cadence_seconds,
            "adaptive": True,
        }
        await self.database.execute(
            """
            INSERT INTO active_token_sessions(
              active_token_session_id, token_mint, pool_address, started_at, ended_at,
              status, trigger_ref, agent_owner, market_data_cadence_seconds,
              agent_review_cadence_seconds, cadence_policy_json, cadence_degradation_reason,
              source_capacity_state_json, last_market_snapshot_id, last_agent_decision_id,
              quality_flags_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, 'watching', ?, ?, ?, ?, ?, NULL, '{}', NULL, NULL, '[]', ?, ?)
            """,
            (
                session_id,
                token_mint,
                pool_address,
                now,
                trigger_ref,
                agent_owner,
                market_data_cadence_seconds,
                agent_review_cadence_seconds,
                dumps_json(policy),
                now,
                now,
            ),
        )
        return session_id

    async def close_session(
        self,
        session_id: str,
        *,
        reason: str = "manual_close",
    ) -> None:
        """Close an active session."""
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            UPDATE active_token_sessions
            SET status = 'closed', ended_at = ?, updated_at = ?,
                cadence_degradation_reason = ?
            WHERE active_token_session_id = ? AND status = 'watching'
            """,
            (now, now, reason, session_id),
        )

    async def close_session_for_token(
        self,
        token_mint: str,
        *,
        reason: str = "token_downgraded",
    ) -> int:
        """Close all open sessions for a token_mint. Returns number closed."""
        open_sessions = await self.database.fetchall(
            "SELECT active_token_session_id FROM active_token_sessions WHERE token_mint = ? AND status = 'watching'",
            (token_mint,),
        )
        for row in open_sessions:
            await self.close_session(str(row["active_token_session_id"]), reason=reason)
        return len(open_sessions)

    async def list_open_sessions(self) -> list[dict[str, Any]]:
        """Return all open sessions ordered by started_at."""
        rows = await self.database.fetchall(
            """
            SELECT * FROM active_token_sessions
            WHERE status = 'watching'
            ORDER BY started_at ASC
            """,
        )
        return [dict(row) for row in rows]

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch a single session by ID."""
        row = await self.database.fetchone(
            "SELECT * FROM active_token_sessions WHERE active_token_session_id = ?",
            (session_id,),
        )
        return dict(row) if row else None

    async def record_market_snapshot(self, session_id: str, snapshot_id: str) -> None:
        """Update last_market_snapshot_id and updated_at."""
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            UPDATE active_token_sessions
            SET last_market_snapshot_id = ?, updated_at = ?
            WHERE active_token_session_id = ?
            """,
            (snapshot_id, now, session_id),
        )

    async def record_agent_decision(self, session_id: str, decision_id: str) -> None:
        """Update last_agent_decision_id and updated_at."""
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            UPDATE active_token_sessions
            SET last_agent_decision_id = ?, updated_at = ?
            WHERE active_token_session_id = ?
            """,
            (decision_id, now, session_id),
        )

    async def update_cadence(
        self,
        session_id: str,
        *,
        market_data_cadence_seconds: int | None = None,
        agent_review_cadence_seconds: int | None = None,
        degradation_reason: str | None = None,
    ) -> None:
        """Update cadence settings for an open session."""
        now = isoformat_utc(self.clock.now())
        parts: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
        if market_data_cadence_seconds is not None:
            parts.append("market_data_cadence_seconds = ?")
            params.append(market_data_cadence_seconds)
        if agent_review_cadence_seconds is not None:
            parts.append("agent_review_cadence_seconds = ?")
            params.append(agent_review_cadence_seconds)
        if degradation_reason is not None:
            parts.append("cadence_degradation_reason = ?")
            params.append(degradation_reason)
        params.append(session_id)
        await self.database.execute(
            f"UPDATE active_token_sessions SET {', '.join(parts)} WHERE active_token_session_id = ?",
            tuple(params),
        )

    async def session_summary(self) -> dict[str, Any]:
        """Return a summary of session state for logging/dashboard."""
        rows = await self.database.fetchall(
            """
            SELECT status, COUNT(*) AS count
            FROM active_token_sessions
            GROUP BY status
            ORDER BY status
            """
        )
        return {
            "sessions_by_status": {str(row["status"]): int(row["count"]) for row in rows},
        }
