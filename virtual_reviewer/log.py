"""Structured JSON logging to stderr.

Each module uses this to emit JSONL logs. Data goes to stdout, logs to stderr.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def log(
    severity: str,
    module: str,
    event: str,
    message: str,
    *,
    application_id: str = "",
    **extra: object,
) -> None:
    """Emit a single JSON log line to stderr."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "module": module,
        "event": event,
        "message": message,
    }
    if application_id:
        entry["application_id"] = application_id
    entry.update(extra)
    print(json.dumps(entry, ensure_ascii=False), file=sys.stderr)


def info(module: str, event: str, message: str, **extra: object) -> None:
    log("INFO", module, event, message, **extra)


def warn(module: str, event: str, message: str, **extra: object) -> None:
    log("WARN", module, event, message, **extra)


def error(module: str, event: str, message: str, **extra: object) -> None:
    log("ERROR", module, event, message, **extra)
