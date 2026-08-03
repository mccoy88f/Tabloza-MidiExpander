"""Tabloza — verifica e applicazione aggiornamenti da GitHub."""

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("TABLOZA_INSTALL_DIR", "/opt/tabloza"))
UPDATE_STATUS_FILE = Path(os.environ.get("TABLOZA_UPDATE_STATUS", "/run/tabloza/update_status.json"))
UPDATE_SCRIPT = Path("/usr/local/bin/tabloza-update")
FETCH_TIMEOUT = 30
APPLY_TIMEOUT = 600

# Servizi da riavviare dopo un aggiornamento manuale da ZIP (stesso elenco di
# `sudo systemctl restart …` documentato in README → Comandi utili).
MANUAL_UPDATE_SERVICES = (
    "tabloza-web",
    "tabloza-orchestrator",
    "tabloza-wifi",
    "tabloza-lan",
    "rtpmidid",
)

_NETWORK_ERROR_MARKERS = (
    "could not resolve host",
    "unable to access",
    "network is unreachable",
    "temporary failure in name resolution",
    "connection timed out",
    "connection refused",
    "no route to host",
    "ssl connect error",
    "could not connect",
)


def _is_network_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _NETWORK_ERROR_MARKERS)


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
            return {
                "ok": False,
                "error": err,
                "update_available": False,
                "network_error": _is_network_error(err),
            }

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


def _current_installed_version() -> str:
    if (INSTALL_DIR / ".git").is_dir():
        return _read_version_at("HEAD")
    version_file = INSTALL_DIR / "VERSION"
    return version_file.read_text().strip() if version_file.is_file() else "?"


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Estrae lo ZIP in dest, rifiutando percorsi che uscirebbero da dest (zip-slip)."""
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            member_path = (dest / member.filename).resolve()
            if member_path != dest_resolved and dest_resolved not in member_path.parents:
                raise ValueError(f"Percorso non sicuro nello ZIP: {member.filename}")
        zf.extractall(dest)


def _find_extracted_root(extract_dir: Path) -> Path:
    """Trova la cartella del progetto dentro lo ZIP estratto (GitHub la annida in un sottodirectory)."""
    if (extract_dir / "install.sh").is_file():
        return extract_dir
    for entry in sorted(extract_dir.iterdir()):
        if entry.is_dir() and (entry / "install.sh").is_file():
            return entry
    raise ValueError(
        "install.sh non trovato nello ZIP: non sembra un archivio valido di Tabloza MidiExpander"
    )


def apply_manual_zip_update(zip_path: Path) -> dict:
    """Aggiorna il codice sorgente da uno ZIP caricato manualmente (fallback senza rete).

    Sostituisce i file applicativi in INSTALL_DIR e riavvia i servizi Tabloza.
    Non reinstalla dipendenze di sistema (apt/pip): per quelle serve comunque
    un aggiornamento online in futuro.
    """
    status = read_update_status()
    if status.get("state") == "updating":
        return {"ok": False, "error": "Aggiornamento già in corso", "busy": True}

    if not zipfile.is_zipfile(zip_path):
        return {"ok": False, "error": "Il file caricato non è uno ZIP valido"}

    previous_version = _current_installed_version()
    _write_status({"state": "updating", "source": "zip"})

    with tempfile.TemporaryDirectory(prefix="tabloza-zip-update-") as tmp:
        tmp_path = Path(tmp)
        try:
            _safe_extract_zip(zip_path, tmp_path)
            source_root = _find_extracted_root(tmp_path)
        except (ValueError, zipfile.BadZipFile, OSError) as exc:
            _write_status({"state": "error", "error": str(exc)})
            return {"ok": False, "error": str(exc)}

        version_file = source_root / "VERSION"
        new_version = version_file.read_text().strip() if version_file.is_file() else "?"

        try:
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            # Mirror completo (come `git reset --hard` + `git clean -fd`): rimuove
            # anche i file non più presenti nello ZIP. Preserva .git se esiste già,
            # così un futuro aggiornamento online torna a funzionare normalmente.
            new_names = {item.name for item in source_root.iterdir()}
            new_names.add(".git")
            for existing in INSTALL_DIR.iterdir():
                if existing.name in new_names:
                    continue
                if existing.is_dir() and not existing.is_symlink():
                    shutil.rmtree(existing)
                else:
                    existing.unlink()

            for item in source_root.iterdir():
                if item.name == ".git":
                    continue
                target = INSTALL_DIR / item.name
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
        except OSError as exc:
            _write_status({"state": "error", "error": f"Copia file fallita: {exc}"})
            return {"ok": False, "error": f"Copia file fallita: {exc}"}

    try:
        subprocess.Popen(
            ["systemctl", "restart", *MANUAL_UPDATE_SERVICES],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _write_status({"state": "error", "error": f"Riavvio servizi fallito: {exc}"})
        return {"ok": False, "error": f"Riavvio servizi fallito: {exc}"}

    result = {
        "ok": True,
        "applied": True,
        "manual": True,
        "previous_version": previous_version,
        "current_version": new_version,
    }
    _write_status({"state": "updated", **result})
    return result
