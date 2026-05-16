from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from rich.logging import RichHandler


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line. Suitable for log aggregators (Loki, Datadog, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra_skip = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                      "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                      "created", "msecs", "relativeCreated", "thread", "threadName",
                      "processName", "process", "message", "taskName"}
        for k, v in record.__dict__.items():
            if k not in extra_skip:
                try:
                    json.dumps(v)
                    payload[k] = v
                except (TypeError, ValueError):
                    payload[k] = str(v)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if json_logs:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            handlers=[handler],
            force=True,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True, markup=True)],
            force=True,
        )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
