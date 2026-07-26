"""Tabloza — configurazione pannello GPIO opzionale (LED stato + pulsanti).

Disattivato di default: per attivarlo aggiungere in config.json:

    "gpio": {"enabled": true}

Pin BCM di default (liberi: nessun altro uso GPIO nel progetto oltre al
futuro ingresso MIDI DIN su GPIO 14/15, vedi docs/TODO.md):

    led_ready_pin (17)        — rosso, acceso finché il motore non è pronto
    led_sf2_pin (27)          — verde, acceso a SF2 caricato, lampeggia su MIDI in
    btn_allnotesoff_pin (22)  — pulsante: All Notes Off (reset synth)
    btn_restart_pin (23)     — pulsante: riavvio motore FluidSynth
"""

DEFAULT_GPIO_CONFIG = {
    "enabled": False,
    "led_ready_pin": 17,
    "led_sf2_pin": 27,
    "btn_allnotesoff_pin": 22,
    "btn_restart_pin": 23,
    "active_low": False,
}


def merge_gpio_config(stored: dict | None) -> dict:
    cfg = dict(DEFAULT_GPIO_CONFIG)
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if k in DEFAULT_GPIO_CONFIG})
    return cfg


def load_gpio_config() -> dict:
    from tabloza_common import load_config

    return merge_gpio_config(load_config().get("gpio"))
