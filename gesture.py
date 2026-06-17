import asyncio
import logging

logger = logging.getLogger("mochisuki.gesture")


class AsyncGesture:
    """PAJ7620U2 gesture sensor driver — I2C with bus fault isolation."""

    def __init__(self):
        self.address = 0x73
        self._enabled = False
        self.bus = None

    async def init(self):
        try:
            from smbus2 import SMBus
            self.bus = SMBus(1)
            logger.info("Gesture sensor initialized on I2C bus 1 @ 0x73")
            # TODO: Write PAJ7620 initialization register sequence here
        except ImportError:
            logger.warning("smbus2 not available — gesture sensor stubbed")
        except OSError as e:
            logger.error("I2C bus error on gesture init: %s", e)
            self.bus = None

    async def enable(self):
        self._enabled = True
        logger.debug("Gesture polling enabled")

    async def disable(self):
        self._enabled = False
        logger.debug("Gesture polling disabled")

    async def read(self) -> int:
        if not self._enabled or not self.bus:
            return 0
        try:
            reg_data = self.bus.read_byte_data(self.address, 0x43)
            return reg_data & 0x0F
        except OSError:
            logger.warning("I2C bus collision on gesture read — recovering")
            return 0
