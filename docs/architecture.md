# Architecture

## Overview

Mochisuki runs a single-threaded `asyncio` event loop. All I/O — MQTT, hardware drivers, timers — is non-blocking. The design avoids threads and locks entirely.

```
  ┌──────────────┐   MQTT (hermes/notify)    ┌──────────────────┐
  │ Hermes Agent │ ──────────────────────────▶│  MochisukiEngine │
  │ (or any MQTT │                            │  (main.py)       │
  │   publisher) │◀───────────────────────────│                   │
  └──────────────┘  MQTT (hermes/ack)         │  ┌─────────────┐ │
                                              │  │ asyncio.Queue│ │
  ┌──────────────┐   Gesture (I2C)           │  └─────────────┘ │
  │ PAJ7620U2    │◀─────────────────────────▶│  ┌─────────────┐ │
  │              │                            │  │ StateMachine│ │
  └──────────────┘                            │  │ IDLE        │ │
                                              │  │ ALERTING    │ │
  ┌──────────────┐   SPI                      │  └─────────────┘ │
  │ E-Ink Display│◀──────────────────────────│  │  ┌─────────┐ │
  └──────────────┘                            │  │  │ Timers  │ │
                                              │  │  └─────────┘ │
  ┌──────────────┐   GPIO 18 (PWM)            └──┴───────────────┘
  │ NeoPixels    │◀──────────────────────────
  └──────────────┘                               ┌────────────────┐
                                                 │ ProductionLog  │
  ┌──────────────┐   GPIO 13 (PWM)              │ (personality.py│
  │ Piezo Buzzer │◀──────────────────────────    │  SQLite + WAL) │
  └──────────────┘                               └────────────────┘
```

## State machine

```
┌──────────────────────────────────────────┐
│               IDLE                        │
│  • Display: sleeping face                 │
│  • LEDs: off                              │
│  • Gesture: disabled                      │
│  • Buzzer: silent                         │
└──────────┬───────────────────────────────┘
           │ notification received
           ▼
┌──────────────────────────────────────────┐
│              ALERTING                     │
│  • Display: notification info            │
│  • LEDs: urgency color, pulsing          │
│  • Gesture: enabled (LEFT/RIGHT/DOWN)    │
│  • Buzzer: initial chime                 │
│                                           │
│  Escalation timeline:                     │
│    0s       ─ chime + display            │
│    120s     ─ LED pulse (slow)           │
│    300s     ─ intense chime + fast pulse │
│    600s     ─ timeout → return to IDLE   │
└──────┬────────────────┬─────────────────┘
       │                │
       │ gesture        │ timeout
       │ (dismiss)      │ (600s)
       ▼                ▼
    ┌──────┐       ┌──────┐
    │ IDLE │       │ IDLE │
    │      │       │      │
    └──────┘       └──────┘
```

**Gesture map (alerting state only):**

| Gesture | Action |
|---|---|
| LEFT swipe | Dismiss notification |
| RIGHT swipe | Snooze 10 min |
| DOWN swipe | Snooze 60 min |

## MQTT flow

1. **Subscribe:** `hermes/notify` — any publisher can push a JSON payload.
2. **Validate:** checks for `id` field, enqueues only valid notifications.
3. **Prioritize:** higher-urgency notifications replace lower ones; no downgrades.
4. **Ack:** publishes to `hermes/ack` with status `"received"` and timestamp.
5. **Log:** writes to SQLite via `ProductionLogger`.

## Escalation

Escalation timers run only while in `ALERTING` state. They're evaluated on every tick of the main loop (20 Hz). Three thresholds:

| Threshold | Config | Effect |
|---|---|---|
| Level 1 | `ESCALATION_1_SEC` (120s) | LEDs pulse slowly |
| Level 2 | `ESCALATION_2_SEC` (300s) | Fast LED pulse + intense buzzer |
| Timeout | `ESCALATION_MAX_SEC` (600s) | Silent return to IDLE |

## Persistence

`ProductionLogger` writes to `data/events.db` using SQLite with WAL journal mode and `synchronous=NORMAL` — optimised for flash storage longevity. Each notification receives an `events` row; dismiss/snooze/ignore actions update that row with the response time.
