# Testing

## On a MacBook (no Raspberry Pi required)

All four hardware drivers gracefully degrade via `try/except ImportError`. When the RPi-specific packages (`RPi.GPIO`, `rpi-ws281x`, `smbus2`, `luma.oled`) aren't installed, the drivers log what they *would* do and return safe defaults.

### 1. Install a local MQTT broker

```bash
brew install mosquitto
brew services start mosquitto
```

### 2. Create a virtual environment

```bash
cd /path/to/mochisuki
python3 -m venv venv
source venv/bin/activate
pip install aiomqtt==2.5.1 python-dotenv==1.0.1 Pillow==10.3.0
```

### 3. Configure

```bash
cat > .env << 'EOF'
MQTT_BROKER=localhost
MQTT_PORT=1883
EOF
```

### 4. Run the daemon

```bash
python main.py
```

You'll see:

```
[mochisuki.engine] Mochisuki engine starting — state=IDLE
[mochisuki.proximity] vl53l1x not available — proximity sensor stubbed
[mochisuki.leds] LEDs stubbed (rpi_ws281x not available)
[mochisuki.buzzer] Buzzer initialized (PWM pin 13)
[mochisuki.display] OLED display stubbed (luma.oled not available)
[mochisuki.engine] Connecting to MQTT broker at localhost:1883
[mochisuki.engine] MQTT connected — subscribing to hermes/notify
```

### 5. Send test notifications

Open a second terminal and publish:

```bash
# Low urgency
mosquitto_pub -h localhost -t hermes/notify -m '{
  "id": "test-1",
  "title": "Low urgency test",
  "body": "From the CLI",
  "category": "general",
  "urgency": "low",
  "source": "cli"
}'

# High urgency (replaces the low one)
mosquitto_pub -h localhost -t hermes/notify -m '{
  "id": "test-2",
  "title": "High urgency!",
  "body": "This should override",
  "category": "alert",
  "urgency": "high",
  "source": "cli"
}'

# Critical
mosquitto_pub -h localhost -t hermes/notify -m '{
  "id": "test-3",
  "title": "CRITICAL",
  "body": "Purple alert",
  "category": "system",
  "urgency": "critical",
  "source": "cli"
}'
```

### 6. Watch acknowledgements

```bash
mosquitto_sub -h localhost -t hermes/ack
```

You'll see JSON acks like:

```json
{"id":"test-1","status":"received","device":"mochisuki-v1","timestamp":1717000000.0}
```

### 7. Test escalations

Start with a notification, then wait. At ~120s you'll see:

```
[mochisuki.engine] Escalation level 1 (120s)
[leds] pulse high (speed=slow)
```

At ~300s:

```
[mochisuki.engine] Escalation level 2 (300s)
[leds] pulse high (speed=fast)
[buzzer] chime: escalation level 2 (intense)
```

At ~600s it times out and returns to idle.

### 8. Test lower-urgency replacement

Send a `critical` notification, then a `low` one — the low one is ignored because the urgency priority is lower:

```
[mochisuki.engine] Notification t4 superseded by current t3 (urgency too low)
```

---

## Automated tests

Currently no test suite. To add one, look at the `test` skill in `.reasonix/`.

---

## On Raspberry Pi

See [deployment.md](deployment.md) for full hardware setup and provisioning.
