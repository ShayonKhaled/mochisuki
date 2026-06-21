# Hermes → Mochisuki Handoff

## Quick install

```bash
# Clone just the hermes folder (no need for the Mochisuki code)
# Or copy the hermes/ folder from the repo.
# Then:
cd hermes
bash setup.sh
source venv/bin/activate
python notify.py --ping   # test against localhost
```

That's it — one command, no dependencies outside this folder.

---

## What Mochisuki is

Mochisuki is a physical notification terminal — a Raspberry Pi with an OLED display, NeoPixel LEDs, a buzzer, and a gesture sensor. It sits on a desk and shows notifications published via MQTT. Hermes (or any agent) publishes to `hermes/notify` and Mochisuki handles the rest.

## How Hermes talks to Mochisuki

```
Hermes                    Mosquitto/MQTT                Mochisuki
  │                           │                            │
  │  publish hermes/notify    │                            │
  │───────────────────────────▶                            │
  │                           │  message routed            │
  │                           │───────────────────────────▶│  enqueue
  │                           │                            │  display
  │                           │  publish hermes/ack        │  LEDs + buzzer
  │                           │◀───────────────────────────│
  │  ack received             │                            │
  │◀───────────────────────────                            │
```

## MQTT topics

| Topic | Direction | Purpose |
|---|---|---|
| `hermes/notify` | Hermes → Mochisuki | Notification payload |
| `hermes/ack` | Mochisuki → Hermes | Confirmation of receipt |

## Payload schema — `hermes/notify`

```json
{
  "id":       "string (required) — unique notification id",
  "title":    "string — short headline shown on OLED",
  "body":     "string — detail text (optional)",
  "category": "string — grouping label, e.g. 'ci', 'alert', 'system'",
  "urgency":  "'low' | 'medium' | 'high' | 'critical' — defaults to 'low'",
  "source":   "string — publisher identifier, e.g. 'hermes'"
}
```

**Only `id` is mandatory.** Mochisuki drops messages without one.

## Urgency rules

Urgency controls LEDs (color) and how aggressively the notification escalates:

| Urgency | LED color | Priority |
|---|---|---|
| `low` | Blue | 1 |
| `medium` | Amber | 2 |
| `high` | Red | 3 |
| `critical` | Purple | 4 |

**Higher urgency replaces lower.** If Mochisuki is showing a `low` alert and a `high` arrives, it switches. If it's showing `high` and a `low` arrives, the low one is ignored.

## Acknowledgement — `hermes/ack`

Mochisuki publishes an ack for every valid notification:

```json
{
  "id":        "echoed from notification",
  "status":    "received",
  "device":    "mochisuki-v1",
  "timestamp": 1717000000.0
}
```

Note: acks are published before the urgency filter runs, so even a lower-urgency notification that gets rejected will still produce an ack. Ack = "we received it", not "we displayed it".

## Escalation timeline (on the device)

| Elapsed | Effect |
|---|---|
| 0s | Chime, display notification, LEDs show urgency color |
| 120s | LEDs pulse slowly |
| 300s | Intense chime, fast LED pulse |
| 600s | Timeout — returns to idle, logs as "ignored" |

## Python integration — `notify.py`

Drop `notify.py` into your Hermes project (or install the whole `hermes/` folder). It uses `paho-mqtt`, a pure-Python MQTT client.

```bash
pip install paho-mqtt
```

### As a library

```python
from hermes.notify import HermesNotifier

notifier = HermesNotifier("10.0.0.50")  # Mochisuki's IP or Tailscale IP

# With broker auth (if configured):
notifier = HermesNotifier("10.0.0.50",
                          username="mochisuki", password="your-password")

# Simple ping test
notifier.ping("hello")

# Full notification
notifier.send(
    title="Build #142 failed",
    body="Test stage — 3 failures in auth module",
    category="ci",
    urgency="high",
)

# Shorthand for critical
notifier.send_critical("Server down", "prod-api unresponsive")

notifier.close()
```

### Async (aiomqtt)

If your Hermes agent already uses `aiomqtt`, publish directly:

```python
import json, time, aiomqtt

async with aiomqtt.Client("10.0.0.50") as client:
    payload = {
        "id": "alert-001",
        "title": "Deploy complete",
        "body": "main → production, 45s",
        "category": "deploy",
        "urgency": "medium",
        "source": "hermes"
    }
    await client.publish("hermes/notify", json.dumps(payload))
```

### CLI

```bash
python notify.py --broker 10.0.0.50 --title "Deploy done" --urgency high
python notify.py --ping           # quick test against localhost
python notify.py --broker 1.2.3.4 --title "CPU spike" --urgency critical
```

## Network requirements

- **Broker:** Any standard MQTT broker (Mosquitto, EMQX, etc.)
- **Port:** 1883 (or the port Mochisuki is listening on)
- **No TLS by default** — use Tailscale, a local network, or configure TLS on the broker if needed
- **QoS 0** is fine — fire-and-forget, Mochisuki handles reconnection

## Testing without hardware

See the main project's [docs/testing.md](../docs/testing.md) — you can run a full Mochisuki stack on a MacBook with Mosquitto and the daemon in stub mode.
