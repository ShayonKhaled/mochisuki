import asyncio
import logging

logger = logging.getLogger("mochisuki.display")


class AsyncDisplay:
    """Waveshare 2.9\" e-ink display driver (296x128, SPI, epd2in9_V2)."""

    def __init__(self):
        self.driver = None
        self.refresh_counter = 0

    async def init(self):
        try:
            from waveshare_epd import epd2in9_V2
            self.driver = epd2in9_V2.EPD()
            ret = self.driver.init()
            if ret == 0:
                self.driver.Clear(0xFF)
                logger.info("E-ink display initialized (2.9\" 296x128 V2)")
            else:
                logger.error("E-ink init() returned %d — display may not be connected", ret)
                self.driver = None
        except ImportError:
            logger.info("E-ink display stubbed (waveshare_epd not available)")
        except Exception as e:
            logger.error("E-ink display init failed: %s", e)
            self.driver = None

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
