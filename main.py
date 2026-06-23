"""
Mochisuki — notification daemon for Raspberry Pi Zero 2 W.

Single-threaded async event loop. Subscribes to Hermes notifications
via MQTT, drives OLED display / LEDs / buzzer / proximity sensor.
"""

import asyncio
import json
import logging
import signal
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Optional

import config
from buzzer import AsyncBuzzer
from display import AsyncDisplay
from proximity import AsyncProximity
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
        self._last_notification_time: Optional[float] = None
        self._last_idle_refresh: float = 0.0
        # Escalation level guard (set once per level transition, never retriggered on same tick)
        self._escalation_level: int = 0

        # Flash task — continuous blink during escalation
        self._flash_task: Optional[asyncio.Task] = None

        # Subsystems
        self.db = ProductionLogger(config.DB_PATH)
        self.display = AsyncDisplay()
        self.leds = AsyncLEDs()
        self.buzzer = AsyncBuzzer()
        self.proximity = AsyncProximity(threshold_mm=config.WAVE_THRESHOLD_MM)

    # ── Flash task helpers ───────────────────────────────────────────

    def _cancel_flash(self):
        """Cancel the current continuous-flash task, if any."""
        if self._flash_task is not None and not self._flash_task.done():
            self._flash_task.cancel()
            self._flash_task = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def run(self):
        """Boot all subsystems and enter the main event loop."""
        logger.info("Mochisuki engine starting — state=IDLE")

        await self.proximity.init()
        await self.leds.init()
        await self.buzzer.init()
        await self.display.init()
        await self._transition_to_idle()

        # Network listeners run as concurrent tasks
        mqtt_task = asyncio.create_task(self.start_mqtt_client())
        # webhook_task = asyncio.create_task(self.start_webhook_server())  # TODO: phase 2
        # ⚠ When phase 2 is enabled, the handler MUST validate
        #    Authorization: Bearer {config.WEBHOOK_SECRET} before processing.

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

                # Poll proximity for wave-to-dismiss in alerting state
                if self.state is AppState.ALERTING and await self.proximity.is_wave():
                    await self._dismiss_alert()

                if self.state is AppState.ALERTING:
                    await self._evaluate_escalations()

                # Refresh idle display every ~2s for sleep animation
                if self.state is AppState.IDLE:
                    now_t = time.monotonic()
                    if now_t - self._last_idle_refresh >= 2.0:
                        self._last_idle_refresh = now_t
                        await self.display.show_idle(
                            connected=self.hermes_connected,
                            last_notification_time=self._last_notification_time,
                        )

                # Sleep to yield CPU — shorter in alerting, longer in idle
                sleep_s = 0.05 if self.state is AppState.ALERTING else 0.25
                done, _ = await asyncio.wait(
                    pending,
                    timeout=sleep_s,
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
            # Validate before ack — only ack payloads that can be processed
            if not isinstance(payload, dict) or "id" not in payload:
                logger.warning("MQTT: payload missing 'id' or not a dict — dropped")
                return
            self._mqtt_queue.append(payload)
            self._mqtt_wake.set()
            # Publish ack from this thread (paho's publish is thread-safe)
            ack = {
                "id": payload["id"],
                "status": "received",
                "device": "mochisuki-v1",
                "timestamp": time.time(),
            }
            _client.publish(config.MQTT_TOPIC_ACK, json.dumps(ack))
            logger.info("MQTT ack published to %s for %s",
                         config.MQTT_TOPIC_ACK, payload["id"])

        def _on_disconnect(_client, _userdata, rc, _props=None):
            """paho callback — connection dropped (runs in network thread)."""
            self.hermes_connected = False
            if rc != 0:
                logger.warning("MQTT disconnected (rc=%d) — will auto-reconnect", rc)
            else:
                logger.info("MQTT clean disconnect")

        def _on_connect(_client, _userdata, _flags, rc, _props=None):
            """paho callback — (re)connected (runs in network thread)."""
            self.hermes_connected = True
            logger.info("MQTT (re)connected (rc=%d)", rc)

        while not self._shutdown_event.is_set():
            try:
                import paho.mqtt.client as mqtt

                logger.info("Connecting to MQTT broker at %s:%s",
                            config.MQTT_BROKER, config.MQTT_PORT)
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id=config.MQTT_CLIENT_ID)
                c.on_message = _on_message
                c.on_connect = _on_connect
                c.on_disconnect = _on_disconnect
                c.reconnect_delay_set(min_delay=1, max_delay=30)
                # Optional broker authentication
                if config.MQTT_USERNAME and config.MQTT_PASSWORD:
                    c.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
                if config.MQTT_TLS:
                    c.tls_set()
                c.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
                c.subscribe(config.MQTT_TOPIC_SUB)
                c.loop_start()
                self.hermes_connected = True
                logger.info("MQTT connected — subscribed to %s", config.MQTT_TOPIC_SUB)
                # Refresh idle display to show connection status
                if self.state is AppState.IDLE:
                    await self.display.show_idle(connected=True,
                                                 last_notification_time=self._last_notification_time)

                await self._shutdown_event.wait()

                c.loop_stop()
                c.disconnect()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.hermes_connected = False
                if self.state is AppState.IDLE:
                    await self.display.show_idle(connected=False,
                                                 last_notification_time=self._last_notification_time)
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
        if len(payload["id"]) > 64:
            logger.warning(
                "Notification 'id' too long (%d chars, max 64) — dropped",
                len(payload["id"]),
            )
            return

        urgency = payload.get("urgency", "low")
        if urgency not in URGENCY_ORDER:
            logger.warning(
                "Unknown urgency '%s' — will be treated as 'low'. "
                "Expected one of: %s",
                urgency, list(URGENCY_ORDER),
            )

        logger.info(
            "Notification enqueued: %s [%s] <%s>",
            payload.get("title", "(no title)"),
            urgency,
            payload.get("source", "unknown"),
        )
        self._last_notification_time = time.time()
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
        """Only upgrade urgency, never downgrade.

        Strictly-greater (``>``) means equal urgencies do NOT replace —
        the first notification keeps its escalation timer and display slot.
        """
        if not self.current_notification:
            return True
        new_urgency = URGENCY_ORDER.get(payload.get("urgency", "low"), 1)
        cur_urgency = URGENCY_ORDER.get(
            self.current_notification.get("urgency", "low"), 1
        )
        return new_urgency > cur_urgency

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
        await self.proximity.enable()

        await self.display.show_alert(self.current_notification)

        self._cancel_flash()
        await self.leds.set_urgency(self.current_notification["urgency"])
        await self.buzzer.chime_notify()
        self.db.log_received(self.current_notification)

    async def _transition_to_idle(self):
        """Return to idle — silence everything, show always-on face."""
        self.state = AppState.IDLE
        self._escalation_level = 0
        self._cancel_flash()
        logger.info("→ IDLE")
        await self.proximity.disable()
        await self.leds.off()
        await self.display.show_idle(connected=self.hermes_connected,
                                         last_notification_time=self._last_notification_time)
        self.current_notification = None

    # ── Escalation ────────────────────────────────────────────────────

    async def _evaluate_escalations(self):
        """Check elapsed alert time and escalate or time out.

        Each escalation branch fires exactly once — ``_escalation_level``
        gates re-entry so hardware is not retriggered on every 50 ms tick.
        """
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

        elif elapsed > config.ESCALATION_2_SEC and self._escalation_level < 2:
            self._escalation_level = 2
            logger.debug("Escalation level 2 (%ds)", int(elapsed))
            self._cancel_flash()
            stop = asyncio.Event()
            self._flash_task = asyncio.create_task(
                self.leds.flash_continuous(
                    self.current_notification["urgency"], speed="fast", stop_event=stop,
                )
            )
            await self.buzzer.chime_escalate_2()

        elif elapsed > config.ESCALATION_1_SEC and self._escalation_level < 1:
            self._escalation_level = 1
            logger.debug("Escalation level 1 (%ds)", int(elapsed))
            stop = asyncio.Event()
            self._flash_task = asyncio.create_task(
                self.leds.flash_continuous(
                    self.current_notification["urgency"], speed="slow", stop_event=stop,
                )
            )

    # ── Wave Dismiss ──────────────────────────────────────────────────

    async def _dismiss_alert(self):
        """Wave detected — dismiss the current notification."""
        elapsed = int(time.time() - self.alert_start_time)
        logger.info("Wave detected — dismiss")
        self.db.log_action(self.current_notification["id"], "dismiss", elapsed)
        await self.display.show_ack()
        await self.leds.flash_ack()
        await self.buzzer.chime_ack()
        await self._transition_to_idle()


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
