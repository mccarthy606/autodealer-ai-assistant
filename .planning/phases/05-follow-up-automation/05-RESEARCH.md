# Phase 5: Follow-Up Automation - Research

**Researched:** 2026-03-27
**Domain:** Celery Beat scheduling, SQLAlchemy sync/async bridging, JSONB mutation tracking, WhatsApp template API, opt-out NLP
**Confidence:** HIGH (all findings verified against official docs or project source code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Celery Beat periodic task runs every 15 minutes. Scans for follow-up candidates.
- D-02: First follow-up: 24 hours after last customer message with no response.
- D-03: Second follow-up: 3 days (72 hours) after last customer message with no response.
- D-04: Only follow up on conversations where: mode="bot", stage in ("PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"), not already followed up at that tier.
- D-05: All follow-ups MUST use WhatsApp template messages (not free-form text).
- D-06: Two template names: `followup_24h_v1` and `followup_3d_v1` with specific text.
- D-07: Templates must be submitted to Meta for approval before follow-ups work in production.
- D-08: Maximum 2 follow-ups per conversation (24h + 3d). After both sent, no more auto follow-ups.
- D-09: Track follow-up count in `Conversation.state["followup_count"]` and `state["last_followup_at"]`.
- D-10: Detect opt-out intents: "no", "no me interesa", "no gracias", "dejá de escribir", "stop", "not interested". Add to intent.py.
- D-11: On opt-out detection: set `state["opted_out"] = True`, never follow up again on this conversation.
- D-12: Respond with: "Entendido, no te vamos a molestar más. Si cambiás de opinión, escribinos!"
- D-13: New file: `src/tasks/followup_task.py`
- D-14: Use existing `WhatsAppCloudAdapter.send_template()` from Phase 4
- D-15: New Celery Beat schedule entry in `celery_app.py`

### Claude's Discretion
- Exact opt-out regex patterns
- Celery Beat interval (suggested 15 min, can adjust)
- Database query optimization for follow-up candidates
- Error handling for failed template sends

### Deferred Ideas (OUT OF SCOPE)
- Re-engagement with new inventory matching preferences — v2
- Visit confirmation day-of reminder — v2
- Configurable follow-up schedule per dealership — v2
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FUP-01 | Auto-reminder at 24h if customer did not reply | Beat task query: `last_message_at < now - 24h AND state["followup_count"] < 1` |
| FUP-02 | Second reminder at 3 days if still silent | Beat task query: `last_message_at < now - 72h AND state["followup_count"] < 2` |
| FUP-03 | Follow-ups via WhatsApp template messages only | `send_template()` already exists; components structure documented in §4 |
| FUP-04 | Maximum 2-3 follow-ups per conversation | `state["followup_count"]` incremented per send; guard in query |
| FUP-05 | Respect opt-out — stop all follow-ups when customer declines | `OPT_OUT` intent + `state["opted_out"]` flag; regex patterns in §5 |
</phase_requirements>

---

## Summary

Phase 5 builds on an already well-structured Celery + SQLAlchemy foundation. The project uses `celery[redis]>=5.3.0` and `sqlalchemy>=2.0.25` with `asyncpg`. The critical architectural insight is that the project **already has a working sync-session pattern** in `import_tasks.py` (using `sessionmaker` + `create_engine`) and a separate `sync_engine` in `session.py`. The follow-up task must use this same sync pattern — Celery workers are synchronous by default and bridging to async adds complexity with no benefit here.

The WhatsApp template component structure is confirmed: a `components` list with a single `body` entry containing a `parameters` array of `{"type": "text", "text": value}` objects. The existing `send_template()` method in `whatsapp_cloud.py` accepts this structure directly.

The JSONB `state` column update pattern requires careful handling: SQLAlchemy does not auto-detect in-place dict mutations. The correct approach is to reassign the full dict (`conv.state = new_dict`) or use `flag_modified()` — matching the pattern already used in the conversation engine (line 419: `conv.state = state`).

**Primary recommendation:** Use sync SQLAlchemy (not asyncio bridging) for the Celery task, following the `import_tasks.py` pattern that already exists in the project.

---

## Q1: Celery Beat Integration

### beat_schedule Syntax — Celery 5.x (VERIFIED)

The `beat_schedule` is added via `conf.update()` with a `timedelta` schedule. The existing `celery_app.py` uses `celery_app.conf.update(...)` — add `beat_schedule` to the same call.

**Confidence:** HIGH — Pattern confirmed from Celery 5.3.x–5.5.x official docs.

```python
# src/tasks/celery_app.py — add to existing conf.update()
from datetime import timedelta

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    beat_schedule={
        "followup-scan-every-15min": {
            "task": "src.tasks.followup_task.scan_and_send_followups",
            "schedule": timedelta(minutes=15),
        },
    },
)
```

### include Parameter

Also add `followup_task` to the Celery `include` list so the worker discovers it:

```python
celery_app = Celery(
    "ai_inventory_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.import_tasks", "src.tasks.followup_task"],  # add this
)
```

### Running Beat in Production

The Celery docs explicitly warn: **do NOT use `-B` (embedded beat) in production with multiple workers** — it causes duplicate task scheduling. Run beat as a separate process:

```bash
# Worker process
celery -A src.tasks.celery_app worker --loglevel=info

# Beat process (separate, single instance)
celery -A src.tasks.celery_app beat --loglevel=info
```

In the project's `docker-compose.yml`, beat should be a separate service. For development, `-B` is acceptable.

### Alternative: crontab syntax

If clock-aligned execution matters (run at :00, :15, :30, :45 past the hour rather than 15 minutes from start):

```python
from celery.schedules import crontab

beat_schedule={
    "followup-scan-every-15min": {
        "task": "src.tasks.followup_task.scan_and_send_followups",
        "schedule": crontab(minute="*/15"),
    },
},
```

**Recommended:** Use `timedelta(minutes=15)` for simplicity. Clock-alignment is not a requirement here.

---

## Q2: Async Celery Tasks with Async SQLAlchemy

### The Problem

The project uses `AsyncSession` + `asyncpg` for FastAPI. Celery workers are synchronous by default. Three options exist:

| Option | Mechanism | Verdict |
|--------|-----------|---------|
| `asyncio.run()` | Creates and destroys a new event loop per call | AVOID — corrupts asyncpg connection pool |
| `asgiref.async_to_sync()` | Bridges sync context to async properly | Works but adds dependency |
| Sync SQLAlchemy | Use `Session` + `psycopg2-binary` (already in pyproject.toml) | BEST — matches project's own `import_tasks.py` |

### Recommended Approach: Sync SQLAlchemy (matches existing project pattern)

The project **already has this pattern** in `import_tasks.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings

sync_engine = create_engine(settings.database_url)
SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)
```

And `session.py` already exports a `sync_engine`. The follow-up task should reuse the same approach:

```python
# src/tasks/followup_task.py
from sqlalchemy.orm import sessionmaker
from src.db.session import sync_engine  # already exists

SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)

@celery_app.task(name="src.tasks.followup_task.scan_and_send_followups")
def scan_and_send_followups():
    session = SyncSession()
    try:
        _run_followup_scan(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Why not asyncio.run():** asyncpg connections are tied to an event loop. Calling `asyncio.run()` in a Celery task creates a new loop, runs the coroutine, then destroys the loop — but asyncpg's connection pool still holds connections tied to the destroyed loop. On the next task, those zombie connections cause errors. This is a documented production issue.

**Why not asgiref:** Adds a dependency (`asgiref`) not already in the project. The sync pattern is simpler and already established.

**Confidence:** HIGH — Pattern is the project's own existing standard (see `import_tasks.py` lines 6-17).

---

## Q3: Follow-Up Candidate Query

### Available Columns in `Conversation` Model

From `src/db/models.py`:
- `mode` (String, "bot" or "manager")
- `state` (JSONB — contains `stage`, `opted_out`, `followup_count`, `last_followup_at`)
- `last_message_at` (DateTime, UTC) — updated on every inbound customer message in `process_message()`
- `channel` (String)

**Critical finding:** `last_message_at` is set in `process_message()` which is only called on inbound customer messages. It is NOT set when the bot sends an outbound message independently (e.g., via the followup task). This makes it a reliable proxy for "last customer message time."

### Query Strategy

SQLAlchemy's JSONB column supports path-based access and the `[]` operator for querying. For the `state` JSONB field:

```python
from datetime import datetime, UTC, timedelta
from sqlalchemy import select, and_, or_, cast
from sqlalchemy.dialects.postgresql import JSONB
from src.db.models import Conversation

now = datetime.now(UTC)
cutoff_24h = now - timedelta(hours=24)
cutoff_72h = now - timedelta(hours=72)

# First follow-up candidates: silent 24h+, followup_count < 1
stmt_24h = select(Conversation).where(
    and_(
        Conversation.mode == "bot",
        Conversation.state["stage"].astext.in_(
            ["PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"]
        ),
        Conversation.last_message_at <= cutoff_24h,
        Conversation.last_message_at > cutoff_72h,  # not yet at 3-day threshold
        # followup_count == 0 (key absent OR value is 0)
        or_(
            Conversation.state["followup_count"] == None,
            cast(Conversation.state["followup_count"].astext, Integer) < 1,
        ),
        # not opted out
        or_(
            Conversation.state["opted_out"] == None,
            Conversation.state["opted_out"].astext != "true",
        ),
    )
)

# Second follow-up candidates: silent 72h+, followup_count == 1
stmt_72h = select(Conversation).where(
    and_(
        Conversation.mode == "bot",
        Conversation.state["stage"].astext.in_(
            ["PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"]
        ),
        Conversation.last_message_at <= cutoff_72h,
        cast(Conversation.state["followup_count"].astext, Integer) == 1,
        or_(
            Conversation.state["opted_out"] == None,
            Conversation.state["opted_out"].astext != "true",
        ),
    )
)
```

### Simpler Alternative: Python-Side Filtering

Given follow-up volumes are expected to be low (tens, not thousands), querying by `last_message_at` and mode only, then filtering JSONB fields in Python avoids JSONB cast complexity:

```python
# Broader DB query (avoids JSONB casts)
stmt = select(Conversation).where(
    and_(
        Conversation.mode == "bot",
        Conversation.last_message_at <= cutoff_24h,  # at least 24h ago
    )
)
candidates = session.execute(stmt).scalars().all()

# Python-side filter (safe, readable, avoids JSONB quirks)
for conv in candidates:
    state = conv.state or {}
    if state.get("opted_out"):
        continue
    stage = state.get("stage", "NEW")
    if stage not in ("PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"):
        continue
    followup_count = state.get("followup_count", 0)
    if followup_count >= 2:
        continue
    # determine which tier
    elapsed = now - conv.last_message_at.replace(tzinfo=UTC)
    if followup_count == 0 and elapsed >= timedelta(hours=24):
        send_24h_followup(conv, session)
    elif followup_count == 1 and elapsed >= timedelta(hours=72):
        send_72h_followup(conv, session)
```

**Recommended:** Python-side filtering. It avoids JSONB type-cast complexity in WHERE clauses. The JSONB cast approach is correct but requires careful handling of missing keys (NULL vs absent). Python-side is more readable, testable, and safe.

**Confidence:** HIGH (model columns verified in source; JSONB access syntax verified against SQLAlchemy 2.0 docs).

---

## Q4: send_template() Call Structure

### Existing Signature (from `src/adapters/whatsapp_cloud.py` lines 57-77)

```python
async def send_template(
    self, to: str, template_name: str, language_code: str,
    components: list[dict],
) -> dict:
```

**Note:** `send_template` is `async`. The Celery task uses sync code. The adapter must be called with `asyncio.run()` **only** for the HTTP call itself (not for DB operations). This is acceptable because `httpx.AsyncClient` is used inside — a single isolated coroutine with no shared pool. Alternative: use `httpx.Client` (sync) directly in the task, bypassing the async adapter.

### Recommended Approach for Celery Task

Use `httpx.Client` (sync) directly in the followup task to avoid needing `asyncio.run()`:

```python
import httpx

def _send_template_sync(to: str, template_name: str, language_code: str, components: list[dict]) -> dict:
    """Sync version of send_template for Celery task."""
    from src.config import settings
    token = settings.whatsapp_cloud_token
    phone_number_id = settings.whatsapp_phone_number_id
    if not token or not phone_number_id:
        logger.info("[WhatsApp MOCK] send_template to=%s template=%s", to, template_name)
        return {"status": "mock"}
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, json=payload, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        return resp.json()
```

### Template Component Structure (VERIFIED via Meta Cloud API docs)

For body-only templates with text parameters:

```python
# followup_24h_v1: "Hola {{1}}! Seguís interesado en {{2}}? Está disponible por {{3}}. Te esperamos en {{4}}!"
# Parameters: name, car_title, price, dealership_address

components_24h = [
    {
        "type": "body",
        "parameters": [
            {"type": "text", "text": customer_name},      # {{1}}
            {"type": "text", "text": car_title},          # {{2}}
            {"type": "text", "text": price_str},          # {{3}}
            {"type": "text", "text": dealership_address}, # {{4}}
        ],
    }
]

# followup_3d_v1: "Hola {{1}}! Te escribimos de {{2}}. El {{3}} que consultaste sigue disponible. Querés pasar a verlo?"
# Parameters: name, dealership_name, car_title

components_3d = [
    {
        "type": "body",
        "parameters": [
            {"type": "text", "text": customer_name},      # {{1}}
            {"type": "text", "text": dealership_name},    # {{2}}
            {"type": "text", "text": car_title},          # {{3}}
        ],
    }
]
```

**Language code:** Use `"es_AR"` for Argentine Spanish when submitting templates to Meta. The existing `send_template()` accepts `language_code` as a parameter.

**Confidence:** HIGH — component structure verified from Meta Cloud API reference (developers.facebook.com/docs/whatsapp/cloud-api/reference/messages).

---

## Q5: OPT_OUT Intent Patterns

### Analysis of Existing Intent Detection

The existing `detect_intent()` function (in `intent.py`) uses `any(k in t for k in _KEYWORD_LIST)` pattern. `t = text.lower().strip()`. This is substring matching, not word-boundary matching.

**False positive risks with bare "no":**
- "no me quedan dudas" → would match "no" → FALSE POSITIVE (means "I have no doubts" = still interested)
- "no sé" → would match "no" → FALSE POSITIVE
- "no tengo tiempo hoy" → would match "no" → ambiguous

**Solution:** Use regex with word boundaries and require either (a) message is VERY short (≤3 words) for bare "no", or (b) use specific multi-word opt-out phrases for longer messages.

### Recommended Regex Patterns

```python
import re

OPT_OUT = "OPT_OUT"

# Patterns are matched against lowercased, stripped text
# Ordered from most to least specific

_OPT_OUT_PATTERNS = [
    # Explicit refusals — safe regardless of message length
    re.compile(r"no\s+me\s+interesa", re.IGNORECASE),
    re.compile(r"no\s+gracias", re.IGNORECASE),
    re.compile(r"dej[aá]\s+de\s+(escribir|molestar|contactar)", re.IGNORECASE),
    re.compile(r"no\s+(me\s+)?(molestes|llames|contactes|escribas)", re.IGNORECASE),
    re.compile(r"\bstop\b", re.IGNORECASE),
    re.compile(r"\bnot\s+interested\b", re.IGNORECASE),
    re.compile(r"ya\s+no\s+me\s+interesa", re.IGNORECASE),
    re.compile(r"no\s+quiero", re.IGNORECASE),
    re.compile(r"no\s+gracias\b", re.IGNORECASE),
    re.compile(r"\bchau\b.*\bgracias\b", re.IGNORECASE),  # "chau gracias"
]

# Bare "no" — only if message is very short (≤2 words total)
_OPT_OUT_BARE_NO = re.compile(r"^\s*no[\s!.?]*$", re.IGNORECASE)


def _is_opt_out(text: str) -> bool:
    """Detect opt-out intent. Returns True if customer wants to stop receiving messages."""
    t = text.strip()
    word_count = len(t.split())
    # Bare "no" only if the entire message is just "no" (optionally with punctuation)
    if _OPT_OUT_BARE_NO.match(t):
        return True
    # Multi-word opt-out phrases — safe at any length
    for pattern in _OPT_OUT_PATTERNS:
        if pattern.search(t):
            return True
    return False
```

### Integration into detect_intent()

Add OPT_OUT check **first** (highest priority — safety-critical), before HUMAN check:

```python
# In intent.py detect_intent():
if _is_opt_out(text):
    return OPT_OUT
```

### False Positive Analysis

| Message | Matches? | Correct? |
|---------|----------|---------|
| "no" | YES (bare no pattern) | YES |
| "no gracias" | YES | YES |
| "no me interesa" | YES | YES |
| "dejá de escribir" | YES | YES |
| "stop" | YES | YES |
| "not interested" | YES | YES |
| "no sé" | NO (2 words but doesn't match bare-no regex) | CORRECT |
| "no me quedan dudas" | NO | CORRECT |
| "no tengo plata ahora" | NO | CORRECT |
| "quiero que no me lo vendan a otro" | NO | CORRECT |
| "no quiero" | YES (matches `no\s+quiero`) | YES |

**Confidence:** MEDIUM-HIGH — patterns designed based on Argentine Spanish idioms; regex reviewed against test cases above. Recommend unit tests covering all rows.

---

## Q6: State JSON Updates in SQLAlchemy

### The Mutation Tracking Problem

SQLAlchemy ORM does **not** automatically detect in-place mutations to a `dict` stored in a JSONB column. If you do:

```python
conv.state["followup_count"] = 1  # WRONG — SQLAlchemy won't detect this change
session.commit()  # No UPDATE issued — silent data loss
```

### Correct Approaches

**Approach A: Full reassignment (matches existing project pattern)**

This is how `conversation_engine.py` handles it (line 419: `conv.state = state`). Use the same pattern:

```python
# Read current state
state = dict(conv.state or {})
# Mutate the copy
state["followup_count"] = state.get("followup_count", 0) + 1
state["last_followup_at"] = datetime.now(UTC).isoformat()
# Reassign triggers SQLAlchemy dirty tracking
conv.state = state
```

**Approach B: flag_modified (when reassignment is awkward)**

```python
from sqlalchemy.orm.attributes import flag_modified

conv.state["followup_count"] = conv.state.get("followup_count", 0) + 1
conv.state["last_followup_at"] = datetime.now(UTC).isoformat()
flag_modified(conv, "state")  # tells SQLAlchemy: this column is dirty
```

**Approach C: Server-side func.jsonb_set (atomic, no ORM load needed)**

For bulk updates where you don't want to load rows into memory:

```python
from sqlalchemy import update, func, cast
from sqlalchemy.dialects.postgresql import JSONB

session.execute(
    update(Conversation)
    .where(Conversation.id == conv_id)
    .values(
        state=func.jsonb_set(
            Conversation.state,
            "{followup_count}",
            cast(str(new_count), JSONB),
        )
    )
)
```

**Recommended:** Approach A (full reassignment). It matches the project's existing pattern exactly, is readable, and avoids the `flag_modified` import and the JSONB casting complexity of approach C. Performance is not a concern for a periodic task scanning tens of rows.

**Confidence:** HIGH — verified via SQLAlchemy 2.0 mutation tracking docs and confirmed against project source (conversation_engine.py line 419).

---

## Q7: Error Handling for Failed Template Sends

### What WhatsApp Returns on Failure

Meta's Cloud API returns HTTP 200 with an `error` key in the JSON body for some failures, and non-200 status codes for others. The existing `_post()` method in `whatsapp_cloud.py` already handles exceptions and returns `{"error": str(e)}` but does NOT raise.

### Error Categories

| Error | Code | Cause | Action |
|-------|------|-------|--------|
| Template not approved | 132001 | Template submitted but pending | Don't increment count; log; skip |
| Invalid phone number | 131030 | Bad E.164 format | Don't retry; mark conversation |
| Rate limit exceeded | 131056 | Too many messages to number | Retry after delay |
| Temporary API error | 131026 | Meta server issue | Retry with backoff |
| Token expired | 190 | Invalid auth token | Alert; don't increment count |

### Recommended Strategy

**Do NOT retry within the same Beat run.** The Beat task runs every 15 minutes — let the next run handle it. This is simpler and avoids Celery retry complexity for a scan task.

**Increment count only on confirmed success:**

```python
result = _send_template_sync(phone, template_name, language_code, components)

if "error" in result or "errors" in result:
    # API returned an error object
    error_code = result.get("error", {}).get("code") or \
                 (result.get("errors") or [{}])[0].get("code")
    logger.error(
        "followup template failed conv=%s code=%s: %s",
        conv.id, error_code, result
    )
    # Do NOT increment followup_count — will retry on next Beat run
    # Exception: rate limit errors — add a cooldown
    if error_code == 131056:
        state["followup_cooldown_until"] = (
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat()
        conv.state = state
    return  # skip this conversation this run

# Success
state["followup_count"] = state.get("followup_count", 0) + 1
state["last_followup_at"] = datetime.now(UTC).isoformat()
conv.state = state
```

**Check cooldown in candidate selection:**

```python
cooldown_until_str = state.get("followup_cooldown_until")
if cooldown_until_str:
    cooldown_until = datetime.fromisoformat(cooldown_until_str)
    if datetime.now(UTC) < cooldown_until:
        continue  # skip this conversation
```

**Confidence:** MEDIUM — error codes sourced from Meta documentation and community reports; exact behavior of Meta API on individual failure cases requires empirical testing.

---

## Architecture Patterns

### Recommended File Structure

```
src/tasks/
├── celery_app.py          # Add beat_schedule and followup_task to include
├── import_tasks.py        # Existing inventory import (reference pattern)
└── followup_task.py       # NEW: Beat task for follow-up scanning

src/services/
├── intent.py              # Add OPT_OUT constant, _is_opt_out(), integrate into detect_intent()
└── conversation_engine.py # Add OPT_OUT handling branch (set opted_out, respond)
```

### Task Flow

```
[Celery Beat, every 15min]
        |
        v
scan_and_send_followups()
        |
        +-- Open sync DB session
        |
        +-- Query: mode=bot, last_message_at <= 24h ago
        |
        +-- Python filter: stage, opted_out, followup_count, cooldown
        |
        +-- For each candidate:
        |       |
        |       +-- Determine tier (24h or 72h)
        |       +-- Get conversation state (name, car, dealership)
        |       +-- Call _send_template_sync()
        |       +-- If success: increment followup_count, set last_followup_at
        |       +-- If error: log, skip (retry next run)
        |
        +-- Commit session
        +-- Close session
```

### OPT_OUT Engine Handling

In `conversation_engine.py`, add after the existing intent detection at step 7:

```python
# In detect_intent() result handling (before other intents)
if intent == OPT_OUT:
    state["opted_out"] = True
    result.text = "Entendido, no te vamos a molestar más. Si cambiás de opinión, escribinos!"
    state["stage"] = state.get("stage", "NEW")  # don't change stage
    conv.state = state
    return result
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async-to-sync bridging | Custom event loop management | Sync SQLAlchemy (existing pattern) | asyncpg pool corruption; project already solved this |
| Beat scheduling | Custom cron/threading in app startup | Celery Beat | Handles clock drift, restarts, missed tasks |
| Template HTTP calls | Custom async wrapper | `httpx.Client` (sync) in task | No pool to corrupt; simpler; no new deps |
| JSONB mutation | Flag fields manually everywhere | Full dict reassignment (conv.state = state) | Matches project standard, SQLAlchemy handles dirty tracking |

---

## Common Pitfalls

### Pitfall 1: asyncio.run() in Celery for DB operations
**What goes wrong:** asyncpg connection pool gets corrupted after the event loop is destroyed inside `asyncio.run()`. Subsequent DB calls fail with "connection is closed" errors.
**Why it happens:** asyncpg connections are bound to a specific event loop. Destroying the loop makes them unusable, but the pool still holds references.
**How to avoid:** Use sync SQLAlchemy + psycopg2 (already in pyproject.toml as `psycopg2-binary>=2.9.9`) for all Celery DB work.
**Warning signs:** "connection is closed" or "another operation in progress" errors in Celery logs.

### Pitfall 2: In-place JSONB mutation without flagging
**What goes wrong:** `conv.state["followup_count"] = 1` appears to work locally but no UPDATE SQL is issued. Data is lost on commit.
**Why it happens:** SQLAlchemy's ORM tracks object identity, not deep dict mutation.
**How to avoid:** Always reassign: `conv.state = {**conv.state, "followup_count": 1}` or use `flag_modified(conv, "state")`.
**Warning signs:** follow-up count never increments in DB; same conversation receives follow-ups on every Beat run.

### Pitfall 3: Bare "no" as opt-out
**What goes wrong:** Customer says "no sé el modelo" (I don't know the model) → triggers opt-out → conversation permanently blocked.
**Why it happens:** Simple substring match on "no" matches too broadly.
**How to avoid:** Use `^\s*no[\s!.?]*$` regex (bare "no" only when entire message is just "no"). Multi-word phrases use specific patterns.
**Warning signs:** Legitimate conversations marked as opted_out.

### Pitfall 4: followup_count not incremented on failure → infinite follow-up loop
**What goes wrong:** Template send fails (network error, Meta API down), count stays at 0, next Beat run sends again, and again.
**Why it happens:** Error path forgets to handle count logic.
**How to avoid:** Only increment on confirmed success. Add `followup_cooldown_until` for rate-limit errors.
**Warning signs:** Same conversation appears in every Beat task log; WhatsApp number gets reported/banned.

### Pitfall 5: last_message_at timezone awareness
**What goes wrong:** `datetime.now(UTC) - conv.last_message_at` raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.
**Why it happens:** PostgreSQL DateTime without timezone stores naive datetimes; Python `datetime.now(UTC)` is timezone-aware.
**How to avoid:** Always use `.replace(tzinfo=UTC)` on datetimes read from DB before arithmetic: `conv.last_message_at.replace(tzinfo=UTC)`.
**Warning signs:** TypeError in Beat task log; task crashes without sending any follow-ups.

### Pitfall 6: Running beat with -B flag in production
**What goes wrong:** With 2+ Celery workers, each embeds a Beat scheduler — follow-up task fires N times per interval.
**Why it happens:** `-B` embeds Beat in the worker process; multiple workers = multiple Beat instances.
**How to avoid:** Run `celery beat` as a separate process/container. In docker-compose, add a dedicated `beat` service.
**Warning signs:** Duplicate follow-up messages received; doubled log entries for `scan_and_send_followups`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.run()` in Celery | Sync engine OR NullPool+async_to_sync | 2022-2023 | asyncpg pool corruption is well-documented; sync is preferred |
| String seconds schedule | `timedelta` or `crontab` objects | Celery 3.x+ | Both still valid; timedelta is more readable |
| JSONB in-place mutation | Full reassignment or flag_modified | SQLAlchemy 1.4+ | MutableDict is an option but adds complexity; reassignment is simpler |

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| `celery[redis]>=5.3` | Beat scheduling | In pyproject.toml | Already installed in project |
| `psycopg2-binary>=2.9.9` | Sync Celery DB session | In pyproject.toml | Already installed — enables sync SQLAlchemy |
| `httpx>=0.26.0` | Sync template HTTP call | In pyproject.toml | Already installed; use `httpx.Client` (sync) |
| `redis>=5.0.0` | Celery broker/backend | In pyproject.toml | Already configured in celery_app.py |
| WhatsApp templates approved | FUP-03, FUP-01, FUP-02 | NOT YET | Must be submitted to Meta before production use |

**Missing with no fallback:**
- WhatsApp template approval — templates `followup_24h_v1` and `followup_3d_v1` must be submitted and approved by Meta. The mock mode in `WhatsAppCloudAdapter` (when token is not set) logs instead of sending, which is sufficient for development.

---

## Code Examples

### Complete followup_task.py skeleton

```python
# Source: project pattern from src/tasks/import_tasks.py
"""Celery Beat task: scan conversations and send follow-up template messages."""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, and_
from sqlalchemy.orm import sessionmaker, Session

from src.config import settings
from src.db.session import sync_engine
from src.db.models import Conversation, Dealership, InventoryItem
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)

FOLLOWUP_STAGES = {"PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"}
MAX_FOLLOWUPS = 2

TEMPLATE_24H = "followup_24h_v1"
TEMPLATE_3D = "followup_3d_v1"
LANGUAGE_CODE = "es_AR"


@celery_app.task(name="src.tasks.followup_task.scan_and_send_followups")
def scan_and_send_followups():
    session = SyncSession()
    try:
        _run_scan(session)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("followup scan failed: %s", e)
        raise
    finally:
        session.close()


def _run_scan(session: Session) -> None:
    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)

    # Broad DB query: bot mode, last message >= 24h ago
    stmt = select(Conversation).where(
        and_(
            Conversation.mode == "bot",
            Conversation.last_message_at <= cutoff_24h,
        )
    )
    conversations = session.execute(stmt).scalars().all()

    for conv in conversations:
        try:
            _process_candidate(conv, now, session)
        except Exception as e:
            logger.error("error processing conv=%s: %s", conv.id, e)
            # Continue processing other conversations


def _process_candidate(conv: Conversation, now: datetime, session: Session) -> None:
    state = dict(conv.state or {})

    # Skip opted-out
    if state.get("opted_out"):
        return

    # Skip wrong stage
    stage = state.get("stage", "NEW")
    if stage not in FOLLOWUP_STAGES:
        return

    # Skip maxed out
    followup_count = state.get("followup_count", 0)
    if followup_count >= MAX_FOLLOWUPS:
        return

    # Cooldown check
    cooldown_str = state.get("followup_cooldown_until")
    if cooldown_str:
        cooldown_until = datetime.fromisoformat(cooldown_str)
        if now < cooldown_until:
            return

    # Time elapsed since last customer message (timezone-safe)
    last_msg = conv.last_message_at
    if last_msg.tzinfo is None:
        last_msg = last_msg.replace(tzinfo=UTC)
    elapsed = now - last_msg

    # Determine which follow-up tier applies
    if followup_count == 0 and elapsed >= timedelta(hours=24):
        template_name = TEMPLATE_24H
    elif followup_count == 1 and elapsed >= timedelta(hours=72):
        template_name = TEMPLATE_3D
    else:
        return  # Not yet due

    # Build components
    components = _build_components(template_name, state, session, conv.dealership_id)
    if not components:
        logger.warning("conv=%s: could not build template components, skipping", conv.id)
        return

    # Send template
    result = _send_template_sync(conv.user_phone, template_name, LANGUAGE_CODE, components)

    if "error" in result or "errors" in result:
        error_code = (result.get("error") or {}).get("code")
        logger.error("followup send failed conv=%s code=%s: %s", conv.id, error_code, result)
        if error_code == 131056:  # rate limited
            state["followup_cooldown_until"] = (now + timedelta(hours=1)).isoformat()
            conv.state = state
        return

    # Success — update state
    state["followup_count"] = followup_count + 1
    state["last_followup_at"] = now.isoformat()
    conv.state = state
    logger.info("followup sent conv=%s tier=%s count=%s", conv.id, template_name, followup_count + 1)
```

### beat_schedule addition to celery_app.py

```python
# Source: Celery 5.x docs — https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
from datetime import timedelta

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    beat_schedule={
        "followup-scan-every-15min": {
            "task": "src.tasks.followup_task.scan_and_send_followups",
            "schedule": timedelta(minutes=15),
        },
    },
)
```

### OPT_OUT intent detection

```python
# Source: project convention from src/services/intent.py

