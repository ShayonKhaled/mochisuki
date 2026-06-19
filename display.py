"""
Mochisuki display driver — ZJY_M242 OLED (SSD1309, 128×64, SPI).

Uses luma.oled for the device interface and Pillow for rendering.
Gracefully degrades to a console-logging stub when luma.oled is not installed.
"""

import asyncio
import logging

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


# ── Layout constants (128×64 OLED) ────────────────────────────────────

_TITLE_H   = 10    # title bar height (px)
_LINE_H    = 10    # line height for body text
_BODY_Y    = 12    # first body line y-offset
_FOOTER_Y  = 54    # footer y-offset
_WRAP_AT   = 16    # max characters per body line
_MAX_LINES = 5     # max body lines before footer


class AsyncDisplay:
    """ZJY_M242 OLED (SSD1309, 128×64, SPI) via luma.oled."""

    def __init__(self):
        self.device = None
        self.width = 128
        self.height = 64

    async def init(self):
        """Initialise the SSD1309 over SPI. Falls back to stub on ImportError."""
        try:
            from luma.core.interface.serial import spi
            from luma.oled.device import ssd1309
            import config

            serial = spi(
                port=0,
                device=0,              # CE0 → GPIO 8
                gpio_DC=config.OLED_DC_PIN,
                gpio_RST=config.OLED_RST_PIN,
            )
            self.device = ssd1309(serial, width=self.width, height=self.height)
            self.device.contrast(255)
            logger.info("OLED display initialized (ZJY_M242 SSD1309 128×64 SPI)")
        except ImportError:
            logger.info("OLED display stubbed (luma.oled not available)")
        except Exception as e:
            logger.error("OLED display init failed: %s", e)
            self.device = None

    async def show_face(self, face_name: str):
        """Draw a static face on the OLED."""
        logger.info("[display] show face: %s", face_name)
        if not self.device:
            return
        try:
            from luma.core.render import canvas

            with canvas(self.device) as draw:
                if face_name == "sleeping":
                    draw.text((24, 27), "( - _ - ) zZz", fill="white")
                else:
                    draw.text((32, 27), f"[{face_name}]", fill="white")
        except Exception as e:
            logger.error("show_face failed: %s", e)

    async def show_notification(self, payload: dict):
        """Render a notification on the 128×64 OLED display."""
        if not self.device:
            logger.info("[display] would show notification: %s",
                        payload.get("title", "(no title)"))
            return
        try:
            from luma.core.render import canvas

            title = payload.get("title", "(no title)")
            body = payload.get("body", "")
            urgency = payload.get("urgency", "unknown")
            source = payload.get("source", "unknown")

            with canvas(self.device) as draw:
                # ── Title bar — inverted highlight ─────────────────
                draw.rectangle((0, 0, self.width - 1, _TITLE_H - 1), fill="white")
                draw.text((2, 1), title[:18], fill="black")

                # ── Body lines ────────────────────────────────────
                lines = _wrap_text(body, _WRAP_AT)[:_MAX_LINES]

                y = _BODY_Y
                for line in lines:
                    draw.text((2, y), line, fill="white")
                    y += _LINE_H

                # ── Footer — urgency + source ─────────────────────
                footer = f"<{urgency}>  {source}"[:24]
                draw.text((2, _FOOTER_Y), footer, fill="white")

            logger.info("[display] rendered notification: %s", title)
        except ImportError:
            logger.warning("Pillow not available for show_notification")
        except Exception as e:
            logger.error("show_notification failed: %s", e)

    async def sleep(self):
        """Put the OLED into power-save mode."""
        if self.device:
            try:
                self.device.hide()
                logger.debug("[display] sleep")
            except Exception:
                pass
