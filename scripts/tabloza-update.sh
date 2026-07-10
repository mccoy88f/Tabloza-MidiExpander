#!/usr/bin/env bash
# Tabloza MidiExpander — Aggiornamento rapido
# Uso: sudo tabloza-update
set -euo pipefail

INSTALL_DIR="/opt/tabloza"
REPO_URL="https://github.com/mccoy88f/Tabloza-MidiExpander.git"

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }

[[ $EUID -eq 0 ]] || { echo "Esegui come root: sudo tabloza-update"; exit 1; }
cd / || cd /root || true

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log "Aggiornamento ${INSTALL_DIR}..."
    git -C "${INSTALL_DIR}" checkout -f main 2>/dev/null || true
    if ! git -C "${INSTALL_DIR}" fetch origin main; then
        warn "Fetch fallito — reinstallazione pulita..."
        rm -rf "${INSTALL_DIR}"
    fi
fi

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "${INSTALL_DIR}" reset --hard origin/main
    git -C "${INSTALL_DIR}" clean -fd
else
    log "Clone repository..."
    git clone --depth 1 -b main "${REPO_URL}" "${INSTALL_DIR}"
fi

exec bash "${INSTALL_DIR}/install.sh"
