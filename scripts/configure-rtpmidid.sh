#!/usr/bin/env bash
# Applica configurazione rtpmidid da config.json Tabloza
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/tabloza}"
PYTHONPATH="${INSTALL_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

export PYTHONPATH
python3 "${INSTALL_DIR}/src/rtpmidid_config.py" apply
