#!/usr/bin/env bash
# Installa rtpmidid-ts (fork Tabloza con timestamp RTP) — non presente nei repo Pi OS.
set -euo pipefail

RTPMIDID_REPO="https://github.com/mccoy88f/rtpmidid-ts.git"
RTPMIDID_VER="26.01-ts.5"
RELEASE_BASE="https://github.com/mccoy88f/rtpmidid-ts/releases/download/v${RTPMIDID_VER}"
MARKER="/var/lib/tabloza/rtpmidid-ts.version"

log()  { echo -e "\033[1;32m[Tabloza]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Tabloza]\033[0m $*"; }
die()  { echo -e "\033[1;31m[Tabloza] ERRORE:\033[0m $*" >&2; exit 1; }

is_ts_fork_installed() {
    [[ -f "${MARKER}" ]] && grep -qx "${RTPMIDID_VER}" "${MARKER}" 2>/dev/null
}

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

    apt-get install -y -qq libavahi-client3 libasound2 python3 2>/dev/null || true
    if ! DEBIAN_FRONTEND=noninteractive dpkg --force-confdef --force-confold -i "${tmpdir}/${deb}"; then
        apt-get install -y -f -qq
    fi
    rm -rf "${tmpdir}"
}

install_release_debs() {
    local base="$1"
    shift
    local deb
    for deb in "$@"; do
        install_deb "${base}/${deb}" "${deb}" || return 1
    done
    command -v rtpmidid >/dev/null 2>&1
}

build_from_source() {
    local tmpdir builddir
    tmpdir=$(mktemp -d)
    builddir="${tmpdir}/rtpmidid-ts"

    log "Build rtpmidid-ts da sorgente (release .deb non disponibile)..."
    apt-get update -qq
    apt-get install -y -qq \
        git curl ca-certificates \
        debhelper debhelper-compat \
        cmake ninja-build pandoc \
        libavahi-client-dev libasound2-dev \
        python3 build-essential pkg-config

    git clone --depth 1 "${RTPMIDID_REPO}" "${builddir}"

    cd "${builddir}"
    make deb
    DEB="$(ls -1 ../*.deb 2>/dev/null | grep -E '/rtpmidid_[0-9].*\.deb$' | head -1 || true)"
    [[ -n "${DEB}" ]] || die "make deb non ha prodotto rtpmidid_*.deb"

    apt-get install -y -qq libavahi-client3 libasound2 python3 2>/dev/null || true
    if ! DEBIAN_FRONTEND=noninteractive dpkg --force-confdef --force-confold -i "${DEB}"; then
        apt-get install -y -f -qq
    fi
    rm -rf "${tmpdir}"
}

if is_ts_fork_installed && [[ "${RTPMIDID_FORCE:-0}" != "1" ]]; then
    log "rtpmidid-ts ${RTPMIDID_VER} già installato: $(command -v rtpmidid)"
    exit 0
fi

if command -v rtpmidid >/dev/null 2>&1 && [[ "${RTPMIDID_FORCE:-0}" != "1" ]] && is_ts_fork_installed; then
    log "rtpmidid-ts già presente: $(command -v rtpmidid)"
    exit 0
fi

if command -v rtpmidid >/dev/null 2>&1 && ! is_ts_fork_installed; then
    warn "rtpmidid stock rilevato — upgrade a rtpmidid-ts ${RTPMIDID_VER}"
fi

ARCH="$(uname -m)"
INSTALLED=false

case "${ARCH}" in
    aarch64)
        LIB_DEB="librtpmidid0-debian-trixie-arm64-${RTPMIDID_VER}.deb"
        DEB="rtpmidid-debian-trixie-arm64-${RTPMIDID_VER}.deb"
        if install_release_debs "${RELEASE_BASE}" "${LIB_DEB}" "${DEB}"; then
            INSTALLED=true
        else
            warn "Pacchetto precompilato non trovato, compilo da sorgente..."
            if build_from_source; then
                INSTALLED=true
            fi
        fi
        ;;
    armv7l|armhf)
        LIB_DEB="librtpmidid0-debian-bookworm-armhf-${RTPMIDID_VER}.deb"
        DEB="rtpmidid-debian-bookworm-armhf-${RTPMIDID_VER}.deb"
        if install_release_debs "${RELEASE_BASE}" "${LIB_DEB}" "${DEB}"; then
            INSTALLED=true
        else
            warn "Pacchetto precompilato non trovato, compilo da sorgente..."
            if build_from_source; then
                INSTALLED=true
            fi
        fi
        ;;
    *)
        die "Architettura non supportata per rtpmidid-ts: ${ARCH}"
        ;;
esac

if [[ "${INSTALLED}" != "true" ]]; then
    die "Installazione rtpmidid-ts fallita"
fi

mkdir -p "$(dirname "${MARKER}")"
echo "${RTPMIDID_VER}" > "${MARKER}"

RTP_BIN="$(command -v rtpmidid)"
log "rtpmidid-ts installato: ${RTP_BIN} (${RTPMIDID_VER})"
