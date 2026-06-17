import asyncio
import logging

logger = logging.getLogger("mochisuki.display")


class AsyncDisplay:
    """Waveshare 2.13" e-ink display driver — stubbed for dev."""

    def __init__(self):
        self.driver = None
        self.refresh_counter = 0

    async def init(self):
        try:
            from waveshare_epd import epd2in13_V4
            self.driver = epd2in13_V4.EPD()
            self.driver.init()
            self.driver.Clear(0xFF)
            logger.info("E-ink display initialized")
        except ImportError:
            logger.info("E-ink display stubbed (waveshare_epd not available)")

    async def show_face(self, face_name: str):
        logger.info("[display] show face: %s", face_name)

    async def show_notification(self, payload: dict):
        if not self.driver:
            logger.info("[display] would show notification: %s", payload.get("title", "(no title)"))
            return
        self.refresh_counter += 1
        if self.refresh_counter % 10 == 0:
            self.driver.init()
        logger.info("[display] rendered notification: %s", payload.get("title", "(no title)"))

    async def sleep(self):
        if self.driver:
            self.driver.sleep()
        logger.debug("[display] sleep")
