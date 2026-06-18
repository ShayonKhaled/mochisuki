import asyncio
import logging
import os
import sys

logger = logging.getLogger("mochisuki.display")


def _wrap_text(text: str, max_chars: int) -> list:
    """Simple word wrap — split on spaces, fit within max_chars."""
    words = text.split()
    lines = []
    current = ""
    for w in words:
        if current and len(current) + 1 + len(w) > max_chars:
            lines.append(current)
            current = w
        elif current:
            current += " " + w
        else:
            current = w
    if current:
        lines.append(current)
    return lines or [""]

# Bundled Waveshare e-paper library lives in lib/
_lib_path = os.path.join(os.path.dirname(__file__), "lib")
if os.path.isdir(_lib_path) and _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)


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

    async def _reinit_if_needed(self):
        """Re-initialize if display was put to sleep (SPI closed)."""
        try:
            self.driver.init()
        except Exception:
            # Some drivers throw on double-init — ignore
            pass

    async def show_face(self, face_name: str):
        """Draw a static face on the e-ink display."""
        logger.info("[display] show face: %s", face_name)
        if not self.driver:
            return
        try:
            from PIL import Image, ImageDraw
            await self._reinit_if_needed()
            W, H = self.driver.width, self.driver.height  # 128 x 296
            image = Image.new("1", (W, H), 255)
            draw = ImageDraw.Draw(image)

            if face_name == "sleeping":
                draw.text((W // 2 - 40, H // 2 - 10), "( - _ - ) zZz", fill=0)
            else:
                draw.text((W // 2 - 30, H // 2 - 10), f"[{face_name}]", fill=0)

            self.driver.display(self.driver.getbuffer(image))
        except ImportError:
            logger.warning("Pillow not available for show_face")

    async def show_notification(self, payload: dict):
        """Render a notification on the e-ink display."""
        if not self.driver:
            logger.info("[display] would show notification: %s", payload.get("title", "(no title)"))
            return
        self.refresh_counter += 1
        try:
            await self._reinit_if_needed()
            from PIL import Image, ImageDraw

            W, H = self.driver.width, self.driver.height  # 128 x 296
            image = Image.new("1", (W, H), 255)
            draw = ImageDraw.Draw(image)

            # Title bar — black background
            draw.rectangle((0, 0, W - 1, 28), fill=0)
            title = payload.get("title", "(no title)")
            draw.text((6, 6), title[:18], fill=255)

            # Body text
            body = payload.get("body", "")
            urgency = payload.get("urgency", "unknown")
            source = payload.get("source", "unknown")

            y = 36
            if body:
                for line in _wrap_text(body, 24):
                    draw.text((6, y), line, fill=0)
                    y += 16

            # Footer — urgency + source + line
            y = max(y, H - 40)
            draw.line((0, y, W - 1, y), fill=0)
            draw.text((6, y + 4), f"<{urgency}>  {source}", fill=0)

            self.driver.display(self.driver.getbuffer(image))
            logger.info("[display] rendered notification: %s", title)
        except ImportError:
            logger.warning("Pillow not available for show_notification")

    async def sleep(self):
        if self.driver:
            self.driver.sleep()
        logger.debug("[display] sleep")
