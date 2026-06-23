# Hermes → Mochisuki: Deploy Playbook

**Audience:** Hermes (your agent). Follow these steps in order when deploying
Mochisuki onto a target Raspberry Pi. Assume nothing — read files as you go.

---

## 0. Prerequisites

- Target Pi is running Raspberry Pi OS Lite (Bookworm), I2C + SPI enabled
- You have SSH access to the Pi (see `pi-tailscale-access` memory)
- You (Hermes) are running a Mosquitto MQTT broker (see `mqtt-broker`)

## 1. Determine your broker IP

Mochisuki needs to know where your Mosquitto broker lives. Pick the address
that the Pi can reach:

| If broker is… | Use this address |
|---|---|
| On the same LAN as the Pi | Hermes VM LAN IP (e.g. `192.168.40.173`) |
| On Tailscale | Hermes' Tailscale IP (e.g. `100.x.x.x`) |
| On the Pi itself | `127.0.0.1` |

> **If unsure:** run `hostname -I` on this machine and try each address.
> The Pi can reach Tailscale IPs even across subnets.

## 2. Push code to the Pi

Use the `store_checkout` skill to sync the latest repo to the Pi:

```
~/mochisuki
```

After pushing, SSH in and confirm the repo is there:

```bash
ssh shayonised@100.67.9.6 "ls ~/mochisuki/main.py"
```

## 3. Create `.env` on the Pi

Write `~/mochisuki/.env` with the broker IP from step 1:

```ini
MQTT_BROKER=<broker-ip-from-step-1>
MQTT_PORT=1883
```

**If broker auth is set up** (password file on the broker), also add:

```ini
MQTT_USERNAME=mochisuki
MQTT_PASSWORD=<password-from-broker-setup>
```

See `mqtt-auth-todo` memory for the full MQTT auth setup procedure.

## 4. Install system dependencies

```bash
ssh shayonised@100.67.9.6 "
  sudo apt update &&
  sudo apt install -y python3-venv python3-pip git
"
```

If the broker runs on the Pi (not your VM), also install Mosquitto:

```bash
ssh shayonised@100.67.9.6 "
  sudo apt install -y mosquitto mosquitto-clients &&
  sudo systemctl enable --now mosquitto
"
```

## 5. Set up Python environment

```bash
ssh shayonised@100.67.9.6 "
  cd ~/mochisuki &&
  bash setup_dev.sh
"
```

This creates a venv and installs pip dependencies.

## 6. Create systemd service

Mochisuki needs to auto-start on boot. Write this file on the Pi:

**`/etc/systemd/system/mochisuki.service`**

```ini
[Unit]
Description=Mochisuki notification daemon
After=network.target

[Service]
Type=simple
User=shayonised
WorkingDirectory=/home/shayonised/mochisuki
ExecStart=/home/shayonised/mochisuki/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
ssh shayonised@100.67.9.6 "
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now mochisuki
"
```

Check it started cleanly:

```bash
ssh shayonised@100.67.9.6 "sudo journalctl -u mochisuki -n 20 --no-pager"
```

## 7. Test end-to-end

From this machine, publish a test notification:

```bash
source ./hermes/venv/bin/activate
python hermes/notify.py --broker <broker-ip> --title "Deploy test" --urgency high --ping
```

Expected output in journalctl:

```
Mochisuki engine starting — state=IDLE
MQTT connected — subscribed to hermes/notify
Notification enqueued: Hermes deploy-test [high]
→ ALERTING: Hermes deploy-test [high]
```

If you see `MQTT disconnected (Connection refused), retrying in 5s...`,
the broker IP in `.env` is wrong — go back to step 1 and try a different address.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Connection refused` connecting to broker | Wrong `MQTT_BROKER` IP — check step 1 |
| `MQTT connected` but no notifications arrive | Broker auth mismatch — check username/password |
| `[Errno 13] Permission denied` on LEDs | Needs root for DMA. Either run as `sudo` or add `CAP_SYS_RAWIO` to the systemd service (see `docs/deployment.md`) |
| `I2C bus error` on proximity | Wiring or I2C not enabled (`sudo raspi-config` → Interface Options → I2C) |
