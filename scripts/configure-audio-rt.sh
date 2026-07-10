#!/usr/bin/env bash
# Priorità real-time per audio (FluidSynth / ALSA)
set -euo pipefail

LIMITS_FILE="/etc/security/limits.d/99-tabloza-audio.conf"
if [[ ! -f "$LIMITS_FILE" ]]; then
    cat > "$LIMITS_FILE" <<'EOF'
@audio   -  rtprio     95
@audio   -  memlock    unlimited
root     -  rtprio     95
root     -  memlock    unlimited
EOF
fi

# Aggiungi utente root al gruppo audio se necessario
usermod -aG audio root 2>/dev/null || true

# ALSA: period size ridotto per bassa latenza
ASOUNDRC="/etc/asound.conf"
if [[ ! -f "$ASOUNDRC" ]] || ! grep -q "tabloza" "$ASOUNDRC" 2>/dev/null; then
    cat > "$ASOUNDRC" <<'EOF'
# Tabloza MidiExpander — ALSA defaults
defaults.pcm.rate_converter "samplerate_best"
EOF
fi

echo "Priorità audio real-time configurata."
