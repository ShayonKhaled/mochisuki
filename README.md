# Mochisuki

**Notification daemon for Raspberry Pi Zero W** — listens for notifications via MQTT, then drives e-ink display, NeoPixel LEDs, a piezo buzzer, and a gesture sensor for hands-free interaction.

A Mochisuki device sits on your desk and acts as a physical notification terminal. Any Hermes-compatible agent (or your own scripts) can publish a notification to `hermes/notify`, and the daemon handles the rest: visual display, urgency escalation, snooze/dismiss via gesture, and persistent event logging.

---

## Quick start (development on MacBook)

Hardware drivers gracefully degrade — all four subsystems log to console when RPi packages aren't available.

```bash
# 1. Install a local MQTT broker
brew install mosquitto && brew services start mosquitto

# 2. Create venv and install deps
python3 -m venv venv
source venv/bin/activate
pip install aiomqtt==2.5.1 python-dotenv==1.0.1 Pillow==10.3.0

# 3. Point to localhost
cat > .env << 'EOF'
MQTT_BROKER=localhost
MQTT_PORT=1883
EOF

# 4. Run it
python main.py
```

Publish a test from another terminal:

```bash
mosquitto_pub -h localhost -t hermes/notify -m '{"id":"t1","title":"Hello","body":"test","category":"general","urgency":"low","source":"cli"}'
```

See [docs/testing.md](docs/testing.md) for the full walkthrough.

---

## Layout

| Path | Role |
|---|---|
| `main.py` | Entry point — `MochisukiEngine` state machine + MQTT client |
| `config.py` | Pin mappings, MQTT topics, timing constants, colors |
| `personality.py` | WAL-mode SQLite event store |
| `gesture.py` / `display.py` / `leds.py` / `buzzer.py` | Async hardware drivers (stub gracefully) |
| `docs/` | Architecture, testing, deployment guides |

See [docs/architecture.md](docs/architecture.md) for the full design.

---

## Stack

- **Python 3.11+** — single-threaded `asyncio` event loop
- **aiomqtt** — async MQTT client (subscribes `hermes/notify`, publishes `hermes/ack`)
- **microdot** — async HTTP server (webhook endpoint — coming in phase 2)
- **ProductionLogger** — SQLite with WAL + `synchronous=NORMAL` for SD-card longevity
- **Hardware** — PAJ7620U2 (gesture), WS2812B (NeoPixels), Waveshare e-ink, piezo buzzer
