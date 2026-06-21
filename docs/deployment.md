# Deployment

## Hardware requirements

| Component | Part | Notes |
|---|---|---|
| Board | Raspberry Pi Zero 2 W | Headless, no display needed for boot |
| Display | ZJY_M242 OLED (SSD1309, 128×64) | SPI — 128×64px |
| LEDs | Adafruit NeoPixel Stick (8× WS2812B) | GPIO 18 — single-wire PWM |
| Proximity | VL53L1X ToF breakout | I2C — address 0x29 |
| Audio | Passive piezo buzzer | GPIO 13 — hardware PWM |
| SD card | 8GB+ Class 10 / A1 | |

## Pinout

### 40-pin header connections

```
 Phy │ BCM GPIO │ Signal      → Component
─────┼──────────┼─────────────────────────────────
   1 │ —        │ 3.3V        → VL53L1X VIN + OLED VCC
   3 │ 2        │ SDA1 (I2C)  → VL53L1X SDA
   5 │ 3        │ SCL1 (I2C)  → VL53L1X SCL
   6 │ —        │ GND         → VL53L1X GND + OLED GND
─────┼──────────┼─────────────────────────────────
  24 │ 8        │ SPI0 CE0    → OLED CS
  19 │ 10       │ SPI0 MOSI   → OLED SDA (MOSI)
  23 │ 11       │ SPI0 SCLK   → OLED SCL (SCLK)
  11 │ 17       │ GPIO 17     → OLED RST
  22 │ 25       │ GPIO 25     → OLED DC
─────┼──────────┼─────────────────────────────────
  33 │ 13       │ GPIO 13     → Piezo buzzer (PWM)
  12 │ 18       │ GPIO 18     → NeoPixel Stick (data in)
```

### Notes

- I2C (VL53L1X) uses the dedicated hardware bus on Phy pins 3/5 (BCM 2/3) — no software bit-banging.
- SPI (OLED) uses SPI0 at Phy pins 19/23/24 (BCM 10/11/8).
- GND can be shared across components (Phy pins 6, 9, 14, 20, 25, 30, 34, 39).
- NeoPixel data-in is a single wire; VCC (5V) and GND should be supplied separately to the stick.

## OS setup

1. Flash Raspberry Pi OS Lite (Bookworm, 64-bit) to an SD card.
2. Enable SSH, Wi-Fi, I2C, and SPI:

```bash
sudo raspi-config
# → Interface Options → I2C → Enable
# → Interface Options → SPI → Enable
```

3. Install system dependencies:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

## MQTT broker security (recommended)

At minimum, add a password file to prevent unauthorised publishing:

```bash
# Create a mosquitto password file
sudo mosquitto_passwd -c /etc/mosquitto/passwd mochisuki

# Add it to mosquitto config
echo "password_file /etc/mosquitto/passwd" | sudo tee -a /etc/mosquitto/mosquitto.conf
sudo systemctl restart mosquitto
```

For TLS (self-signed):
```bash
# Generate a self-signed cert
sudo mkdir -p /etc/mosquitto/certs
sudo openssl req -new -x509 -days 365 -nodes \
  -out /etc/mosquitto/certs/server.crt \
  -keyout /etc/mosquitto/certs/server.key
echo -e "listener 8883\ncafile /etc/mosquitto/certs/server.crt\ncertfile /etc/mosquitto/certs/server.crt\nkeyfile /etc/mosquitto/certs/server.key\nrequire_certificate false" | sudo tee /etc/mosquitto/conf.d/tls.conf
sudo systemctl restart mosquitto
```

Then set the credentials in `.env`:
```bash
echo "MQTT_USERNAME=mochisuki" >> .env
echo "MQTT_PASSWORD=your-password" >> .env
# For TLS:
echo "MQTT_TLS=true" >> .env
```

## Application setup

```bash
git clone git@github.com:ShayonKhaled/mochisuki.git /home/pi/mochisuki
cd /home/pi/mochisuki

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env with your MQTT broker IP
cat > .env << 'EOF'
MQTT_BROKER=10.0.0.50   # or your Tailscale IP
MQTT_PORT=1883
EOF
```

## Systemd service

Create `/etc/systemd/system/mochisuki.service`:

```ini
[Unit]
Description=Mochisuki notification daemon
After=network.target mosquitto.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mochisuki
ExecStart=/home/pi/mochisuki/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mochisuki
sudo journalctl -u mochisuki -f
```

## Verifying

```bash
# From any machine on the same network:
mosquitto_pub -h <pi-ip> -t hermes/notify -m '{"id":"deploy-test","title":"Hello RPi","body":"It works","category":"general","urgency":"low","source":"deploy"}'

# Check the daemon log:
sudo journalctl -u mochisuki --since "5 minutes ago"
```

## Updating

```bash
cd /home/pi/mochisuki
git pull
sudo systemctl restart mochisuki
```
