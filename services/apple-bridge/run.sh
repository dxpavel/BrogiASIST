#!/bin/bash
# BrogiASIST Apple Bridge — lokální HTTP server pro Apple data
# Spouští se přes launchd, nebo ručně: bash run.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
    echo "Vytvářím venv..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi

exec "$VENV/bin/python" "$SCRIPT_DIR/main.py"
