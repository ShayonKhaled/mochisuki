# API Reference

## MQTT

### Subscribe: `hermes/notify`

Any MQTT client can publish a notification to this topic.

**Payload schema:**

```json
{
  "id":       "string",   // required — unique notification id
  "title":    "string",   // optional — short headline (shown on OLED)
  "body":     "string",   // optional — detail text
  "category": "string",   // optional — grouping category, default "general"
  "urgency":  "string",   // optional — "low" | "medium" | "high" | "critical", default "low"
  "source":   "string"    // optional — publisher identifier
}
```

**Urgency priority order:** `low` (1) < `medium` (2) < `high` (3) < `critical` (4)

A notification can only replace the current one if its urgency is strictly higher than the current urgency. Equal-urgency notifications are silently dropped (the current notification keeps its escalation timer).

**Example:**

```bash
mosquitto_pub -h localhost -t hermes/notify -m '{
  "id": "alert-42",
  "title": "Build failed",
  "body": "Pipeline main#123 — test stage failed",
  "category": "ci",
  "urgency": "high",
  "source": "github-actions"
}'
```

### Publish: `hermes/ack`

Mochisuki publishes an acknowledgement for every valid notification received.

**Payload:**

```json
{
  "id":        "string",   // echoed from the notification
  "status":    "received",
  "device":    "mochisuki-v1",
  "timestamp": 1717000000.0  // unix epoch seconds
}
```

---

## SQLite event store

Managed by `ProductionLogger` (`personality.py`). Database at `data/events.db`.

**`events` table:**

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | UUID or unique string |
| `notification_id` | TEXT | Echoed from notification payload |
| `category` | TEXT | `general`, `ci`, `alert`, etc. |
| `urgency` | TEXT | `low` / `medium` / `high` / `critical` |
| `received_at` | TIMESTAMP | Auto-set on insert |
| `action` | TEXT | `received` → `dismiss` / `snoozed` / `ignored` |
| `response_time_sec` | INTEGER | Seconds from alert to action (nullable) |

**Query recent events:**

```bash
sqlite3 data/events.db "SELECT * FROM events ORDER BY received_at DESC LIMIT 10;"
```

---

## Webhook (phase 2 — coming soon)

A `microdot` HTTP server will listen on port 5000, accepting POST to `/webhook/notify` with a bearer-token secret. Same payload schema as MQTT. Not yet wired in the engine.
