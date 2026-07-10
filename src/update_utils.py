"""Tabloza — verifica e applicazione aggiornamenti da GitHub."""

import json
import os
import subprocess
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("TABLOZA_INSTALL_DIR", "/opt/tabloza"))
UPDATE_STATUS_FILE = Path(os.environ.get("TABLOZA_UPDATE_STATUS", "/run/tabloza/update_status.json"))
UPDATE_SCRIPT = Path("/usr/local/bin/tabloza-update")
FETCH_TIMEOUT = 30
APPLY_TIMEOUT = 600


def _run_git(args: list[str], cwd: Path = INSTALL_DIR, timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _read_version_at(ref: str = "HEAD") -> str:
    result = _run_git(["show", f"{ref}:VERSION"])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    version_file = INSTALL_DIR / "VERSION"
    if ref in ("HEAD", "") and version_file.is_file():
        return version_file.read_text().strip()
    return "?"


def _write_status(data: dict) -> None:
    UPDATE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_STATUS_FILE.write_text(json.dumps(data, indent=2))


def read_update_status() -> dict:
    if not UPDATE_STATUS_FILE.is_file():
        return {"state": "idle"}
    try:
        return json.loads(UPDATE_STATUS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"state": "idle"}


def check_for_update(fetch: bool = True) -> dict:
    """Compare local main with origin/main on GitHub."""
    if not (INSTALL_DIR / ".git").is_dir():
        return {
            "ok": False,
            "error": "Installazione git non trovata in /opt/tabloza",
            "update_available": False,
        }

    if fetch:
        fetch_result = _run_git(["fetch", "origin", "main"], timeout=FETCH_TIMEOUT)
        if fetch_result.returncode != 0:
            err = (fetch_result.stderr or fetch_result.stdout or "git fetch fallito").strip()
            return {"ok": False, "error": err, "update_available": False}

    local = _run_git(["rev-parse", "HEAD"])
    remote = _run_git(["rev-parse", "origin/main"])
    if local.returncode != 0 or remote.returncode != 0:
        return {
            "ok": False,
            "error": "Impossibile leggere commit locali/remoti",
            "update_available": False,
        }

    local_sha = local.stdout.strip()
    remote_sha = remote.stdout.strip()
    update_available = local_sha != remote_sha

    return {
        "ok": True,
        "update_available": update_available,
        "current_version": _read_version_at("HEAD"),
        "remote_version": _read_version_at("origin/main"),
        "current_commit": local_sha[:8],
        "remote_commit": remote_sha[:8],
    }


def apply_update_if_needed() -> dict:
    """Fetch GitHub; run tabloza-update only when origin/main is ahead."""
    status = read_update_status()
    if status.get("state") == "updating":
        return {"ok": False, "error": "Aggiornamento già in corso", "busy": True}

    check = check_for_update(fetch=True)
    if not check.get("ok"):
        return check

    if not check.get("update_available"):
        result = {
            "ok": True,
            "applied": False,
            "up_to_date": True,
            **check,
        }
        _write_status({"state": "up_to_date", **result})
        return result

    if not UPDATE_SCRIPT.is_file():
        return {"ok": False, "error": "tabloza-update non installato"}

    _write_status({
        "state": "updating",
        "current_version": check["current_version"],
        "remote_version": check["remote_version"],
    })

    try:
        proc = subprocess.run(
            [str(UPDATE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=APPLY_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _write_status({"state": "error", "error": "Timeout aggiornamento"})
        return {"ok": False, "error": "Timeout aggiornamento (>10 min)"}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        _write_status({"state": "error", "error": err[:500]})
        return {"ok": False, "error": err[:500], "applied": False}

    after = check_for_update(fetch=False)
    result = {
        "ok": True,
        "applied": True,
        "up_to_date": True,
        **after,
        "previous_version": check["current_version"],
    }
    _write_status({"state": "updated", **result})
    return result
