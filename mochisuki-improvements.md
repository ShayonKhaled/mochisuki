# Mochisuki — Code Review & Handoff Document

---

## Summary

| Critical | High | Medium | Low / Info | Ideas |
|----------|------|--------|------------|-------|
| 2 | 5 | 5 | 4 | 2 |

Overall the architecture is solid: the async event loop design, stub-graceful hardware drivers, WAL-mode SQLite for SD card longevity, and the thread-safe MQTT deque pattern are all good choices. The proximity debounce logic in `is_wave()` with the `_wave_pending` flag is particularly well thought out.

**Severity guide:**
- **Critical** — active security exposure or data loss risk
- **High** — likely to cause incorrect behaviour or hardware damage in production
- **Medium** — functional bug or usability issue that will surface under normal use
- **Low / Info** — minor inconsistency, dead code, or documentation mismatch
- **Idea** — optional enhancement worth considering

---

## Security & Vulnerabilities

### [Critical] No TLS or authentication on the MQTT broker

**Location:** `config.py`, `hermes/README.md`, `docs/deployment.md`

The README explicitly documents *No TLS by default* with QoS 0. Anyone on the same Tailscale tailnet can publish arbitrary payloads to `hermes/notify` — spamming critical alerts, filling the SQLite DB, or probing for future webhook injection paths.

**Fix:**
- Enable Mosquitto TLS: `listener 8883` with a self-signed cert and `require_certificate true`
- At minimum, add a `password_file` even without TLS
- Add `MQTT_TLS`, `MQTT_USERNAME`, `MQTT_PASSWORD` environment variables to `config.py`

---

### [Critical] Webhook secret is declared but never validated

**Location:** `config.py:23`, `docs/api.md`

`WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")` is set in `config.py` but the `microdot` server is commented out with a `# TODO: phase 2`. When it ships, there is no bearer-token validation middleware wired up anywhere. If someone uncomments the task and deploys, any POST to `/webhook/notify` will be accepted without challenge.

**Fix:**
- Write an `@app.before_request` hook that checks `Authorization: Bearer {WEBHOOK_SECRET}` *before* enabling the microdot server
- Add an integration test that sends a request with a wrong token and asserts a 401 response

---

### [High] No input validation on the user-controlled `id` field

**Location:** `personality.py`, `main.py _enqueue_notification()`

Parameterised queries prevent SQL injection, but there is no length cap, no character whitelist, and no deduplication guard. A malicious publisher can send payloads with a 64 KB `id` string, or send thousands of unique IDs rapidly to fill the SQLite file until the SD card is exhausted.

**Fix:**
- Validate `len(payload["id"]) <= 64` (or enforce a UUID format)
- Add a TTL-based cleanup job in `ProductionLogger` to prune old rows

---

### [High] Ack is published before `id` validation — misleads Hermes

**Location:** `main.py start_mqtt_client()`

The `on_message` paho callback publishes the ack *before* `_enqueue_notification()` validates that `id` exists and that the payload is a dict. A completely invalid payload (e.g. a bare string) still produces an ack with `id: "unknown"`, which can mislead Hermes into thinking a notification was received when it was silently dropped.

**Fix:**
- Move ack publish into `_enqueue_notification()` after the `id` check, or
- Clearly document ack semantics as "broker received, not validated" in `hermes/README.md`

---

## Bugs & Logic Flaws

### [High] Escalation fires every tick — buzzer and LEDs triggered at ~20 Hz

**Location:** `main.py _evaluate_escalations()`

`_evaluate_escalations()` is called on every 50 ms loop tick while in `ALERTING` state. The `elif elapsed > ESCALATION_2_SEC` branch calls `leds.pulse()` and `buzzer.chime_escalate_2()` without any "already escalated" guard. On real hardware this means the buzzer is retriggered ~20 times per second and the LED pulse function runs its full 3-cycle animation on every tick.

**Fix** — add an `_escalation_level` field and gate each branch:

```python
# In __init__:
self._escalation_level: int = 0

# In _evaluate_escalations():
if elapsed > config.ESCALATION_MAX_SEC:
    # ... existing timeout logic

elif elapsed > config.ESCALATION_2_SEC and self._escalation_level < 2:
    self._escalation_level = 2
    logger.debug("Escalation level 2 (%ds)", int(elapsed))
    await self.leds.pulse(self.current_notification["urgency"], speed="fast")
    await self.buzzer.chime_escalate_2()

elif elapsed > config.ESCALATION_1_SEC and self._escalation_level < 1:
    self._escalation_level = 1
    logger.debug("Escalation level 1 (%ds)", int(elapsed))
    await self.leds.pulse(self.current_notification["urgency"], speed="slow")

# In _transition_to_idle():
self._escalation_level = 0
```

---

### [High] `_should_replace` uses `>=` — same-urgency notification always resets the timer

**Location:** `main.py _should_replace()`

The docstring says *"only upgrade urgency, never downgrade"* but `return new_urgency >= cur_urgency` means an incoming `low` notification replaces a currently-displayed `low` one, silently resetting the escalation timer and discarding the first notification.

**Fix:**
- Change to `>` if the intent is strictly "upgrade only"
- If same-urgency notifications should queue rather than replace, that requires a deliberate design decision — document it either way

---

### [Medium] `--ping` CLI flag fails because `--title` is `required=True`

