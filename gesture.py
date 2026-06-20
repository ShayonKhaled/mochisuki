"""
APDS-9960 gesture sensor driver — I2C.

Gesture direction codes returned by read():
    1 = UP, 2 = DOWN, 3 = LEFT, 4 = RIGHT

Degrades gracefully on ImportError (no smbus2) or I2C bus errors.
"""

import asyncio
import logging
import time

logger = logging.getLogger("mochisuki.gesture")

# ── 7-bit I2C address ──────────────────────────────────────────────────
_APDS_ADDR = 0x39

# ── Register map ────────────────────────────────────────────────────────
_ENABLE   = 0x80
_ATIME    = 0x81
_WTIME    = 0x83
_PERS     = 0x8C
_CONFIG1  = 0x8D
_PPULSE   = 0x8E
_CONTROL  = 0x8F
_CONFIG2  = 0x90
_ID       = 0x92
_STATUS   = 0x93
_PDATA    = 0x9C
_CONFIG3  = 0x9F
_GCONF1   = 0xA0
_GCONF2   = 0xA1
_GPULSE   = 0xA6
_GCONF3   = 0xAA
_GCONF4   = 0xAB
_GFLVL    = 0xAE
_GSTATUS  = 0xAF
_GFIFO_U  = 0xFC
_GFIFO_D  = 0xFD
_GFIFO_L  = 0xFE
_GFIFO_R  = 0xFF

# ── Bit masks / constants ──────────────────────────────────────────────
_PON       = 0x01
_PEN       = 0x04
_GENS      = 0x40
_GVALID    = 0x01        # Bit 0 in GSTATUS (varies by chip revision — 0x01 on this one)
_GMODE     = 0x01        # Bit 0 in GCONF4
_DEVICE_ID = 0xAB        # APDS-9960 ID register value

_GESTURE_CODES = {0: 1, 1: 2, 2: 3, 3: 4}  # index → UP/DOWN/LEFT/RIGHT

# Gesture detection thresholds
_MIN_TOTAL = 150              # Minimum cumulative signal (L/R only, so lower)
_DOMINANCE_RATIO = 1.25       # Leading direction must beat runner-up by ≥25%


class AsyncGesture:
    """APDS-9960 gesture sensor driver — I2C with bus fault isolation."""

    def __init__(self):
        self.address = _APDS_ADDR
        self._enabled = False
        self.bus = None
        self._last_error_at: float = 0.0
        self._error_count: int = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    async def init(self):
        """Initialise the APDS-9960: power on, configure gesture engine."""
        try:
            from smbus2 import SMBus
            self.bus = SMBus(1)

            # Verify device ID (warn on mismatch, but continue — some clones use different IDs)
            dev_id = self.bus.read_byte_data(self.address, _ID)
            if dev_id != _DEVICE_ID:
                logger.warning(
                    "Gesture sensor ID mismatch: got 0x%02X, expected 0x%02X — "
                    "continuing with APDS-9960-compatible init",
                    dev_id, _DEVICE_ID,
                )

            # Power on
            self._write(_ENABLE, _PON)
            await asyncio.sleep(0.01)

            # ALS integration: max duration (minimises ALS noise)
            self._write(_ATIME, 0xFF)

            # Enable proximity + gesture engines
            self._write(_ENABLE, _PON | _PEN | _GENS)  # 0x45
            await asyncio.sleep(0.01)

            # Proximity pulses (reduced — IR LED is strong)
            self._write(_PPULSE, 0x08)   # 9 pulses (was 255, was saturating)

            # Proximity gain: 1x (was defaulting to 16x/64x, causing saturation at 255)
            self._write(_CONTROL, 0x00)  # PGAIN=1x, AGAIN=1x

            # Gesture config (reduced gain — IR LED is strong)
            self._write(_GCONF1, 0x10)   # GEXTH=1, GFIFOTH=0
            self._write(_GCONF2, 0x01)   # gain=2x, LED=100mA, both diodes
            self._write(_GPULSE, 0x9F)   # 16µs pulse length, 32 pulses (was 10)
            self._write(_GCONF3, 0x02)   # L/R only — U/D zeroed out (UP bias was drowning RIGHT)

            # Enter gesture mode
            self._write(_GCONF4, _GMODE)

            logger.info(
                "APDS-9960 initialised on I2C bus 1 @ 0x%02X",
                _APDS_ADDR,
            )

        except ImportError:
            logger.info("Gesture sensor stubbed (smbus2 not available)")
            self.bus = None
        except OSError as exc:
            logger.error("I2C bus error on gesture init: %s", exc)
            self.bus = None

    # ── I/O helpers ──────────────────────────────────────────────────

    def _write(self, reg: int, value: int):
        """Single-byte register write."""
        if self.bus:
            self.bus.write_byte_data(self.address, reg, value)

    def _read(self, reg: int) -> int:
        """Single-byte register read."""
        return self.bus.read_byte_data(self.address, reg) if self.bus else 0

    # ── Enable / Disable polling ─────────────────────────────────────

    async def enable(self):
        """Activate gesture polling."""
        self._enabled = True
        self._error_count = 0
        logger.debug("Gesture polling enabled")

    async def disable(self):
        """Deactivate gesture polling."""
        self._enabled = False
        logger.debug("Gesture polling disabled")

    # ── Gesture detection ────────────────────────────────────────────

    async def read(self) -> int:
        """Poll sensor, return a gesture code or 0.

        Returns:
            0  — no gesture detected
            1  — UP swipe
            2  — DOWN swipe
            3  — LEFT swipe
            4  — RIGHT swipe
        """
        if not self._enabled or not self.bus:
            return 0

        try:
            # Check if gesture FIFO has data
            status = self._read(_GSTATUS)
            if not (status & _GVALID):
                return 0

            # How many entries are in the FIFO?
            levels = self._read(_GFLVL)
            if levels == 0 or levels > 32:
                return 0

            # Drain FIFO: read first ~5 entries (plenty for direction, way faster than 32)
            totals = [0, 0, 0, 0]
            n = min(levels, 5)
            for _ in range(n):
                totals[0] += self._read(_GFIFO_U)
                totals[1] += self._read(_GFIFO_D)
                totals[2] += self._read(_GFIFO_L)
                totals[3] += self._read(_GFIFO_R)

            sorted_vals = sorted(totals, reverse=True)
            max_total = sorted_vals[0]
            second_total = sorted_vals[1]

            ratio = max_total / second_total if second_total > 0 else 99
            if max_total < _MIN_TOTAL or ratio < _DOMINANCE_RATIO:
                return 0

            best_idx = totals.index(max_total)
            code = _GESTURE_CODES[best_idx]

            self._error_count = 0  # reset on success
            logger.debug(
                "Gesture: %s (idx=%d, ratio=%.2f, totals=%s, levels=%d)",
                {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT"}.get(code, "?"),
                best_idx, ratio, totals, levels,
            )
            return code

        except OSError:
            # Rate-limited I2C error logging
            now = time.monotonic()
            self._error_count += 1
            if now - self._last_error_at >= 1.0:
                if self._error_count > 1:
                    logger.warning(
                        "I2C bus error on gesture read (%d errors in last second)",
                        self._error_count,
                    )
                else:
                    logger.warning("I2C bus error on gesture read — recovering")
                self._last_error_at = now
                self._error_count = 0
            return 0
