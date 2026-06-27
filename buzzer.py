"""
Active electromagnetic buzzer driver for Raspberry Pi — chirping patterns.

This is a standard active buzzer with an internal oscillator. Applying
DC power (GPIO HIGH) produces a fixed tone (~2.3 kHz). No PWM needed.
The buzzer pin is toggled HIGH/LOW in short patterns to create chirps.

Degrades gracefully to logging on ImportError (no RPi.GPIO available).
"""

import asyncio
import logging

logger = logging.getLogger("mochisuki.buzzer")


class AsyncBuzzer:
    """Active buzzer driver — GPIO HIGH = sound ON, LOW = OFF."""

    def __init__(self):
        self._pin = None
        self._gpio = None

    async def init(self):
        """Set up GPIO pin for buzzer output."""
        try:
            import RPi.GPIO as GPIO
            import config

            self._gpio = GPIO
            self._pin = config.BUZZER_PIN

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.OUT)
            GPIO.output(self._pin, GPIO.LOW)

            logger.info("Active buzzer initialized (GPIO %d)", self._pin)
        except ImportError:
            logger.info("Buzzer stubbed (RPi.GPIO not available)")
            self._gpio = None
        except (RuntimeError, PermissionError, OSError) as e:
            logger.warning("Buzzer stubbed (GPIO error: %s)", e)
            self._gpio = None

    # ── Low-level helper ────────────────────────────────────────────

    def _on(self):
        """Turn buzzer on immediately (GPIO HIGH)."""
        if self._gpio and self._pin is not None:
            self._gpio.output(self._pin, self._gpio.HIGH)

    def _off(self):
        """Turn buzzer off immediately (GPIO LOW)."""
        if self._gpio and self._pin is not None:
            self._gpio.output(self._pin, self._gpio.LOW)

    async def _chirp(self, on_ms: int, off_ms: int, count: int):
        """Play a chirp pattern: beep *count* times with *on_ms/off_ms* spacing.

        Args:
            on_ms: Duration of each beep in milliseconds.
            off_ms: Silence between beeps in milliseconds.
            count:  Number of beeps to play.
        """
        for i in range(count):
            self._on()
            await asyncio.sleep(on_ms / 1000.0)
            self._off()
            if i < count - 1:
                await asyncio.sleep(off_ms / 1000.0)

    async def _cleanup_on_exit(self):
        """Ensure the buzzer is off when the driver is shut down."""
        self._off()

    # ── Chime patterns ──────────────────────────────────────────────

    async def chime_notify(self):
        """Notification received — 3 quick chirps (beep beep beep)."""
        logger.info("[buzzer] chime: notification received (3 chirps)")
        await self._chirp(on_ms=80, off_ms=80, count=3)

    async def chime_ack(self):
        """Acknowledged — 1 short chirp."""
        logger.info("[buzzer] chime: ack (1 short chirp)")
        self._on()
        await asyncio.sleep(0.10)
        self._off()

    async def chime_sulk(self):
        """Timed out — 2 slow, sad chirps."""
        logger.info("[buzzer] chime: timeout/sulk (2 slow chirps)")
        await self._chirp(on_ms=200, off_ms=300, count=2)

    async def chime_escalate_2(self, stop_event: asyncio.Event = None):
        """Level 2 escalation — 5 rapid urgent chirps.

        If *stop_event* is provided, repeats the chirp pattern continuously
        in a loop (with a short pause between bursts) until the event is
        set. Without it, plays once.
        """
        if stop_event:
            logger.info("[buzzer] chime: escalation level 2 (continuous)")
            while not stop_event.is_set():
                await self._chirp(on_ms=50, off_ms=50, count=5)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
        else:
            logger.info("[buzzer] chime: escalation level 2 (5 rapid chirps)")
            await self._chirp(on_ms=50, off_ms=50, count=5)