**Location:** `hermes/notify.py _cli()`

Running `python notify.py --ping` (without `--title`) raises an argparse error before the ping fires, making the flag useless as a quick test.

**Fix:**
```python
p.add_argument("--title", default="", help="Notification headline")
# Then in the body:
if not args.ping and not args.title:
    p.error("--title is required unless --ping is set")
```

---

### [Medium] `show_face()` silently ignores its `name` argument

**Location:** `display.py show_face()`

`show_face(self, name: str)` calls `self.show_idle(connected=True)` regardless of which face is requested. `test_display.py` calls `show_face("sleeping")` expecting a sleeping face but always gets the idle animation.

**Fix:** Either wire the `name` parameter to select from `FACES` and render it directly, or remove the parameter to avoid misleading callers.

---

### [Medium] `show_snooze()` is fully implemented but never called

**Location:** `display.py`, `main.py`

`show_snooze()` is a complete, polished display method but there is no snooze state in the engine. It is dead code today.

**Fix:** Either wire it up as part of the snooze-by-wave feature, or remove it until that feature is built to keep the display API honest.

---

### [Medium] `HermesNotifier` uses the deprecated legacy paho `Client()` constructor

**Location:** `hermes/notify.py _connect()`

`main.py` correctly uses `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, ...)` as required for paho-mqtt 2.x. `HermesNotifier._connect()` uses the legacy `mqtt.Client(client_id=self.client_id)` form which emits a deprecation warning in paho 2.x and will break in 3.x.

**Fix:**
```python
self._client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=self.client_id
)
```

---

## Documentation Issues

### [Low] `title` is required in `api.md` but optional in `hermes/README.md`

**Location:** `docs/api.md`, `hermes/README.md`

`hermes/README.md` marks `title` as optional ("string — short headline shown on OLED"). `docs/api.md` marks it `// required — short headline`. The engine only checks for `id`. Pick one definition and make the other match — the inconsistency will confuse integrators.

---

### [Low] Testing doc references `.reasonix/` which is gitignored

**Location:** `docs/testing.md`

The testing doc says *"look at the `test` skill in `.reasonix/`"* but `.reasonix/` is in `.gitignore` and won't be present for anyone cloning the repo.

**Fix:** Remove the reference or describe the testing approach inline until there is an actual test suite committed.

---

### [Low] `aiomqtt` is in `requirements.txt` but not used anywhere

**Location:** `requirements.txt`, `main.py`

`main.py` uses synchronous paho callbacks via a thread-safe deque — `aiomqtt` is not imported anywhere in the application. The `hermes/README.md` async example uses it as an illustration, but it is not a runtime dependency.

**Fix:** Remove `aiomqtt` from `requirements.txt`, or migrate the engine to use it if async MQTT is preferred. Currently it creates a confusing dependency boundary.

---

### [Info] `WAVE_THRESHOLD_MM` is 100 mm in `config.py` but 150 mm in the architecture doc

**Location:** `config.py:31`, `docs/architecture.md`

Minor, but misleading for hardware tuning. The architecture doc says *"object within ~150mm"* while the actual value is 100 mm.

**Fix:** Update `docs/architecture.md` to say 100 mm.

---

## Feature Ideas

### [Idea] Snooze-by-wave: short tap = snooze, long hold = dismiss

**Location:** `proximity.py`, `main.py`

The VL53L1X already returns continuous distance readings, so tracking hold duration costs nothing extra. A short tap (<500 ms within threshold) triggers snooze — the notification re-alerts after N minutes via an `asyncio.sleep` task. A long hold (>500 ms) is a full dismiss. This would activate the already-implemented `show_snooze()` display state and give a natural *"I see it, not now"* affordance with zero additional hardware.

---

### [Idea] Per-source rate limiting to protect against noisy CI pipelines

**Location:** `main.py _enqueue_notification()`

A runaway GitHub Actions workflow could publish hundreds of notifications per minute, saturating the display queue and filling the SQLite DB on the SD card. A simple per-source token bucket (e.g. max 5 notifications per source per 60 seconds) in `_enqueue_notification()` would protect both layers at low implementation cost.

---

## Prioritised Action Checklist

### Before first production deployment

- [ ] Add MQTT authentication (`password_file` at minimum, TLS ideally)
- [ ] Fix escalation level guard in `_evaluate_escalations()` — the 20 Hz buzzer bug
- [ ] Fix `_should_replace()` `>=` vs `>` and document the replacement policy
- [ ] Write webhook bearer-token validation before enabling the microdot server

### Before next minor release

- [ ] Cap and validate `id` field length in `_enqueue_notification()`
- [ ] Move ack publish after `id` validation, or clarify semantics in docs
- [ ] Fix `--ping` CLI flag (`--title` should not be required)
- [ ] Fix `show_face()` to use its `name` argument
- [ ] Update `HermesNotifier._connect()` to use `CallbackAPIVersion.VERSION2`

### Documentation sweep

- [ ] Reconcile `title` field optional/required across `hermes/README.md` and `docs/api.md`
- [ ] Remove `.reasonix/` reference from `docs/testing.md`
- [ ] Remove `aiomqtt` from `requirements.txt` (or migrate to it)
- [ ] Sync `WAVE_THRESHOLD_MM` value in `docs/architecture.md` to 100 mm

---

*Generated from Mochisuki repository review — June 2026*
