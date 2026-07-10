"""Tabloza — statistiche sistema (RAM, processi)."""

import shutil
import subprocess
from pathlib import Path

SF2_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


def _read_meminfo_kb() -> dict[str, int]:
    data: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    data[parts[0].rstrip(":")] = int(parts[1])
    except OSError:
        pass
    return data


def _pid_rss_mb(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024)
    except (OSError, ValueError, IndexError):
        return None
    return None


def _process_rss_mb(process_name: str, match_pattern: str | None = None) -> int | None:
    cmd = ["pgrep", "-x", process_name] if not match_pattern else ["pgrep", "-f", match_pattern]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    pid_str = result.stdout.strip().split()[0] if result.stdout.strip() else ""
    if not pid_str.isdigit():
        return None
    return _pid_rss_mb(int(pid_str))


def get_memory_stats(soundfonts_dir: Path | None = None) -> dict:
    """Return RAM usage summary for the web console."""
    mem = _read_meminfo_kb()
    total_kb = mem.get("MemTotal", 0)
    avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb) if total_kb else 0
    swap_total_kb = mem.get("SwapTotal", 0)
    swap_free_kb = mem.get("SwapFree", 0)

    disk_free_mb = None
    if soundfonts_dir is not None:
        try:
            usage = shutil.disk_usage(soundfonts_dir)
            disk_free_mb = round(usage.free / (1024 * 1024))
        except OSError:
            pass

    return {
        "total_mb": round(total_kb / 1024),
        "available_mb": round(avail_kb / 1024),
        "used_mb": round(used_kb / 1024),
        "used_percent": round(used_kb / total_kb * 100) if total_kb else 0,
        "swap_total_mb": round(swap_total_kb / 1024),
        "swap_free_mb": round(swap_free_kb / 1024),
        "fluidsynth_mb": _process_rss_mb("fluidsynth"),
        "orchestrator_mb": _process_rss_mb("python3", "midi_orchestrator.py"),
        "disk_free_mb": disk_free_mb,
        "sf2_max_upload_mb": round(SF2_MAX_UPLOAD_BYTES / (1024 * 1024)),
    }