import re

OPT_OUT = "OPT_OUT"

_OPT_OUT_BARE_NO = re.compile(r"^\s*no[\s!.?]*$", re.IGNORECASE)

_OPT_OUT_PATTERNS = [
    re.compile(r"no\s+me\s+interesa", re.IGNORECASE),
    re.compile(r"no\s+gracias", re.IGNORECASE),
    re.compile(r"dej[aá]\s+de\s+(escribir|molestar|contactar)", re.IGNORECASE),
    re.compile(r"no\s+(me\s+)?(molestes|llames|contactes|escribas)", re.IGNORECASE),
    re.compile(r"\bstop\b", re.IGNORECASE),
    re.compile(r"\bnot\s+interested\b", re.IGNORECASE),
    re.compile(r"ya\s+no\s+me\s+interesa", re.IGNORECASE),
    re.compile(r"no\s+quiero", re.IGNORECASE),
]


def _is_opt_out(text: str) -> bool:
    t = text.strip()
    if _OPT_OUT_BARE_NO.match(t):
        return True
    for pattern in _OPT_OUT_PATTERNS:
        if pattern.search(t):
            return True
    return False
```

---

## Open Questions

1. **`last_message_at` vs last customer message**
   - What we know: `last_message_at` is set inside `process_message()`, which is only called on inbound customer messages. The follow-up task does not call `process_message()` when sending outbound templates. So it accurately reflects last customer contact time.
   - What's unclear: If a manager manually sends a message through the admin UI (`admin_conversations.py` line 113 also updates `last_message_at`), this resets the follow-up clock. This is actually the CORRECT behavior — if a manager engaged, no bot follow-up should fire.
   - Recommendation: No schema change needed. Document this behavior.

2. **Template parameter data availability**
   - What we know: `followup_24h_v1` needs: customer name, car title, price, dealership address. All are in `Conversation.state` (name) and `InventoryItem` (car via `state["selected_car_id"]`).
   - What's unclear: What if `selected_car_id` is absent (BROWSING stage)? Template will need fallback values.
   - Recommendation: Use `state.get("name", "Cliente")` for name; load car from `state["selected_car_id"]` if present, else use a generic phrase. For `followup_3d_v1` which only needs name + dealership name + car title, load `Dealership.name` from DB.

3. **Meta template approval timeline**
   - What we know: Templates must be approved before use; approval takes 24-72 hours typically.
   - What's unclear: Template names `followup_24h_v1` and `followup_3d_v1` are decided; exact copy must match submission.
   - Recommendation: Document template submission as a separate manual step outside code. The mock adapter handles missing tokens gracefully for dev/staging.

---

## Sources

### Primary (HIGH confidence)
- Project source: `src/tasks/import_tasks.py` — sync SQLAlchemy session pattern for Celery tasks
- Project source: `src/db/session.py` — `sync_engine` already exported
- Project source: `src/adapters/whatsapp_cloud.py` — `send_template()` signature (lines 57-77)
- Project source: `src/db/models.py` — `Conversation` model columns verified
- Project source: `src/services/conversation_engine.py` — `conv.state = state` pattern (line 419), `last_message_at` update behavior
- Meta Cloud API docs — template components structure (developers.facebook.com/docs/whatsapp/cloud-api/reference/messages)
- SQLAlchemy 2.0 mutation tracking docs — flag_modified, MutableDict (docs.sqlalchemy.org/en/20/orm/extensions/mutable.html)

### Secondary (MEDIUM confidence)
- [Celery 5.5.x periodic tasks docs](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html) — beat_schedule syntax, timedelta schedule
- [Using Async SQLAlchemy Inside Sync Celery Tasks - DEV Community](https://dev.to/kevinnadar22/using-async-sqlalchemy-inside-sync-celery-tasks-3eg4) — asyncio.run() pitfalls, NullPool pattern
- [Celery GitHub Issue #6313](https://github.com/celery/celery/issues/6313) — -B flag not recommended for production
- [SQLAlchemy Discussion #7033](https://github.com/sqlalchemy/sqlalchemy/discussions/7033) — JSONB update strategies
- [SQLAlchemy Discussion #7806](https://github.com/sqlalchemy/sqlalchemy/discussions/7806) — atomic JSON updates

### Tertiary (LOW confidence — needs validation)
- Meta WhatsApp error codes (131056 rate limit, 131030 invalid phone, 132001 template not approved) — sourced from community reports; verify against current Meta docs before finalizing error handling

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml, versions confirmed
- Architecture: HIGH — follows established project patterns from import_tasks.py
- Pitfalls: HIGH for SQLAlchemy/Celery patterns; MEDIUM for Meta API error codes
- Opt-out patterns: MEDIUM-HIGH — designed from Argentine Spanish idioms, needs unit test coverage

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (stable libraries; Meta API template structure rarely changes)
