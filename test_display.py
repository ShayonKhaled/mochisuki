"""Visible flash test - full screen changes"""
import logging, time
logging.basicConfig(level=logging.INFO)

from waveshare_epd import epd2in9_V2
from PIL import Image, ImageDraw

epd = epd2in9_V2.EPD()
print(f"Starting...")
epd.init()

# 1. Clear to white
epd.Clear(0xFF)
print("Step 1: White screen (should be white)")

time.sleep(3)

# 2. Full black
image = Image.new("1", (epd.width, epd.height), 0)  # all black
epd.display(epd.getbuffer(image))
print("Step 2: All BLACK - do you see dark screen?")

time.sleep(3)

# 3. All white
image = Image.new("1", (epd.width, epd.height), 255)  # all white
epd.display(epd.getbuffer(image))
print("Step 3: All WHITE - do you see white screen now?")

time.sleep(3)

# 4. Text
image = Image.new("1", (epd.width, epd.height), 255)
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, epd.width-1, epd.height-1), fill=0)
draw.text((10, 60), "Mochisuki!", fill=255)
draw.text((10, 130), "2.9 inch", fill=255)
draw.text((10, 200), "Pi Zero", fill=255)
epd.display(epd.getbuffer(image))
print("Step 4: Text on black - can you read it?")

epd.sleep()
