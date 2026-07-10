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

DEFAULT_FLUIDSYNTH_CONFIG: dict = {
    "audio_driver": "alsa",
    "audio_device": "plughw:0,0",
    "sample_rate": 44100,
    "period_size": 512,
    "period_count": 6,
    "gain": 2.0,
    "alsa_card": 0,
    "alsa_mixer_control": "PCM",
    "audio_preset": "standard",
    "polyphony": 256,
    "reverb": True,
    "chorus": True,
    "dynamic_sample_loading": False,
}


def merge_fluidsynth_config(stored: dict | None) -> dict:
    """Merge stored fluidsynth section with defaults."""
    merged = dict(DEFAULT_FLUIDSYNTH_CONFIG)
    if stored:
        merged.update(stored)
    preset = merged.get("audio_preset", "standard")
    if preset in AUDIO_PRESETS:
        merged["period_size"] = AUDIO_PRESETS[preset]["period_size"]
        merged["period_count"] = AUDIO_PRESETS[preset]["period_count"]
    merged["polyphony"] = max(32, min(512, int(merged.get("polyphony", 256))))
    merged["reverb"] = bool(merged.get("reverb", True))
    merged["chorus"] = bool(merged.get("chorus", True))
    merged["dynamic_sample_loading"] = bool(merged.get("dynamic_sample_loading", False))
    if merged.get("audio_preset") not in AUDIO_PRESETS:
        merged["audio_preset"] = "standard"
    return merged


def fluidsynth_startup_options(fs_cfg: dict) -> list[str]:
    """Extra FluidSynth -o flags (require process restart)."""
    cfg = merge_fluidsynth_config(fs_cfg)
    opts = [
        f"synth.polyphony={cfg['polyphony']}",
        f"synth.reverb.active={1 if cfg['reverb'] else 0}",
        f"synth.chorus.active={1 if cfg['chorus'] else 0}",
        f"synth.dynamic-sample-loading={1 if cfg['dynamic_sample_loading'] else 0}",
    ]
    return opts


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
        "presets": presets,
    }


def parse_synth_settings_update(data: dict, current: dict) -> tuple[dict, bool]:
    """Validate UI update; return merged fluidsynth config and whether restart is needed."""
    fs = merge_fluidsynth_config(current.get("fluidsynth"))
    old_restart_key = (
        fs["period_size"],
        fs["period_count"],
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

    new_restart_key = (
        fs["period_size"],
        fs["period_count"],
        fs["dynamic_sample_loading"],
    )
    needs_restart = new_restart_key != old_restart_key
    return fs, needs_restart
