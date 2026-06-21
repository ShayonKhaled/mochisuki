"""Hermes → Mochisuki notification client.

  import from hermes.notify import HermesNotifier
  notifier = HermesNotifier("localhost")
  notifier.ping("hello")

Also works as a CLI:
  python notify.py --broker 10.0.0.50 --title "Deploy done" --urgency high
"""

import json
import time
import uuid
import argparse
import logging
import sys
from typing import Optional

logger = logging.getLogger("hermes.notify")

# ── Protocol constants (keep in sync with Mochisuki config.py) ──────────

TOPIC_NOTIFY = "hermes/notify"
TOPIC_ACK = "hermes/ack"
URGENCY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class HermesNotifier:
    """Publish notifications to a Mochisuki device via MQTT.

    Usage::

        notifier = HermesNotifier("10.0.0.50")
        notifier.send(title="Build failed", urgency="high")
        notifier.ping("hello")  # quick test
    """

    def __init__(self, broker_host: str = "localhost", port: int = 1883,
                 source: str = "hermes", client_id: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 tls: bool = False):
        self.broker_host = broker_host
        self.port = port
        self.source = source
        self.client_id = client_id or f"hermes-{uuid.uuid4().hex[:8]}"
        self.username = username
        self.password = password
        self.tls = tls
        self._client = None

    # ── Public API ────────────────────────────────────────────────────

    def send(self, title: str, body: str = "", category: str = "general",
             urgency: str = "low", notify_id: Optional[str] = None) -> dict:
        """Publish a notification and return the payload that was sent.

        Args:
            title: Short headline (shown on OLED display).
            body: Detail text (optional).
            category: Grouping label — ``ci``, ``alert``, ``system``, etc.
            urgency: ``low`` | ``medium`` | ``high`` | ``critical``.
            notify_id: Unique id; auto-generated if omitted.
        """
        payload = {
            "id": notify_id or uuid.uuid4().hex[:12],
            "title": title,
            "body": body,
            "category": category,
            "urgency": urgency,
            "source": self.source,
        }
        self._connect()
        self._client.publish(TOPIC_NOTIFY, json.dumps(payload))
        logger.info("Published %s [%s]", payload["title"], payload["urgency"])
        return payload

    def ping(self, label: str = "ping") -> dict:
        """Send a low-urgency test notification. Returns the payload."""
        return self.send(title=f"Hermes {label}", body="Test ping",
                         category="test", urgency="low")

    def send_critical(self, title: str, body: str = "") -> dict:
        """Shorthand for a critical-urgency notification."""
        return self.send(title=title, body=body, urgency="critical")

    # ── Internal ──────────────────────────────────────────────────────

    def _connect(self):
        if self._client is not None:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("paho-mqtt not installed. Run: pip install paho-mqtt",
                  file=sys.stderr)
            sys.exit(1)
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        if self.username and self.password:
            self._client.username_pw_set(self.username, self.password)
        if self.tls:
            self._client.tls_set()
        self._client.connect(self.broker_host, self.port)
        self._client.loop_start()  # background network thread

    def close(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None


# ── CLI ──────────────────────────────────────────────────────────────────

def _cli():
    p = argparse.ArgumentParser(description="Hermes → Mochisuki notifier")
    p.add_argument("--broker", default="localhost", help="MQTT broker host")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--source", default="hermes-cli")
    p.add_argument("--title", default="", help="Notification headline")
    p.add_argument("--body", default="", help="Detail text")
    p.add_argument("--urgency", default="low",
                   choices=["low", "medium", "high", "critical"])
    p.add_argument("--category", default="general")
    p.add_argument("--ping", action="store_true", help="Send a quick test ping")
    p.add_argument("--username", default=None, help="MQTT broker username")
    p.add_argument("--password", default=None, help="MQTT broker password")
    p.add_argument("--tls", action="store_true", help="Enable TLS for broker connection")
    args = p.parse_args()

    if not args.ping and not args.title:
        p.error("--title is required unless --ping is set")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s",
                        datefmt="%H:%M:%S")

    notifier = HermesNotifier(args.broker, args.port, source=args.source,
                               username=args.username, password=args.password,
                               tls=args.tls)

    if args.ping:
        notifier.ping("cli-test")
    else:
        notifier.send(title=args.title, body=args.body,
                      urgency=args.urgency, category=args.category)
    notifier.close()


if __name__ == "__main__":
    _cli()
