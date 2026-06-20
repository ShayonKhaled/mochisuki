"""
Mochisuki — notification daemon for Raspberry Pi Zero 2 W.

Single-threaded async event loop. Subscribes to Hermes notifications
via MQTT, drives OLED display / LEDs / buzzer / gesture sensor.
"""

import asyncio
import json
import logging
import signal
import time
from collections import deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import config
from buzzer import AsyncBuzzer
from display import AsyncDisplay
from gesture import AsyncGesture
from leds import AsyncLEDs
from personality import ProductionLogger

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mochisuki.engine")


# ── State Machine ─────────────────────────────────────────────────────────

class AppState(Enum):
    IDLE = "idle"
    ALERTING = "alerting"


# ── Notification Schema ───────────────────────────────────────────────────

URGENCY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

NOTIFICATION_SCHEMA = {
    "id": str,
    "title": str,
    "body": str,
    "category": str,
    "urgency": str,
    "source": str,
}


# ── Engine ────────────────────────────────────────────────────────────────

class MochisukiEngine:
    """Central async event loop — single-threaded, non-blocking."""

    def __init__(self):
        self.state = AppState.IDLE
        self.current_notification: Optional[dict] = None
        self.alert_start_time: float = 0.0
        self.queue: asyncio.Queue = asyncio.Queue()
        self._shutdown_event = asyncio.Event()
        self._mqtt_queue: deque = deque()  # thread-safe: paho push, async poll
        self._mqtt_wake = asyncio.Event()

        # Hermes / MQTT connection state
        self.hermes_connected: bool = False

        # Subsystems
        self.db = ProductionLogger(config.DB_PATH)
        self.display = AsyncDisplay()
        self.leds = AsyncLEDs()
        self.buzzer = AsyncBuzzer()
        self.gesture = AsyncGesture()

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def run(self):
        """Boot all subsystems and enter the main event loop."""
        logger.info("Mochisuki engine starting — state=IDLE")

        await self.gesture.init()
        await self.leds.init()
        await self.buzzer.init()
        await self.display.init()
        await self._transition_to_idle()

        # Network listeners run as concurrent tasks
        mqtt_task = asyncio.create_task(self.start_mqtt_client())
        # webhook_task = asyncio.create_task(self.start_webhook_server())  # TODO: phase 2

        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        mqtt_wake_task = asyncio.create_task(self._mqtt_wake.wait())

        # ── Main event loop ───────────────────────────────────────────
        pending = {mqtt_task, shutdown_task, mqtt_wake_task}

        try:
            while not self._shutdown_event.is_set():
                # Drain thread-safe MQTT deque onto the async queue
                await self._drain_mqtt()
                # Process inbound notifications from MQTT / webhook
                await self._process_network_queue()

                # Poll gestures in all states (for live display feedback)
                gesture_input = await self.gesture.read()
                if gesture_input != 0:
                    if self.state is AppState.ALERTING:
                        await self._handle_gesture(gesture_input)
                    else:
                        # Live gesture preview — flash and return
                        await self.display.show_gesture(gesture_input)
                        await asyncio.sleep(0.3)
                        await self._transition_to_idle()

                if self.state is AppState.ALERTING:
                    await self._evaluate_escalations()

                # 20 Hz target — give other tasks room to breathe
                done, _ = await asyncio.wait(
                    pending,
                    timeout=0.05,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if mqtt_wake_task in done:
                    self._mqtt_wake.clear()
                    mqtt_wake_task = asyncio.create_task(self._mqtt_wake.wait())
                    pending.add(mqtt_wake_task)
                if shutdown_task in done:
                    break
        finally:
            await self._shutdown()

    async def _shutdown(self):
        """Graceful shutdown: return to idle, cancel tasks, close hardware."""
        logger.info("Shutting down Mochisuki engine...")
        await self._transition_to_idle()
        # Cancel and await remaining background tasks cleanly
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Engine stopped.")

    # ── MQTT Client ───────────────────────────────────────────────────

    async def start_mqtt_client(self):
        """Subscribe to Hermes notifications via paho-mqtt.

        paho's on_message callback runs in a background thread. It pushes
        decoded payloads onto a thread-safe deque + wakes the async loop
        via an Event. The async loop drains the deque in _drain_mqtt.
        """
        def _on_message(_client, _userdata, msg):
            """paho callback — runs in background thread."""
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("MQTT: non-JSON message dropped")
                return
            self._mqtt_queue.append(payload)
            self._mqtt_wake.set()
            # Publish ack from this thread (paho's publish is thread-safe)
            ack = {
                "id": payload.get("id", "unknown"),
                "status": "received",
                "device": "mochisuki-v1",
                "timestamp": time.time(),
            }
            _client.publish(config.MQTT_TOPIC_ACK, json.dumps(ack))
            logger.info("MQTT ack published to %s for %s",
                         config.MQTT_TOPIC_ACK, payload.get("id", "unknown"))

        while not self._shutdown_event.is_set():
            try:
                import paho.mqtt.client as mqtt

                logger.info("Connecting to MQTT broker at %s:%s",
                            config.MQTT_BROKER, config.MQTT_PORT)
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id=config.MQTT_CLIENT_ID)
                c.on_message = _on_message
                c.connect(config.MQTT_BROKER, config.MQTT_PORT)
                c.subscribe(config.MQTT_TOPIC_SUB)
                c.loop_start()
                self.hermes_connected = True
                logger.info("MQTT connected — subscribed to %s", config.MQTT_TOPIC_SUB)
                # Refresh idle display to show connection status
                if self.state is AppState.IDLE:
                    await self.display.show_idle(connected=True)

                await self._shutdown_event.wait()

                c.loop_stop()
                c.disconnect()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.hermes_connected = False
                if self.state is AppState.IDLE:
                    await self.display.show_idle(connected=False)
                if self._shutdown_event.is_set():
                    break
                logger.warning("MQTT disconnected (%s), retrying in 5s...", exc)
                await asyncio.sleep(5)

    async def _drain_mqtt(self):
        """Drain the thread-safe MQTT deque onto the async notification queue."""
        while self._mqtt_queue:
            payload = self._mqtt_queue.popleft()
            await self._enqueue_notification(payload)

    # ── Notification Queue ────────────────────────────────────────────

    async def _enqueue_notification(self, payload: dict):
        """Validate and enqueue an incoming notification."""
        if not isinstance(payload, dict):
            logger.warning("Notification payload is not a dict — dropped")
            return
        if "id" not in payload:
            logger.warning("Notification missing 'id' — dropped")
            return

        logger.info(
            "Notification enqueued: %s [%s] <%s>",
            payload.get("title", "(no title)"),
            payload.get("urgency", "unknown"),
            payload.get("source", "unknown"),
        )
        await self.queue.put(payload)

    async def _process_network_queue(self):
        """Drain the inbound queue — highest-urgency notification wins."""
        while not self.queue.empty():
            payload = await self.queue.get()
            if self._should_replace(payload):
                self.current_notification = payload
                await self._transition_to_alerting()
            else:
                logger.debug(
                    "Notification %s superseded by current %s (urgency too low)",
                    payload.get("id"), self.current_notification.get("id"),
                )
            self.queue.task_done()

    def _should_replace(self, payload: dict) -> bool:
        """Only upgrade urgency, never downgrade."""
        if not self.current_notification:
            return True
        new_urgency = URGENCY_ORDER.get(payload.get("urgency", "low"), 1)
        cur_urgency = URGENCY_ORDER.get(
            self.current_notification.get("urgency", "low"), 1
        )
        return new_urgency >= cur_urgency

    # ── State Transitions ─────────────────────────────────────────────

    async def _transition_to_alerting(self):
        """Enter alerting state — engage sensors, display, LEDs, buzzer."""
        self.state = AppState.ALERTING
        self.alert_start_time = time.time()
        logger.info(
            "→ ALERTING: %s [%s]",
            self.current_notification.get("title"),
            self.current_notification.get("urgency"),
        )
        await self.gesture.enable()

        await self.display.show_alert(self.current_notification)

        await self.leds.set_urgency(self.current_notification["urgency"])
        await self.buzzer.chime_notify()
        self.db.log_received(self.current_notification)

    async def _transition_to_idle(self):
        """Return to idle — silence everything, show always-on face."""
        self.state = AppState.IDLE
        logger.info("→ IDLE")
        await self.gesture.enable()   # keep polling for live gesture feedback
        await self.leds.off()
        await self.display.show_idle(connected=self.hermes_connected)
        self.current_notification = None

    # ── Escalation ────────────────────────────────────────────────────

    async def _evaluate_escalations(self):
        """Check elapsed alert time and escalate or time out."""
        elapsed = time.time() - self.alert_start_time

        if elapsed > config.ESCALATION_MAX_SEC:
            logger.info("Alert timed out after %ds — silencing", int(elapsed))
            self.db.log_action(
                self.current_notification["id"], "ignored", int(elapsed)
            )
            await self.buzzer.chime_sulk()
            await self.display.show_sulk(self.current_notification)
            await asyncio.sleep(3)
            await self._transition_to_idle()

        elif elapsed > config.ESCALATION_2_SEC:
            logger.debug("Escalation level 2 (%ds)", int(elapsed))
            await self.leds.pulse(self.current_notification["urgency"], speed="fast")
            await self.buzzer.chime_escalate_2()

        elif elapsed > config.ESCALATION_1_SEC:
            logger.debug("Escalation level 1 (%ds)", int(elapsed))
            await self.leds.pulse(self.current_notification["urgency"], speed="slow")

    # ── Gesture Handling ──────────────────────────────────────────────

    async def _handle_gesture(self, action: int):
        """Map gesture codes to dismiss / snooze actions."""
        elapsed = int(time.time() - self.alert_start_time)

        # Quick gesture flash
        await self.display.show_gesture(action)
        await asyncio.sleep(0.3)

        if action == 3:  # LEFT → Dismiss
            logger.info("Gesture: LEFT → dismiss")
            self.db.log_action(self.current_notification["id"], "dismiss", elapsed)
            await self.leds.flash_ack()
            await self.buzzer.chime_ack()
            await self._transition_to_idle()

        elif action == 4:  # RIGHT → Short snooze
            logger.info("Gesture: RIGHT → short snooze (%ds)", config.SNOOZE_SHORT_SEC)
            await self._apply_snooze(config.SNOOZE_SHORT_SEC)

        elif action == 2:  # DOWN → Long snooze
            logger.info("Gesture: DOWN → long snooze (%ds)", config.SNOOZE_LONG_SEC)
            await self._apply_snooze(config.SNOOZE_LONG_SEC)

        else:
            logger.debug("Gesture: unknown code %d — ignored", action)

    async def _apply_snooze(self, seconds: int):
        """Snooze: show snooze screen, then idle + deferred wakeup."""
        payload = self.current_notification
        resume_dt = datetime.now() + timedelta(seconds=seconds)
        resume_time = resume_dt.strftime("%H:%M")
        await self.display.show_snooze(seconds, resume_time)
        await asyncio.sleep(2)
        await self._transition_to_idle()
        asyncio.create_task(self._deferred_alert_wakeup(seconds, payload))

    async def _deferred_alert_wakeup(self, delay: int, payload: dict):
        """Re-enqueue a notification after snooze delay."""
        await asyncio.sleep(delay)
        logger.info("Snooze expired — re-alerting")
        await self._enqueue_notification(payload)


# ── Entry Point ───────────────────────────────────────────────────────────

def main():
    engine = MochisukiEngine()

    # Wire up graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal_handler():
        logger.info("Signal received — shutting down...")
        engine._shutdown_event.set()

    loop.add_signal_handler(signal.SIGINT, _signal_handler)
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    try:
        loop.run_until_complete(engine.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
