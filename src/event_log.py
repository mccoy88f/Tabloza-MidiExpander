"""Ring-buffer event log for the web console."""

import os
import threading
import time
from pathlib import Path

MAX_LINES = 400
LOG_FILE = Path(os.environ.get("TABLOZA_CONSOLE_LOG", "/run/tabloza/console.log"))
_lock = threading.Lock()


def log_event(source: str, message: str, level: str = "info") -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"{ts} [{level}] {source}: {message}\n"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            existing = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.is_file() else ""
            lines = existing.splitlines()
            lines.append(line.rstrip("\n"))
            if len(lines) > MAX_LINES:
                lines = lines[-MAX_LINES:]
            LOG_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError:
        pass


def read_events(limit: int = 150) -> list[str]:
    try:
        if not LOG_FILE.is_file():
            return []
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        return lines[-limit:]
    except OSError:
        return []


def clear_events() -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("", encoding="utf-8")
    except OSError:
        pass
