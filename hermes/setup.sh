#!/usr/bin/env bash
# Hermes → Mochisuki — one-shot install
# Usage: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Hermes → Mochisuki notifier ==="

# Create venv if missing
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "venv created"
fi

source venv/bin/activate
pip install --upgrade pip -q
pip install paho-mqtt -q

echo ""
echo "Done. Test it:"
echo "  source venv/bin/activate"
echo "  python notify.py --ping"
echo ""
echo "Or from Python:"
echo "  from notify import HermesNotifier"
