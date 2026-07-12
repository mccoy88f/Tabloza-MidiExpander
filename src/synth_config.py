"""Tabloza — preset e parametri FluidSynth."""

AUDIO_PRESETS: dict[str, dict] = {
    "standard": {
        "label": "Standard",
        "period_size": 512,
        "period_count": 6,
    },
    "low_latency": {
        "label": "Bassa latenza",
        "period_size": 256,
        "period_count": 4,
    },
    "stable": {
        "label": "Stabile",
        "period_size": 1024,
        "period_count": 8,
    },
}

DEFAULT_AUDIO_PRESET = "stable"

MIN_SYNTH_GAIN = 0.0
MAX_SYNTH_GAIN = 4.0
DEFAULT_SYNTH_GAIN = 2.0

DEFAULT_REVERB_EFFECT: dict[str, float] = {
    "room_size": 0.75,
    "damp": 0.15,
    "width": 0.8,
    "level": 0.825,
}

DEFAULT_CHORUS_EFFECT: dict[str, float | int] = {
    "nr": 3,
    "level": 0.6,
    "speed": 0.2,
    "depth": 4.25,
}

EFFECT_FLOAT_KEYS = {
    "reverb": ("room_size", "damp", "width", "level"),
    "chorus": ("level", "speed", "depth"),
}

EFFECT_RANGES: dict[str, tuple[float, float]] = {
    "room_size": (0.0, 1.0),
    "damp": (0.0, 1.0),
    "width": (0.0, 100.0),
    "reverb_level": (0.0, 1.0),
    "chorus_level": (0.0, 10.0),
    "speed": (0.1, 5.0),
    "depth": (0.0, 256.0),
}

STABLE_SYNTH_DEFAULTS: dict = {
    "audio_preset": DEFAULT_AUDIO_PRESET,
    "polyphony": 256,
    "reverb": True,
    "chorus": True,
    "dynamic_sample_loading": False,
    "reverb_effect": dict(DEFAULT_REVERB_EFFECT),
    "chorus_effect": dict(DEFAULT_CHORUS_EFFECT),
}

DEFAULT_FLUIDSYNTH_CONFIG: dict = {
    "audio_driver": "alsa",
    "audio_device": "plughw:0,0",
    "sample_rate": 44100,
    "period_size": 1024,
    "period_count": 8,
    "gain": 2.0,
    "alsa_card": 0,
    "alsa_mixer_control": "PCM",
    "audio_preset": DEFAULT_AUDIO_PRESET,
    "polyphony": 256,
    "reverb": True,
    "chorus": True,
    "dynamic_sample_loading": False,
    "reverb_effect": dict(DEFAULT_REVERB_EFFECT),
    "chorus_effect": dict(DEFAULT_CHORUS_EFFECT),
}


def normalize_synth_gain(value) -> float:
    try:
        gain = float(value)
    except (TypeError, ValueError):
        gain = DEFAULT_SYNTH_GAIN
    return round(max(MIN_SYNTH_GAIN, min(MAX_SYNTH_GAIN, gain)), 2)


def _clamp_effect_value(key: str, value, *, effect_kind: str = "reverb") -> float | int:
    if key == "nr":
        try:
            return max(0, min(99, int(value)))
        except (TypeError, ValueError):
            return int(DEFAULT_CHORUS_EFFECT["nr"])
    try:
        num = float(value)
    except (TypeError, ValueError):
        defaults = {**DEFAULT_REVERB_EFFECT, **DEFAULT_CHORUS_EFFECT}
        num = float(defaults.get(key, 0))
    range_key = key
    if key == "level":
        range_key = "chorus_level" if effect_kind == "chorus" else "reverb_level"
    low, high = EFFECT_RANGES.get(range_key, (0.0, 1.0))
    return round(max(low, min(high, num)), 3)


