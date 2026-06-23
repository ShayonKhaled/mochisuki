"""
VL53L1X Time-of-Flight proximity sensor driver — I2C.

Returns distance in mm. "Wave" = object detected within WAVE_THRESHOLD_MM
while enabled, with a debounce cooldown to prevent retriggering.

Degrades gracefully on ImportError (no vl53l1x package) or I2C bus errors.
"""

import asyncio
import logging
import time

logger = logging.getLogger("mochisuki.proximity")

# ── 7-bit I2C address ──────────────────────────────────────────────────
_I2C_ADDR = 0x29

# ── Ranging mode constants ──────────────────────────────────────────────
_MODE_SHORT = 1   # Up to ~1.3m, better ambient immunity
_MODE_MEDIUM = 2  # Up to ~3m
_MODE_LONG = 3    # Up to ~4m


class AsyncProximity:
    """VL53L1X ToF distance sensor — async wrapper.

    Polls distance via the vl53l1x library. Provides a simple
    ``is_wave()`` check suitable for "wave to dismiss" UI.
    """

    def __init__(self, threshold_mm: int = 100, mode: int = _MODE_SHORT):
        self.address = _I2C_ADDR
        self.threshold_mm = threshold_mm
        self._mode = mode
        self._enabled = False
        self._sensor = None
        self._last_wave_at: float = 0.0
        self._cooldown = 1.0          # seconds between wave triggers
        self._last_error_at: float = 0.0
        self._error_count: int = 0
        self._wave_pending = False     # near reading seen during cooldown

    # ── Lifecycle ────────────────────────────────────────────────────

    async def init(self):
        """Initialise the VL53L1X: open I2C, start continuous ranging."""
        try:
            import VL53L1X as vl53l1x

            self._sensor = vl53l1x.VL53L1X(
                i2c_bus=1,
                i2c_address=self.address,
            )
            self._sensor.open()
            self._sensor.stop_ranging()   # clear stale state from crashed sessions
            # Ranging started/stopped by enable()/disable()

            logger.info(
                "VL53L1X initialised on I2C bus 1 @ 0x%02X (mode=%d, threshold=%dmm)",
                _I2C_ADDR, self._mode, self.threshold_mm,
            )

        except ImportError:
            logger.info("Proximity sensor stubbed (vl53l1x not available)")
            self._sensor = None
        except OSError as exc:
            logger.error("I2C bus error on proximity init: %s", exc)
            self._sensor = None

    # ── Enable / Disable ─────────────────────────────────────────────

    async def enable(self):
        """Activate proximity polling with startup cooldown."""
        self._enabled = True
        if self._sensor is not None:
            self._sensor.start_ranging(self._mode)
        self._error_count = 0
        self._last_wave_at = time.monotonic()
        self._wave_pending = False
        logger.debug("Proximity polling enabled")

    async def disable(self):
        """Deactivate proximity polling and stop sensor."""
        self._enabled = False
        if self._sensor is not None:
            self._sensor.stop_ranging()
        logger.debug("Proximity polling disabled")

    # ── Reading ──────────────────────────────────────────────────────

    async def read_distance(self) -> int:
        """Poll the sensor and return distance in mm.

        Returns:
            Distance in millimetres (0 = no reading / error).
        """
        if not self._enabled or not self._sensor:
            return 0

        try:
            dist = self._sensor.get_distance()
            self._error_count = 0
            return dist
        except Exception as exc:
            now = time.monotonic()
            self._error_count += 1
            if now - self._last_error_at >= 1.0:
                if self._error_count > 1:
                    logger.warning(
                        "VL53L1X read error (%d errors in last second): %s",
                        self._error_count, exc,
                    )
                else:
                    logger.warning("VL53L1X read error: %s", exc)
                self._last_error_at = now
                self._error_count = 0
            return 0

    async def is_wave(self) -> bool:
        """Check for wave gesture — hand within *threshold_mm* of sensor.

        A wave is any reading where the distance is below *threshold_mm*
        (default 100 mm / 10 cm) and the sensor is not returning an error.

        A 1-second startup cooldown prevents stray first-read noise.
        If a qualifying hand-close occurs during cooldown, it is
        remembered via ``_wave_pending`` and fires immediately when
        the cooldown expires — even if the hand has already moved away.

        Returns:
            True if a hand was detected within threshold distance.
        """
        if not self._enabled:
            return False

        dist = await self.read_distance()
        now = time.monotonic()
        in_cooldown = (now - self._last_wave_at) < self._cooldown

        # Error / glitch readings — skip
        if dist <= 0:
            return False

        # Hand must be within threshold distance
        if dist > self.threshold_mm:
            return False

        # Hand is near!  If still in startup cooldown, remember and wait
        if in_cooldown:
            self._wave_pending = True
            return False

        # Cooldown expired — fire any pending wave first
        if self._wave_pending:
            self._wave_pending = False
            self._last_wave_at = now
            logger.info("Wave detected (pending)")
            return True

        # Fresh wave after cooldown
        self._last_wave_at = now
        logger.info("Wave detected: %d mm", dist)
        return True
