#!/usr/bin/env python3
"""
Standalone OLED display test for Mochisuki — ZJY_M242 (SSD1309, 128×64, SPI).

Displays a test pattern then shows a sample notification.
Run on the Pi directly.

Usage:
    python test_display.py
"""

import asyncio
import logging
import time

from display import AsyncDisplay
from luma.core.render import canvas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_display")


async def main():
    logger.info("=== OLED Display Test ===")

    display = AsyncDisplay()
    await display.init()
    if not display.device:
        logger.error("Display not available — aborting")
        return 1

    # ── Test 1: sleeping face ─────────────────────────────────────────
    logger.info("Test 1 — sleeping face")
    await display.show_face("sleeping")
    await asyncio.sleep(3)

    # ── Test 2: notification card ─────────────────────────────────────
    logger.info("Test 2 — notification")
    await display.show_notification({
        "title": "Hello from Mochisuki!",
        "body": "This is a test notification on the ZJY_M242 OLED. SSD1309 128x64 via SPI.",
        "urgency": "low",
        "source": "test_script",
    })
    await asyncio.sleep(5)

    # ── Test 3: high urgency notification ─────────────────────────────
    logger.info("Test 3 — high-urgency notification")
    await display.show_notification({
        "title": "Alert: CPU Temp",
        "body": "Core temperature 78°C — above threshold.",
        "urgency": "high",
        "source": "sensors",
    })
    await asyncio.sleep(5)

    # ── Test 4: direct render with canvas ─────────────────────────────
    logger.info("Test 4 — custom canvas render")
    with canvas(display.device) as draw:
        draw.rectangle((0, 0, 127, 63), outline="white", fill=None)
        draw.text((20, 27), "Test Complete!", fill="white")
    await asyncio.sleep(3)

    # ── Clean up ──────────────────────────────────────────────────────
    logger.info("Tests done — putting display to sleep")
    await display.show_face("sleeping")
    await display.sleep()

    logger.info("=== Test Complete ===")
    return 0


if __name__ == "__main__":
    asyncio.run(main())