def merge_reverb_effect(stored: dict | None) -> dict[str, float]:
    merged = dict(DEFAULT_REVERB_EFFECT)
    if stored:
        for key in EFFECT_FLOAT_KEYS["reverb"]:
            if key in stored:
                merged[key] = float(_clamp_effect_value(key, stored[key], effect_kind="reverb"))
    return merged


def merge_chorus_effect(stored: dict | None) -> dict[str, float | int]:
    merged = dict(DEFAULT_CHORUS_EFFECT)
    if stored:
        if "nr" in stored:
            merged["nr"] = _clamp_effect_value("nr", stored["nr"], effect_kind="chorus")
        for key in ("level", "speed", "depth"):
            if key in stored:
                merged[key] = float(_clamp_effect_value(key, stored[key], effect_kind="chorus"))
    return merged


def merge_fluidsynth_config(stored: dict | None) -> dict:
    """Merge stored fluidsynth section with defaults."""
    merged = dict(DEFAULT_FLUIDSYNTH_CONFIG)
    if stored:
        merged.update(stored)
    preset = merged.get("audio_preset", DEFAULT_AUDIO_PRESET)
    if preset in AUDIO_PRESETS:
        merged["period_size"] = AUDIO_PRESETS[preset]["period_size"]
        merged["period_count"] = AUDIO_PRESETS[preset]["period_count"]
    merged["polyphony"] = max(32, min(512, int(merged.get("polyphony", 256))))
    merged["reverb"] = bool(merged.get("reverb", True))
    merged["chorus"] = bool(merged.get("chorus", True))
    merged["dynamic_sample_loading"] = bool(merged.get("dynamic_sample_loading", False))
    merged["gain"] = normalize_synth_gain(merged.get("gain"))
    merged["reverb_effect"] = merge_reverb_effect(merged.get("reverb_effect"))
    merged["chorus_effect"] = merge_chorus_effect(merged.get("chorus_effect"))
    if merged.get("audio_preset") not in AUDIO_PRESETS:
        merged["audio_preset"] = DEFAULT_AUDIO_PRESET
    return merged


def fluidsynth_effect_startup_options(fs_cfg: dict) -> list[str]:
    cfg = merge_fluidsynth_config(fs_cfg)
    reverb = cfg["reverb_effect"]
    chorus = cfg["chorus_effect"]
    return [
        f"synth.reverb.room-size={reverb['room_size']}",
        f"synth.reverb.damp={reverb['damp']}",
        f"synth.reverb.width={reverb['width']}",
        f"synth.reverb.level={reverb['level']}",
        f"synth.chorus.nr={chorus['nr']}",
        f"synth.chorus.level={chorus['level']}",
        f"synth.chorus.speed={chorus['speed']}",
        f"synth.chorus.depth={chorus['depth']}",
    ]


def fluidsynth_startup_options(fs_cfg: dict) -> list[str]:
    """Extra FluidSynth -o flags (require process restart)."""
    cfg = merge_fluidsynth_config(fs_cfg)
    opts = [
        f"synth.polyphony={cfg['polyphony']}",
        f"synth.reverb.active={1 if cfg['reverb'] else 0}",
        f"synth.chorus.active={1 if cfg['chorus'] else 0}",
        f"synth.dynamic-sample-loading={1 if cfg['dynamic_sample_loading'] else 0}",
    ]
    opts.extend(fluidsynth_effect_startup_options(cfg))
    return opts


def fluidsynth_effect_set_commands(fs_cfg: dict) -> list[str]:
    """Runtime `set` commands for reverb/chorus effect parameters."""
    cfg = merge_fluidsynth_config(fs_cfg)
    reverb = cfg["reverb_effect"]
    chorus = cfg["chorus_effect"]
    return [
        f"set synth.reverb.active {1 if cfg['reverb'] else 0}",
        f"set synth.reverb.room-size {reverb['room_size']}",
        f"set synth.reverb.damp {reverb['damp']}",
        f"set synth.reverb.width {reverb['width']}",
        f"set synth.reverb.level {reverb['level']}",
        f"set synth.chorus.active {1 if cfg['chorus'] else 0}",
        f"set synth.chorus.nr {chorus['nr']}",
        f"set synth.chorus.level {chorus['level']}",
        f"set synth.chorus.speed {chorus['speed']}",
        f"set synth.chorus.depth {chorus['depth']}",
    ]


