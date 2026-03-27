"""Log erori pe disc pentru diagnosticare în producție."""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

_LOG = Path(__file__).resolve().parent.parent / "data" / "errors.log"


def log_exception(source: str, exc: BaseException) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().isoformat()
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    line = f"[{ts}] {source}\n{tb}\n"
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(line)
