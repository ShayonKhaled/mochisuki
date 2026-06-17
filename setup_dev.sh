#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q

# Install deps — Pillow uses the system package for this arch
pip install asyncio-mqtt==0.4.0 microdot==2.1.0 python-dotenv==1.0.1 aiohttp==3.9.5 -q
echo "--- venv deps installed ---"
