"""
Quick WS2812B LED test — cycle through colors.
Run on Pi with: sudo venv/bin/python test_leds.py
"""
import time
import sys
sys.path.insert(0, ".")

from rpi_ws281x import PixelStrip, WS2811_STRIP_GRB
import config

strip = PixelStrip(
    config.LED_COUNT, config.LED_PIN,
    freq_hz=800000, dma=10, invert=False,
    brightness=config.LED_BRIGHTNESS, channel=0,
    strip_type=WS2811_STRIP_GRB
)
strip.begin()

print(f"WS2812B test: {config.LED_COUNT} LEDs on GPIO {config.LED_PIN}")
print()

# Cycle through colors
colors = [
    ("RED",    255, 0, 0),
    ("GREEN",  0, 255, 0),
    ("BLUE",   0, 0, 255),
    ("AMBER",  180, 80, 0),
    ("PURPLE", 180, 0, 180),
    ("WHITE",  128, 128, 128),
    ("OFF",    0, 0, 0),
]

for name, r, g, b in colors:
    print(f"  {name}")
    for i in range(config.LED_COUNT):
        strip.setPixelColor(i, (r << 16) | (g << 8) | b)
    strip.show()
    time.sleep(1.5)

# Chase animation
print()
print("Chase animation...")
for _ in range(config.LED_COUNT * 2):
    for i in range(config.LED_COUNT):
        strip.setPixelColor(i, 0)
    strip.setPixelColor(_ % config.LED_COUNT, (0 << 16) | (180 << 8) | 0)
    strip.show()
    time.sleep(0.12)

# All off
for i in range(config.LED_COUNT):
    strip.setPixelColor(i, 0)
strip.show()

print()
print("Done! Connect WS2812B data line to GPIO 18 (pin 12)")
print("VCC → 5V (pin 2 or 4), GND → GND (pin 6 or 14)")
