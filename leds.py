import asyncio
import logging
from typing import Optional

logger = logging.getLogger("mochisuki.leds")


class AsyncLEDs:
    """WS2812B NeoPixel stick driver."""

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

    # ── helpers ──────────────────────────────────────────────────────

    def _pack(self, r: int, g: int, b: int) -> int:
        return (r << 16) | (g << 8) | b

    def _set_all(self, r: int, g: int, b: int):
        if not self.strip:
            return
        color = self._pack(r, g, b)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
        self.strip.show()

    def _color_for(self, urgency: str):
        import config
        return {
            "low":      config.COLOR_LOW,
            "medium":   config.COLOR_MEDIUM,
            "high":     config.COLOR_HIGH,
            "critical": config.COLOR_CRITICAL,
        }.get(urgency, config.COLOR_MEDIUM)

    # ── public API ───────────────────────────────────────────────────

    async def set_urgency(self, urgency: str):
        """Solid color for the notification urgency."""
        r, g, b = self._color_for(urgency)
        self._set_all(r, g, b)
        logger.info("[leds] urgency %s", urgency)

    async def flash_continuous(self, urgency: str, speed: str = "slow",
                                 stop_event: Optional[asyncio.Event] = None):
        """Blinks the urgency color on/off until *stop_event* is set.

        If no stop_event is provided, flashes once (on + off) and returns.
        """
        r, g, b = self._color_for(urgency)
        delay = 0.15 if speed == "fast" else 0.4
        if stop_event is None:
            self._set_all(r, g, b)
            await asyncio.sleep(delay)
            self._set_all(0, 0, 0)
            await asyncio.sleep(delay)
            return
        while not stop_event.is_set():
            self._set_all(r, g, b)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            if stop_event.is_set():
                break
            self._set_all(0, 0, 0)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
        logger.debug("[leds] flash_continuous %s (%s) stopped", urgency, speed)

    async def flash_ack(self):
        """Quick green acknowledgment flash."""
        import config
        r, g, b = config.COLOR_ACK
        for _ in range(2):
            self._set_all(r, g, b)
            await asyncio.sleep(0.12)
            self._set_all(0, 0, 0)
            await asyncio.sleep(0.12)
        logger.info("[leds] ack flash")

    async def off(self):
        """All off."""
        self._set_all(0, 0, 0)
        logger.info("[leds] off")
