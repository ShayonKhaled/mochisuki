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
_GENS      = 0x40
_GVALID    = 0x04        # Bit 2 in GSTATUS
_GMODE     = 0x01        # Bit 0 in GCONF4
_DEVICE_ID = 0xAB        # APDS-9960 ID register value

_GESTURE_CODES = {0: 1, 1: 2, 2: 3, 3: 4}  # index → UP/DOWN/LEFT/RIGHT

# Gesture detection: minimum cumulative FIFO signal to report a direction
_MIN_GESTURE_TOTAL = 30

# How many consecutive noise samples silence gesture detection
_SILENCE_AFTER_READS = 3


class AsyncGesture:
    """APDS-9960 gesture sensor driver — I2C with bus fault isolation."""

    def __init__(self):
        self.address = _APDS_ADDR
        self._enabled = False
        self.bus = None
        self._last_error_at: float = 0.0
        self._error_count: int = 0
        self._silence_count: int = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    async def init(self):
        """Initialise the APDS-9960: power on, configure gesture engine."""
        try:
            from smbus2 import SMBus
            self.bus = SMBus(1)

            # Verify device ID
            dev_id = self.bus.read_byte_data(self.address, _ID)
            if dev_id != _DEVICE_ID:
                logger.warning(
                    "APDS-9960 ID mismatch: got 0x%02X, expected 0x%02X",
                    dev_id, _DEVICE_ID,
                )
                self.bus = None
                return

            # Power on
            self._write(_ENABLE, _PON)
            await asyncio.sleep(0.01)

            # ALS integration: max duration (minimises ALS noise)
            self._write(_ATIME, 0xFF)

            # Enable gesture engine
            self._write(_ENABLE, _PON | _GENS)  # 0x41
            await asyncio.sleep(0.01)

            # Gesture config
            self._write(_GCONF1, 0x60)   # GEXTH=6, GFIFOTH=0
            self._write(_GCONF2, 0x01)   # gain=2x, LED=100mA, both diodes
            self._write(_GPULSE, 0x89)   # 16µs pulse length, 10 pulses
            self._write(_GCONF3, 0x00)   # 2D dimension (all axes)

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
        self._silence_count = 0
        logger.debug("Gesture polling enabled")

    async def disable(self):
        """Deactivate gesture polling."""
        self._enabled = False
        self._silence_count = 0
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

            # Drain the FIFO: accumulate per-direction totals
            totals = [0, 0, 0, 0]  # U, D, L, R
            count = 0

            for _ in range(min(levels, 32)):
                u = self._read(_GFIFO_U)
                d = self._read(_GFIFO_D)
                l = self._read(_GFIFO_L)
                r = self._read(_GFIFO_R)

                totals[0] += u
                totals[1] += d
                totals[2] += l
                totals[3] += r
                count += 1

            # If the readings are all tiny, it's noise — silence briefly
            max_total = max(totals)
            if max_total < _MIN_GESTURE_TOTAL:
                self._silence_count += 1
                if self._silence_count >= _SILENCE_AFTER_READS:
                    logger.debug("Gesture: noise floor — silenced")
                return 0

            self._silence_count = 0
            best_idx = totals.index(max_total)
            code = _GESTURE_CODES[best_idx]

            self._error_count = 0  # reset on success
            logger.debug(
                "Gesture: %s (idx=%d, totals=%s, levels=%d)",
                {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT"}.get(code, "?"),
                best_idx, totals, levels,
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
