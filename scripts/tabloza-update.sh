#!/usr/bin/env bash
# Tabloza MidiExpander — Aggiornamento rapido
# Uso: sudo tabloza-update
#      sudo tabloza-update --check-only   (exit 0=aggiornato, 2=disponibile, 1=errore)
set -euo pipefail

INSTALL_DIR="/opt/tabloza"
REPO_URL="https://github.com/mccoy88f/Tabloza-MidiExpander.git"
CHECK_ONLY=0

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only) CHECK_ONLY=1; shift ;;
        *) warn "Opzione sconosciuta: $1"; shift ;;
    esac
done

[[ $EUID -eq 0 ]] || { echo "Esegui come root: sudo tabloza-update"; exit 1; }
cd / || cd /root || true

_fetch_repo() {
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
}

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
    if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
        echo "no-git"
        exit 1
    fi
    git -C "${INSTALL_DIR}" checkout -f main 2>/dev/null || true
    if ! git -C "${INSTALL_DIR}" fetch origin main; then
        echo "fetch-failed"
        exit 1
    fi
    LOCAL="$(git -C "${INSTALL_DIR}" rev-parse HEAD)"
    REMOTE="$(git -C "${INSTALL_DIR}" rev-parse origin/main)"
    CUR_VER="$(cat "${INSTALL_DIR}/VERSION" 2>/dev/null || echo "?")"
    REM_VER="$(git -C "${INSTALL_DIR}" show origin/main:VERSION 2>/dev/null | tr -d '\n' || echo "?")"
    if [[ "${LOCAL}" == "${REMOTE}" ]]; then
        echo "up-to-date ${CUR_VER}"
        exit 0
    fi
    echo "update-available ${CUR_VER} -> ${REM_VER}"
    exit 2
fi

_fetch_repo
exec bash "${INSTALL_DIR}/install.sh"
