import asyncio
import logging

logger = logging.getLogger("mochisuki.leds")


class AsyncLEDs:
    """WS2812B NeoPixel stick driver — stubbed for dev."""

    def __init__(self):
        self.strip = None

    async def init(self):
        try:
            from rpi_ws281x import PixelStrip, WS2811_STRIP_GRB
            import config
            self.strip = PixelStrip(
                config.LED_COUNT, config.LED_PIN,
                freq_hz=800000, dma=10, invert=False,
                brightness=config.LED_BRIGHTNESS, channel=0,
                strip_type=WS2811_STRIP_GRB
            )
            self.strip.begin()
            logger.info("NeoPixel strip initialized (%d LEDs)", config.LED_COUNT)
        except ImportError:
            logger.info("LEDs stubbed (rpi_ws281x not available)")
        except (RuntimeError, PermissionError, OSError) as e:
            logger.warning("LEDs stubbed (hardware error: %s)", e)
            self.strip = None

    async def set_urgency(self, urgency: str):
        logger.info("[leds] set urgency: %s", urgency)

    async def pulse(self, urgency: str, speed: str = "slow"):
        logger.info("[leds] pulse %s (speed=%s)", urgency, speed)

    async def flash_ack(self):
        logger.info("[leds] flash ack (green)")

    async def off(self):
        logger.info("[leds] off")
