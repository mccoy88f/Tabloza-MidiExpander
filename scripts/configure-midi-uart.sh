#!/usr/bin/env bash
# Configura GPIO UART per MIDI a 31250 bps
set -euo pipefail

CONFIG_TXT="/boot/firmware/config.txt"
[[ -f "$CONFIG_TXT" ]] || CONFIG_TXT="/boot/config.txt"
[[ -f "$CONFIG_TXT" ]] || { echo "config.txt non trovato" >&2; exit 1; }

backup="${CONFIG_TXT}.tabloza.bak"
[[ -f "$backup" ]] || cp "$CONFIG_TXT" "$backup"

# Disabilita console seriale su UART primario
for param in "enable_uart=1" "dtoverlay=disable-bt" "init_uart_clock=300000000"; do
    key="${param%%=*}"
    if grep -q "^${key}=" "$CONFIG_TXT"; then
        sed -i "s/^${key}=.*/${param}/" "$CONFIG_TXT"
    elif grep -q "^#${key}=" "$CONFIG_TXT"; then
        sed -i "s/^#${key}=.*/${param}/" "$CONFIG_TXT"
    else
        echo "$param" >> "$CONFIG_TXT"
    fi
done

# init_uart_clock=300000000 → baud = 300000000 / (16 * 600) = 31250
if ! grep -q "^init_uart_baud=31250" "$CONFIG_TXT"; then
    echo "init_uart_baud=31250" >> "$CONFIG_TXT"
fi

# Disabilita login seriale
systemctl disable serial-getty@ttyAMA0.service 2>/dev/null || true
systemctl stop serial-getty@ttyAMA0.service 2>/dev/null || true

# cmdline: rimuovi console=serial0
CMDLINE="/boot/firmware/cmdline.txt"
[[ -f "$CMDLINE" ]] || CMDLINE="/boot/cmdline.txt"
if [[ -f "$CMDLINE" ]]; then
    sed -i 's/console=serial0,[0-9]* //g' "$CMDLINE"
    sed -i 's/console=ttyAMA0,[0-9]* //g' "$CMDLINE"
fi

echo "UART MIDI configurato. Reboot richiesto per applicare."
