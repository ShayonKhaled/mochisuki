import asyncio
import logging

logger = logging.getLogger("mochisuki.buzzer")


class AsyncBuzzer:
    """Passive piezo buzzer driver — stubbed for dev."""

    async def init(self):
        logger.info("Buzzer initialized (PWM pin 13)")

    async def chime_notify(self):
        logger.info("[buzzer] chime: notification received (2-note ascending)")

    async def chime_ack(self):
        logger.info("[buzzer] chime: ack (short confirmation)")

    async def chime_sulk(self):
        logger.info("[buzzer] chime: timeout/sulk (descending)")

    async def chime_escalate_2(self):
        logger.info("[buzzer] chime: escalation level 2 (intense)")
