"""
Mochisuki display driver — ZJY_M242 OLED (SSD1309, 128×64, SPI).

Split-screen UI with face zone (left) and content zone (right).
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("mochisuki.display")


# ── Fonts (Terminus bold — two crisp bitmap sizes) ─────────────────────

_FONT_PATH = Path(__file__).parent / "assets" / "terminus-bold.ttf"
_FONT_FACE: ImageFont.FreeTypeFont = None   # 16px — face
_FONT_BODY: ImageFont.FreeTypeFont = None   # 12px — everything else


def _load_fonts():
    global _FONT_FACE, _FONT_BODY
    try:
        _FONT_FACE = ImageFont.truetype(str(_FONT_PATH), 16)
        _FONT_BODY = ImageFont.truetype(str(_FONT_PATH), 12)
        logger.info("Fonts: 16px (face) + 12px (body)")
    except Exception as exc:
        logger.warning("Font fallback to default (%s)", exc)
        default = ImageFont.load_default()
        _FONT_FACE = _FONT_BODY = default


_load_fonts()


# ── Layout constants ──────────────────────────────────────────────────────

_DIVIDER_X = 46          # vertical split: face | content
_FACE_CX = _DIVIDER_X // 2  # 23

_CONTENT_X0 = _DIVIDER_X + 2   # 48
_CONTENT_W  = 128 - _CONTENT_X0  # 80

_FACE_Y = 24             # vertical center for all faces (64px / 2 - 16/2)
_FOOTER_Y = 48           # horizontal divider — 48+12=60, fits within 0-63
_FOOTER_TEXT_Y = 51      # 51+10=61 (ascent), text ends at ~63

# ── Faces (pure ASCII) ──────────────────────────────────────────────────

FACES = {
    "idle":       "(._.)",
    "sleeping":   "(._.)",
    "happy":      "^_^",
    "sad":        "T_T",
    "alert":      "O_O",
    "panic":      "X_X",
    "snooze":     "-_^",
    "dead":       "x_x",
}


# ── Drawing helpers ───────────────────────────────────────────────────────

def _draw_frame(draw: ImageDraw, brightness: int = 255):
    """Screen border (1px) + vertical divider at *DIVIDER_X*."""
    # Outer border
    draw.rectangle([0, 0, 127, 63], fill=0, outline=brightness)
    # Vertical divider — full height
    draw.line([(_DIVIDER_X, 1), (_DIVIDER_X, 62)],
              fill=brightness)


def _draw_face(draw: ImageDraw, face: str, y: int, brightness: int = 255):
    """Draw a face centred in the left zone at *y*."""
    w = _FONT_FACE.getbbox(face)[2]
    x = _FACE_CX - w // 2
    draw.text((x, y), face, font=_FONT_FACE, fill=brightness)


def _draw_content_line(draw: ImageDraw, text: str, y: int,
                       brightness: int = 255):
    """Draw a line of text in the content zone at *y*."""
    draw.text((_CONTENT_X0, y), text, font=_FONT_BODY, fill=brightness)


def _draw_content_centred(draw: ImageDraw, text: str, y: int,
                          brightness: int = 255):
    """Draw text centred in the content zone at *y*."""
    w = _FONT_BODY.getbbox(text)[2]
    x = _CONTENT_X0 + (_CONTENT_W - w) // 2
    draw.text((x, y), text, font=_FONT_BODY, fill=brightness)


def _draw_footer(draw: ImageDraw, text: str,
                 text_brightness: int = 255,
                 line_brightness: int = 255):
    """Footer horizontal line + centred text."""
    draw.line([(_DIVIDER_X + 1, _FOOTER_Y), (126, _FOOTER_Y)],
              fill=line_brightness)
    _draw_content_centred(draw, text, _FOOTER_TEXT_Y,
                          brightness=text_brightness)


def _summarize(text: str, max_words: int = 3, max_px: int = 72) -> str:
    """First *max_words* words, truncated to fit *max_px* pixels."""
    words = text.strip().split()
    if not words:
        return ""
    short = " ".join(words[:max_words])
    w = _FONT_BODY.getbbox(short)[2]
    if w <= max_px:
        return short
    while short and _FONT_BODY.getbbox(short + "…")[2] > max_px:
        short = short[:-1]
    return short + "…" if short else ""


# ── Display class ─────────────────────────────────────────────────────────

class AsyncDisplay:
    """ZJY_M242 OLED (SSD1309, 128×64, SPI) via luma.oled."""

    _contrast_full = 255
    _contrast_dim  = 60

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
                device=0,
                gpio_DC=config.OLED_DC_PIN,
                gpio_RST=config.OLED_RST_PIN,
            )
            self.device = ssd1309(serial, width=self.width, height=self.height)
            self.device.contrast(self._contrast_full)
            self.device.show()
            logger.info("OLED initialized (ZJY_M242 SSD1309 128×64 SPI)")
        except ImportError:
            logger.info("OLED stubbed (luma.oled not available)")
        except Exception as e:
            logger.error("OLED init failed: %s", e)
            self.device = None

    async def _render(self, draw_func, contrast: int = None):
        """Render via luma's canvas (proven to work on this device)."""
        if not self.device:
            return
        try:
            from luma.core.render import canvas

            with canvas(self.device) as draw:
                draw_func(draw)
            self.device.show()
            if contrast is not None:
                self.device.contrast(contrast)
        except Exception as e:
            logger.error("Render failed: %s", e)

    # ── IDLE ──────────────────────────────────────────────────────────

    async def show_idle(self, connected: bool = True,
                        now: datetime = None) -> None:
        """Sleeping face left, clock right."""
        if not self.device:
            logger.info("[display] idle (connected=%s)", connected)
            return
        now = now or datetime.now()
        time_str = now.strftime("%H:%M")

        def _draw(draw):
            _draw_frame(draw, brightness=80)
            _draw_face(draw, FACES["idle"], _FACE_Y, brightness=180)
            _draw_content_centred(draw, time_str, 18, brightness=180)
            # Connection dot under the face
            dot = "•" if connected else "○"
            w = _FONT_BODY.getbbox(dot)[2]
            draw.text((_FACE_CX - w // 2, 40), dot, font=_FONT_BODY,
                      fill=120 if connected else 50)
            _draw_footer(draw, "  zzz",
                         text_brightness=80, line_brightness=60)

        await self._render(_draw, contrast=self._contrast_dim)
        logger.debug("[display] idle %s  %s", time_str, "OK" if connected else "??")

    # ── ALERT ─────────────────────────────────────────────────────────

    async def show_alert(self, payload: dict) -> None:
        """Single-line notification: face + urgency + short message."""
        if not self.device:
            logger.info("[display] alert: %s", payload.get("title"))
            return

        title = (payload.get("title") or "").strip()
        body = (payload.get("body") or "").strip()
        urgency = (payload.get("urgency") or "medium").lower()
        source = (payload.get("source") or "").strip()

        # One short message: prefer title, fall back to body, then source
        msg = _summarize(title) or _summarize(body) or _summarize(source) or "?"

        # Face + urgency marker
        if urgency in ("high", "critical"):
            face = FACES["panic"]
            marker = "!!"
            bright = 255
        elif urgency == "medium":
            face = FACES["alert"]
            marker = "! "
            bright = 255
        else:
            face = FACES["alert"]
            marker = "o "
            bright = 200

        def _draw(draw):
            _draw_frame(draw, brightness=255)
            _draw_face(draw, face, _FACE_Y, brightness=bright)
            draw.text((_FACE_CX - 6, 41), marker, font=_FONT_BODY,
                      fill=bright)
            _draw_content_centred(draw, msg, 18, brightness=255)
            _draw_footer(draw, "← dismiss",
                         text_brightness=180, line_brightness=180)

        await self._render(_draw, contrast=self._contrast_full)
        logger.info("[display] alert %s [%s]", msg, urgency)

    # ── ACK ───────────────────────────────────────────────────────────

    async def show_ack(self, title: str = "") -> None:
        """Happy face + confirmation."""
        if not self.device:
            logger.info("[display] ack")
            return

        def _draw(draw):
            _draw_frame(draw, brightness=255)
            _draw_face(draw, FACES["happy"], _FACE_Y, brightness=255)
            _draw_content_centred(draw, "got it!", 10, brightness=200)
            _draw_content_centred(draw, "*", 26, brightness=100)
            _draw_footer(draw, "goodnight",
                         text_brightness=120, line_brightness=120)

        await self._render(_draw, contrast=self._contrast_full)

    # ── SNOOZE ────────────────────────────────────────────────────────

    async def show_snooze(self, remaining_sec: int,
                          resume_time: str = "") -> None:
        """Half-asleep face + countdown."""
        if not self.device:
            logger.info("[display] snooze %ds", remaining_sec)
            return

        if remaining_sec >= 3600:
            remaining_str = f"{remaining_sec // 3600}:{(remaining_sec % 3600) // 60:02d}"
        else:
            remaining_str = f"{remaining_sec // 60}:{remaining_sec % 60:02d}"

        def _draw(draw):
            _draw_frame(draw, brightness=100)
            _draw_face(draw, FACES["alert"], _FACE_Y, brightness=100)
            _draw_content_centred(draw, remaining_str, 10, brightness=180)
            if resume_time:
                _draw_content_centred(draw, f"~{resume_time}",
                                      26, brightness=80)
            _draw_footer(draw, "snoozing",
                         text_brightness=80, line_brightness=60)

        await self._render(_draw, contrast=self._contrast_dim)

    # ── SULK ──────────────────────────────────────────────────────────

    async def show_sulk(self, payload: dict) -> None:
        """Sulky face + missed info."""
        if not self.device:
            logger.info("[display] sulk: %s", payload.get("title"))
            return

        def _draw(draw):
            _draw_frame(draw, brightness=60)
            _draw_face(draw, FACES["sad"], _FACE_Y, brightness=60)
            _draw_content_centred(draw, "missed", 18, brightness=80)
            _draw_footer(draw, "timed out",
                         text_brightness=40, line_brightness=30)

        await self._render(_draw, contrast=self._contrast_dim)

    # ── Convenience ───────────────────────────────────────────────────

    async def show_notification(self, payload: dict, face: str = None) -> None:
        await self.show_alert(payload)

    async def show_face(self, name: str) -> None:
        await self.show_idle(connected=True)

    async def sleep(self) -> None:
        if self.device:
            try:
                self.device.hide()
                logger.debug("[display] sleep")
            except Exception:
                pass
