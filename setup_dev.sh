#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q

# Install deps
pip install paho-mqtt==2.1.0 microdot==2.1.0 python-dotenv==1.0.1 aiohttp==3.9.5 Pillow==10.3.0 -q
echo "--- venv deps installed ---"
