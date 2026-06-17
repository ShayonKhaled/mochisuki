"""Display test — Waveshare 2.13\" e-ink HAT (V4) on Raspberry Pi.

Uses only the waveshare_epd library + Pillow.
Gracefully exits with a message if the library isn't installed.
"""

import logging
import sys
import time

logging.basicConfig(level=logging.INFO)

try:
    from waveshare_epd import epd2in13_V4
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print(f"Library not available: {e}")
    print("Install on Raspberry Pi: pip install waveshare-epd Pillow")
    sys.exit(1)

print("Initialising Waveshare 2.13\" e-ink V4...")
epd = epd2in13_V4.EPD()
epd.init()
W, H = epd.width, epd.height  # 250 x 122

# 1 ── Clear to white ──────────────────────────────────────────────────
print("Step 1: White screen")
epd.Clear(0xFF)
time.sleep(2)

# 2 ── Full black frame ────────────────────────────────────────────────
print("Step 2: Full black")
image = Image.new("1", (W, H), 0)
epd.display(epd.getbuffer(image))
time.sleep(2)

# 3 ── Notification mockup ─────────────────────────────────────────────
print("Step 3: Notification mockup")
image = Image.new("1", (W, H), 255)
draw = ImageDraw.Draw(image)

# Title bar
draw.rectangle((0, 0, W - 1, 28), fill=0)
draw.text((8, 6), "MOCHISUKI", fill=255)

# Notification body
draw.text((8, 36), "Build pipeline #142", fill=0)
draw.text((8, 52), "Tests failed — check logs", fill=0)

# Footer
draw.line((0, 90, W - 1, 90), fill=0)
draw.text((8, 96), "urgency: HIGH  |  hermes/notify", fill=0)

epd.display(epd.getbuffer(image))
time.sleep(2)

# 4 ── Idle / sleeping face ────────────────────────────────────────────
print("Step 4: Sleeping face")
image = Image.new("1", (W, H), 255)
draw = ImageDraw.Draw(image)

# Simple ASCII-art style sleeping face
draw.text((int(W / 2) - 40, 40), "( - _ - ) zZz", fill=0)

epd.display(epd.getbuffer(image))
time.sleep(2)

# Cleanup
epd.sleep()
print("Display test complete — epd.sleep() called")
