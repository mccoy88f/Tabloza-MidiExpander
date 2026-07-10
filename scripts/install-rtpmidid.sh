#!/usr/bin/env bash
# Installa rtpmidid da GitHub (non presente nei repo Raspberry Pi OS)
set -euo pipefail

RTPMIDID_VER="26.01"
RELEASE_V26="https://github.com/davidmoreno/rtpmidid/releases/download/v${RTPMIDID_VER}"
RELEASE_V24="https://github.com/davidmoreno/rtpmidid/releases/download/v24.12"

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }
die()  { echo -e "\033[1;31m[Tabloza] ERRORE:\033[0m $*" >&2; exit 1; }

if command -v rtpmidid >/dev/null 2>&1; then
    log "rtpmidid già installato: $(command -v rtpmidid)"
    exit 0
fi

install_deb() {
    local url="$1"
    local deb="$2"
    local tmpdir
    tmpdir=$(mktemp -d)

    log "Download ${deb}..."
    if ! curl -fsSL "${url}" -o "${tmpdir}/${deb}"; then
        rm -rf "${tmpdir}"
        return 1
    fi

    apt-get install -y -qq libavahi-client3 libasound2 2>/dev/null || true
    if ! dpkg -i "${tmpdir}/${deb}"; then
        apt-get install -y -f -qq
    fi
    rm -rf "${tmpdir}"
    command -v rtpmidid >/dev/null 2>&1
}

ARCH="$(uname -m)"
INSTALLED=false

case "${ARCH}" in
    aarch64)
        DEB_V26="rtpmidid-debian-trixie-arm64-${RTPMIDID_VER}.deb"
        if install_deb "${RELEASE_V26}/${DEB_V26}" "${DEB_V26}"; then
            INSTALLED=true
        else
            warn "Pacchetto ${DEB_V26} non compatibile, provo fallback 24.12..."
            if install_deb "${RELEASE_V24}/rtpmidid_24.12.2_arm64.deb" "rtpmidid_24.12.2_arm64.deb"; then
                INSTALLED=true
            fi
        fi
        ;;
    armv7l|armhf)
        if install_deb "${RELEASE_V24}/rtpmidid_24.12.2_armhf.deb" "rtpmidid_24.12.2_armhf.deb"; then
            INSTALLED=true
        fi
        ;;
    *)
        die "Architettura non supportata per rtpmidid: ${ARCH}"
        ;;
esac

if [[ "${INSTALLED}" != "true" ]]; then
    die "Installazione rtpmidid fallita"
fi

RTP_BIN="$(command -v rtpmidid)"
log "rtpmidid installato: ${RTP_BIN}"
