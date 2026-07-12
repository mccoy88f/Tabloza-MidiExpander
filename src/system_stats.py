"""Tabloza — statistiche sistema (RAM, CPU, disco, temperatura)."""

import os
import re
import shutil
import subprocess
from pathlib import Path

SF2_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

_last_cpu_sample: dict[str, int] | None = None


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


def _read_cpu_jiffies() -> tuple[int, int] | None:
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            line = f.readline()
        parts = line.split()
        if not parts or parts[0] != "cpu":
            return None
        values = [int(x) for x in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)
    except (OSError, ValueError, IndexError):
        return None


def _cpu_stats() -> dict:
    global _last_cpu_sample
    current = _read_cpu_jiffies()
    percent: float | None = None
    if current is not None:
        idle, total = current
        if _last_cpu_sample:
            idle_delta = idle - _last_cpu_sample["idle"]
            total_delta = total - _last_cpu_sample["total"]
            if total_delta > 0:
                percent = round((1 - idle_delta / total_delta) * 100, 1)
        _last_cpu_sample = {"idle": idle, "total": total}

    load_1m: float | None = None
    try:
        load_1m = round(os.getloadavg()[0], 2)
    except OSError:
        pass

    return {
        "percent": percent,
        "load_1m": load_1m,
        "cores": os.cpu_count() or 1,
    }


def _disk_stats(path: Path) -> dict:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {
            "disk_total_mb": None,
            "disk_used_mb": None,
            "disk_free_mb": None,
            "disk_used_percent": None,
        }
    total_mb = round(usage.total / (1024 * 1024))
    used_mb = round(usage.used / (1024 * 1024))
    free_mb = round(usage.free / (1024 * 1024))
    used_percent = round(usage.used / usage.total * 100) if usage.total else 0
    return {
        "disk_total_mb": total_mb,
        "disk_used_mb": used_mb,
        "disk_free_mb": free_mb,
        "disk_used_percent": used_percent,
    }


def _read_temperature_c() -> float | None:
    thermal_root = Path("/sys/class/thermal")
    if thermal_root.is_dir():
        for zone in sorted(thermal_root.glob("thermal_zone*")):
            temp_file = zone / "temp"
            try:
                raw = int(temp_file.read_text(encoding="utf-8").strip())
                if raw > 0:
                    return round(raw / 1000.0, 1)
            except (OSError, ValueError):
                continue

    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        match = re.search(r"([\d.]+)", result.stdout)
        if match:
            return round(float(match.group(1)), 1)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def fluidsynth_rss_mb() -> int | None:
    """Resident memory (RSS) of the FluidSynth process, in MB."""
    return _process_rss_mb("fluidsynth")


def get_memory_stats(soundfonts_dir: Path | None = None) -> dict:
    """Return RAM usage summary."""
    mem = _read_meminfo_kb()
    total_kb = mem.get("MemTotal", 0)
    avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb) if total_kb else 0
    swap_total_kb = mem.get("SwapTotal", 0)
    swap_free_kb = mem.get("SwapFree", 0)

    disk_path = soundfonts_dir or Path("/var/lib/tabloza")
    disk = _disk_stats(disk_path)

    return {
        "total_mb": round(total_kb / 1024),
        "available_mb": round(avail_kb / 1024),
        "used_mb": round(used_kb / 1024),
        "used_percent": round(used_kb / total_kb * 100) if total_kb else 0,
        "swap_total_mb": round(swap_total_kb / 1024),
        "swap_free_mb": round(swap_free_kb / 1024),
        "fluidsynth_mb": fluidsynth_rss_mb(),
        "orchestrator_mb": _process_rss_mb("python3", "midi_orchestrator.py"),
        "disk_free_mb": disk["disk_free_mb"],
        "sf2_max_upload_mb": round(SF2_MAX_UPLOAD_BYTES / (1024 * 1024)),
    }


def get_device_stats(soundfonts_dir: Path | None = None) -> dict:
    """Return RAM, CPU, disk and temperature for the device panel."""
    disk_path = soundfonts_dir or Path("/var/lib/tabloza")
    memory = get_memory_stats(soundfonts_dir)
    disk = _disk_stats(disk_path)
    cpu = _cpu_stats()
    return {
        **memory,
        **disk,
        **cpu,
        "temperature_c": _read_temperature_c(),
    }
