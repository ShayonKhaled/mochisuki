import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# --- Hardware Pins ---
LED_PIN         = 18       # WS2812B Data Line via PWM DMA
LED_COUNT       = 8        # Stick variant total
LED_BRIGHTNESS  = 40       # Range: 0-255
BUZZER_PIN      = 13       # Dedicated PWM capable pin

# E-ink Hat Mapping (Waveshare 2.9" 296x128 V2, SPI) — superseded by OLED below
# EINK_RST_PIN    = 17
# EINK_DC_PIN     = 25
# EINK_CS_PIN     = 8
# EINK_BUSY_PIN   = 24
# EINK_PWR_PIN    = 6
# EINK_WIDTH      = 128
# EINK_HEIGHT     = 296

# ZJY_M242 OLED (SSD1309, 128×64, SPI)
OLED_CS_PIN     = 8         # SPI0 CE0
OLED_DC_PIN     = 25        # Data/Command
OLED_RST_PIN    = 17        # Reset
OLED_WIDTH      = 128
OLED_HEIGHT     = 64

# --- Network & Integration Boundaries ---
MQTT_BROKER     = os.getenv("MQTT_BROKER", "your-proxmox-tailscale-ip")
MQTT_PORT       = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_SUB  = "hermes/notify"
MQTT_TOPIC_ACK  = "hermes/ack"
MQTT_CLIENT_ID  = "mochisuki-v1"

WEBHOOK_HOST    = "0.0.0.0"
WEBHOOK_PORT    = 5000
WEBHOOK_SECRET  = os.getenv("WEBHOOK_SECRET")

# --- Timing Metrics (Seconds) ---
ESCALATION_1_SEC   = 120    # Level 1: Pulses engage
ESCALATION_2_SEC   = 300    # Level 2: Intense chimes
ESCALATION_MAX_SEC = 600    # Timeout: Drop to silent sleep

WAVE_THRESHOLD_MM  = 100    # VL53L1X proximity: object closer than this = wave

# --- Color Array Definitions (R, G, B) ---
COLOR_IDLE        = (0, 0, 0)         # Unlit
COLOR_LOW         = (0, 0, 180)       # Blue alert
COLOR_MEDIUM      = (180, 80, 0)      # Amber alert
COLOR_HIGH        = (180, 0, 0)       # Red alert
COLOR_CRITICAL    = (180, 0, 180)     # Purple alert
COLOR_ACK         = (0, 180, 0)       # Green feedback

FACE_DIR          = str(Path(__file__).parent / "assets/faces")
DB_PATH           = str(Path(__file__).parent / "data" / "events.db")