def synth_settings_for_api(config: dict) -> dict:
    """Public synth settings block for REST/UI."""
    fs = merge_fluidsynth_config(config.get("fluidsynth"))
    presets = []
    for key, preset in AUDIO_PRESETS.items():
        presets.append({
            "id": key,
            "period_size": preset["period_size"],
            "period_count": preset["period_count"],
        })
    return {
        "audio_preset": fs["audio_preset"],
        "period_size": fs["period_size"],
        "period_count": fs["period_count"],
        "polyphony": fs["polyphony"],
        "reverb": fs["reverb"],
        "chorus": fs["chorus"],
        "dynamic_sample_loading": fs["dynamic_sample_loading"],
        "gain": fs["gain"],
        "reverb_effect": fs["reverb_effect"],
        "chorus_effect": fs["chorus_effect"],
        "stable_defaults": dict(STABLE_SYNTH_DEFAULTS),
        "presets": presets,
    }


def _merge_effect_update(current: dict, patch: dict | None, kind: str) -> dict:
    if not patch:
        return current
    merged = dict(current)
    if kind == "reverb":
        keys = EFFECT_FLOAT_KEYS["reverb"]
    else:
        keys = ("nr", *EFFECT_FLOAT_KEYS["chorus"])
    for key in keys:
        if key in patch:
            if key == "nr":
                merged[key] = _clamp_effect_value(key, patch[key], effect_kind=kind)
            else:
                merged[key] = float(_clamp_effect_value(key, patch[key], effect_kind=kind))
    return merged


def parse_synth_settings_update(data: dict, current: dict) -> tuple[dict, bool]:
    """Validate UI update; return merged fluidsynth config and whether restart is needed."""
    fs = merge_fluidsynth_config(current.get("fluidsynth"))
    old_restart_key = (
        fs["period_size"],
        fs["period_count"],
        fs["polyphony"],
        fs["dynamic_sample_loading"],
    )

    if "audio_preset" in data:
        preset = str(data["audio_preset"]).strip()
        if preset not in AUDIO_PRESETS:
            raise ValueError("Preset audio non valido")
        fs["audio_preset"] = preset
        fs["period_size"] = AUDIO_PRESETS[preset]["period_size"]
        fs["period_count"] = AUDIO_PRESETS[preset]["period_count"]

    if "polyphony" in data:
        fs["polyphony"] = max(32, min(512, int(data["polyphony"])))

    if "reverb" in data:
        fs["reverb"] = bool(data["reverb"])
    if "chorus" in data:
        fs["chorus"] = bool(data["chorus"])
    if "dynamic_sample_loading" in data:
        fs["dynamic_sample_loading"] = bool(data["dynamic_sample_loading"])
    if "gain" in data:
        fs["gain"] = normalize_synth_gain(data["gain"])

    if "reverb_effect" in data:
        if not isinstance(data["reverb_effect"], dict):
            raise ValueError("reverb_effect deve essere un oggetto")
        fs["reverb_effect"] = _merge_effect_update(fs["reverb_effect"], data["reverb_effect"], "reverb")
    if "chorus_effect" in data:
        if not isinstance(data["chorus_effect"], dict):
            raise ValueError("chorus_effect deve essere un oggetto")
        fs["chorus_effect"] = _merge_effect_update(fs["chorus_effect"], data["chorus_effect"], "chorus")

    new_restart_key = (
        fs["period_size"],
        fs["period_count"],
        fs["polyphony"],
        fs["dynamic_sample_loading"],
    )
    needs_restart = new_restart_key != old_restart_key
    return fs, needs_restart
