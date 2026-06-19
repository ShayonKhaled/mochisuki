# Deployment

## Hardware requirements

| Component | Part | Notes |
|---|---|---|
| Board | Raspberry Pi Zero 2 W | Headless, no display needed for boot |
| Display | ZJY_M242 OLED (SSD1309, 128×64) | SPI — 128×64px |
| LEDs | Adafruit NeoPixel Stick (8× WS2812B) | GPIO 18 — single-wire PWM |
| Gesture | APDS-9960 breakout | I2C — address 0x39 |
| Audio | Passive piezo buzzer | GPIO 13 — hardware PWM |
| SD card | 8GB+ Class 10 / A1 | |

## Pinout

```
GPIO 18  ─── NeoPixel Stick (data in)
GPIO 13  ─── Piezo buzzer (PWM)
I2C SDA ─── APDS-9960 SDA
I2C SCL ─── APDS-9960 SCL

ZJY_M242 OLED (SPI, SSD1309):
  GPIO 8  ─── CS  (SPI0 CE0)
  GPIO 10 ─── MOSI (SPI0 SDA)
  GPIO 11 ─── SCLK (SPI0 SCL)
  GPIO 17 ─── RST
  GPIO 25 ─── DC
```

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
