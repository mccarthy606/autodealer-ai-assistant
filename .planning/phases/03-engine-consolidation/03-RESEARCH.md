# Phase 3: Engine Consolidation - Research

**Researched:** 2026-03-27
**Domain:** Conversation engine hardening, state machine verification, multilingual support, message deduplication
**Confidence:** HIGH

## Summary

Phase 3 is a hardening phase, not a feature-building phase. The conversation engine already exists as a single unified module (`conversation_engine.py`, ~514 lines) after the Phase 1 merge of the old orchestrator. The work here is: (1) verify all 6+1 states and 7 intents work correctly with comprehensive test coverage, (2) ensure language stickiness so conversations do not mix Spanish/English, (3) add wamid-based deduplication for WhatsApp messages, and (4) create the Alembic migration for the new `wamid` column.

The codebase is straightforward Python 3.12 + FastAPI + SQLAlchemy 2.0 async with PostgreSQL JSONB for conversation state. Tests use SQLite in-memory via aiosqlite with pytest-asyncio (mode: auto). There are currently 10 engine integration tests and 22 intent/entity unit tests. The engine is deterministic (rule-based intent + entity extraction), with optional LLM rephrasing behind a feature flag.

**Primary recommendation:** Focus on test-driven verification of existing engine behavior, add the wamid dedup at the webhook layer, and fix the language switching logic which currently has a subtle bug (only switches es->en, never en->es).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** conversation_engine.py is already the single engine (Phase 1 merged it). This phase verifies correctness and fixes any gaps found during testing.
- **D-02:** All routes (webhook_cloud.py, debug_routes.py, admin test chat) must use `process_message()` from conversation_engine.
- **D-03:** Verify all 6 states (NEW, BROWSING, PRESENTING, DETAILS, CLOSING, HANDOFF) + NOTIFY_WAIT work correctly with proper transitions.
- **D-04:** Add comprehensive test coverage for edge cases: state transitions that were previously only in orchestrator, conversation recovery after errors.
- **D-05:** Language detection already works (entities.py `detect_language()`). Ensure bot responds in correct language consistently -- no mixing Spanish/English within a conversation.
- **D-06:** Language sticky: once detected, keep using that language unless customer switches.
- **D-07:** Add `wamid` (WhatsApp message ID) column to Message model. Unique constraint per conversation.
- **D-08:** In webhook_cloud.py, check for existing wamid before calling process_message(). If duplicate, return `{"status": "ok", "message": "duplicate"}` without processing.
- **D-09:** New Alembic migration for wamid column.

### Claude's Discretion
- Test strategy: expand existing test_engine.py with new test cases for edge cases
- Language detection improvements if needed
- Error handling in state transitions

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-01 | Unified engine for all channels | Already done in Phase 1. Verified: all 3 routes (webhook_cloud, debug_routes, admin_dashboard) use `process_message()`. Tests should confirm this works across channels. |
| ENG-02 | State machine correctly handles all intents | Engine has all 7 intents wired (SEARCH_CAR, ASK_PHOTOS, ASK_DETAILS, VISIT, FINANCING, TRADE_IN, HUMAN) plus GREETING, ASK_PRICE, ASK_KM, ASK_STATUS, NOTIFY, OTHER. States are NEW/BROWSING/PRESENTING/DETAILS/CLOSING/HANDOFF/NOTIFY_WAIT. Need comprehensive transition tests. |
| ENG-03 | Multilingual responses (es-AR / en) with auto-detection | `detect_language()` exists. Language stored in `state["language"]`. Current switching logic has a bug -- see Pitfall 1. Responder already has all templates in both languages. |
| ENG-04 | Message deduplication by wamid | Not yet implemented. Requires: (1) wamid column on Message model, (2) unique index on (conversation_id, wamid), (3) wamid extraction from webhook payload, (4) dedup check before engine call. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Stack locked:** Python 3.12 + FastAPI + SQLAlchemy 2.0 -- do not change
- **Naming:** snake_case.py for modules, test_<module>.py for tests
- **Imports:** explicit named imports, from `src.xxx` paths
- **Error handling:** broad `except Exception` with logging, graceful fallback
- **Logging:** use `%s` formatting, not f-strings
- **Type annotations:** all function params and return types annotated
- **Docstrings:** triple-quoted on every .py file and all public functions
- **Tests:** pytest with asyncio_mode=auto, SQLite in-memory via aiosqlite
- **GSD workflow:** do not make direct repo edits outside a GSD workflow

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.25 | ORM + async sessions + migrations model | Already in use for all data access |
| Alembic | >=1.13.0 | Database migration for wamid column | Already used for schema changes |
| pytest | >=7.4.0 | Test runner | Already configured |
| pytest-asyncio | >=0.23.0 | Async test support | Already configured with mode=auto |
| aiosqlite | >=0.19.0 | SQLite async for tests | Already in test fixtures |

### No New Dependencies
This phase requires zero new packages. All work uses existing libraries.

## Architecture Patterns

### Existing Project Structure (Relevant Files)
```
src/
  services/
    conversation_engine.py  # THE engine -- process_message() entry point
    intent.py               # Rule-based intent detection (13 intents)
    entities.py             # Entity extraction + detect_language()
    responder.py            # Multilingual response templates
    handoff_rules.py        # Handoff condition checking
  db/
    models.py               # SQLAlchemy models (add wamid to Message)
  api/
    routes/
      webhook_cloud.py      # WhatsApp webhook (add dedup here)
      debug_routes.py       # Debug endpoint (already uses process_message)
  adapters/
    whatsapp_cloud.py       # Parse incoming payload (extract wamid here)
alembic/
  versions/
    003_add_wamid_column.py # NEW migration
tests/
  conftest.py               # Fixtures: db_session, dealership, sample_car
  test_engine.py            # 10 integration tests (expand)
  test_intent_entities.py   # 22 unit tests (keep as-is)
```

### Pattern 1: Deduplication via Unique Index
**What:** Add nullable `wamid` column to Message model with a partial unique index on `(conversation_id, wamid) WHERE wamid IS NOT NULL`. Check existence before calling process_message.
**When to use:** WhatsApp channel only. Other channels (admin_test, web) do not have wamid.
**Example:**
```python
# In models.py -- Message model
wamid = Column(String(128), nullable=True)

__table_args__ = (
    Index("ix_msg_conv_wamid", "conversation_id", "wamid",
          unique=True, postgresql_where=text("wamid IS NOT NULL")),
)
```

```python
# In webhook_cloud.py -- before process_message
from sqlalchemy import select, exists
from src.db.models import Message

wamid = _extract_wamid(payload)
if wamid:
    dup = await db.execute(
        select(exists().where(Message.wamid == wamid))
    )
    if dup.scalar():
        return {"status": "ok", "message": "duplicate"}
```

### Pattern 2: wamid Extraction from Webhook Payload
**What:** WhatsApp Cloud API webhook payloads include a message `id` field (the wamid) at `entry[0].changes[0].value.messages[0].id`. Format: `wamid.xxxx...`.
**Example:**
```python
# In whatsapp_cloud.py -- modify parse_incoming_message
# Currently returns (phone, text), change to return (phone, text, wamid)
msg = messages[0]
phone = msg.get("from", "")
wamid = msg.get("id")  # e.g. "wamid.HBgNNTQ5..."
```

### Pattern 3: Language Stickiness Fix
**What:** Current language logic (lines 111-118 of conversation_engine.py) only switches from es to en, never back. Fix: switch language when user clearly writes in a different language.
**Example:**
```python
# Current (buggy):
if not lang:
    lang = detected_lang
elif detected_lang != "es" and lang.startswith("es"):
    lang = detected_lang
# Problem: if lang="en" and user writes Spanish, lang stays "en"

# Fixed:
if not lang:
    lang = detected_lang
elif detected_lang != lang.split("-")[0]:
    # User switched language
    lang = detected_lang
```

### Pattern 4: State Transition Test Pattern
**What:** Multi-step tests that verify state machine transitions by sending sequential messages.
**Example:**
```python
@pytest.mark.asyncio
async def test_full_flow_new_to_handoff(db_session, dealership, sample_car):
    phone = "+5491100099999"
    # Step 1: Greeting -> BROWSING
    r1 = await process_message(db_session, dealership.id, phone, "Hola!", "whatsapp")
    assert r1.stage == "BROWSING"

    # Step 2: Search -> PRESENTING
    r2 = await process_message(db_session, dealership.id, phone, "Tienen Hilux?", "whatsapp")
    assert r2.stage == "PRESENTING"

    # Step 3: Visit -> HANDOFF
    r3 = await process_message(db_session, dealership.id, phone, "Quiero pasar manana", "whatsapp")
    assert r3.stage == "HANDOFF"
    assert r3.mode == "manager"
```

### Anti-Patterns to Avoid
- **Testing language in isolation:** Language detection tests exist in test_intent_entities.py, but the stickiness behavior lives in the engine. Must test language across sequential messages in the engine.
- **Dedup at engine level:** Dedup must happen at the webhook route level, BEFORE calling process_message. Putting it in the engine would break admin_test and debug channels.
- **Non-nullable wamid:** The column MUST be nullable. Only WhatsApp messages have wamids. Admin test, web, and debug channels do not.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dedup storage | In-memory set or Redis cache | Database unique index on wamid | Survives restarts, single source of truth, no TTL management |
| Language detection | ML-based classifier | Existing `detect_language()` heuristic | Already works well for es/en binary case, no new deps |
| State machine framework | FSM library (transitions, etc.) | Existing if/elif chain in process_message | Engine is small (~500 lines), adding a framework is over-engineering |

## Common Pitfalls

### Pitfall 1: Language Switching Only Works One Way
**What goes wrong:** Current code (lines 111-118) allows switching from Spanish to English but NOT from English back to Spanish. If a customer starts in English then switches to Spanish, the bot continues in English.
**Why it happens:** The condition `detected_lang != "es" and lang.startswith("es")` only triggers when current is Spanish and detected is non-Spanish.
**How to avoid:** Replace with symmetric switching: if detected language differs from stored language, update it.
**Warning signs:** Tests pass for es->en but fail for en->es switching.

### Pitfall 2: SQLite Partial Index Not Supported in Tests
**What goes wrong:** PostgreSQL partial unique index (`WHERE wamid IS NOT NULL`) is not supported by SQLite. Tests will fail on table creation.
**Why it happens:** SQLite has limited partial index support compared to PostgreSQL.
**How to avoid:** Use a conditional table_args approach or make the test conftest handle the difference. Alternative: use a regular unique index but make sure to handle NULL correctly (SQLite allows multiple NULLs in unique index by default, which is the desired behavior). Actually, SQLite does support partial indexes via `CREATE INDEX ... WHERE ...`, so this should work. Verify with a test.
**Warning signs:** `OperationalError` during `Base.metadata.create_all` in tests.

### Pitfall 3: parse_incoming_message Signature Change Breaks Callers
**What goes wrong:** Changing `parse_incoming_message` to return `(phone, text, wamid)` instead of `(phone, text)` breaks the unpacking in webhook_cloud.py.
**Why it happens:** Tuple unpacking `phone, text = parsed` fails with 3 values.
**How to avoid:** Update all callers simultaneously. There is only one caller: `webhook_cloud.py` line 49. But also check if any tests mock this function.

### Pitfall 4: WhatsApp Sends Status Updates That Look Like Messages
**What goes wrong:** WhatsApp Cloud API sends `statuses` (delivered, read) alongside `messages`. The webhook receives both. Status updates have no `messages` array, just `statuses`.
**Why it happens:** Meta bundles status updates in the same webhook.
**How to avoid:** `parse_incoming_message` already handles this correctly by checking `if not messages: return None`. No action needed.

### Pitfall 5: Duplicate Messages Arrive Within Milliseconds
**What goes wrong:** WhatsApp can retry webhook delivery very quickly if the first response is slow (>5s). Two identical messages may be processing concurrently.
**Why it happens:** WhatsApp retries on timeout, and FastAPI handles requests concurrently.
**How to avoid:** The unique index on wamid handles this at the database level. The dedup check + unique constraint together provide both fast-path rejection and race-condition safety. If the check passes but a concurrent request inserts first, the unique constraint will raise IntegrityError -- catch it and return duplicate response.

## Code Examples

### wamid Column Addition (models.py)
```python
# In Message class
wamid = Column(String(128), nullable=True, index=False)

# Table args with partial unique index
__table_args__ = (
    Index(
        "ix_msg_conv_wamid",
        "conversation_id",
        "wamid",
        unique=True,
        postgresql_where=sa.text("wamid IS NOT NULL"),
    ),
)
```

### Alembic Migration (003)
```python
"""Add wamid column to messages for deduplication.

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"

def upgrade() -> None:
    op.add_column("messages", sa.Column("wamid", sa.String(128), nullable=True))
    op.create_index(
        "ix_msg_conv_wamid",
        "messages",
        ["conversation_id", "wamid"],
        unique=True,
        postgresql_where=sa.text("wamid IS NOT NULL"),
    )

def downgrade() -> None:
    op.drop_index("ix_msg_conv_wamid", table_name="messages")
    op.drop_column("messages", "wamid")
```

### Updated parse_incoming_message
```python
def parse_incoming_message(payload: dict) -> Optional[tuple[str, str, Optional[str]]]:
    """Parse incoming Meta WhatsApp Cloud webhook payload.
    Returns (phone, text, wamid) or None.
    """
    # ... existing code ...
    msg = messages[0]
    phone = msg.get("from", "")
    wamid = msg.get("id")  # WhatsApp message ID
    # ... text extraction ...
    if phone and text:
        return phone, text, wamid
    return None
```

### Dedup Check in webhook_cloud.py
```python
parsed = parse_incoming_message(payload)
if not parsed:
    return {"status": "ok", "message": "no actionable message"}

phone, text, wamid = parsed
if not text.strip():
    return {"status": "ok"}

# Dedup check (D-08)
if wamid:
    from sqlalchemy import select, exists
    from src.db.models import Message
    dup_exists = await db.execute(
        select(exists().where(Message.wamid == wamid))
    )
    if dup_exists.scalar():
        return {"status": "ok", "message": "duplicate"}
```

### Engine wamid Pass-Through
```python
# In process_message, accept optional wamid parameter
async def process_message(
    session: AsyncSession,
    dealership_id: int,
    phone: str,
    text: str,
    channel: str = "whatsapp",
    wamid: Optional[str] = None,  # NEW
) -> EngineResult:
    # ... when creating inbound Message ...
    msg_in = Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.inbound,
        text=text,
        channel=channel,
        wamid=wamid,  # Save wamid
    )
```

### Comprehensive State Transition Tests
```python
@pytest.mark.asyncio
async def test_state_new_to_browsing_on_greeting(db_session, dealership):
    r = await process_message(db_session, dealership.id, "+test01", "Hola!", "admin_test")
    assert r.stage == "BROWSING"
    assert r.intent == "GREETING"

@pytest.mark.asyncio
async def test_language_sticky_es_stays_es(db_session, dealership, sample_car):
    phone = "+test_lang_01"
    r1 = await process_message(db_session, dealership.id, phone, "Hola, tienen Toyota?", "admin_test")
    assert r1.language == "es"
    r2 = await process_message(db_session, dealership.id, phone, "Mandame fotos", "admin_test")
    assert r2.language == "es"

@pytest.mark.asyncio
async def test_language_switches_en_to_es(db_session, dealership, sample_car):
    phone = "+test_lang_02"
    r1 = await process_message(db_session, dealership.id, phone, "Hi, do you have a Toyota?", "admin_test")
    assert r1.language == "en"
    r2 = await process_message(db_session, dealership.id, phone, "Quiero ver las fotos por favor", "admin_test")
    assert r2.language == "es"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Two engines (orchestrator + conversation_engine) | Single conversation_engine.py | Phase 1 (2026-03) | ENG-01 already satisfied structurally |
| No dedup | wamid-based unique index | Phase 3 (this phase) | Prevents double-processing of WhatsApp retries |
| Language detected per-message, no stickiness | Language sticky with switch detection | Phase 3 (this phase) | Consistent conversation language |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.4.0 + pytest-asyncio >=0.23.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/test_engine.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENG-01 | All routes use process_message() | integration | `python -m pytest tests/test_engine.py -x` | Partial (10 tests exist, need channel variety) |
| ENG-02 | All 7 intents trigger correct state transitions | integration | `python -m pytest tests/test_engine.py -x` | Partial (covers 6/7 intents, missing NOTIFY) |
| ENG-02 | All 6+1 states reachable and correct | integration | `python -m pytest tests/test_engine.py -x` | Partial (missing NOTIFY_WAIT, DETAILS explicit) |
| ENG-03 | Language detection + stickiness | integration | `python -m pytest tests/test_engine.py::test_language -x` | Partial (1 test for English, no stickiness tests) |
| ENG-03 | Language switch es->en and en->es | integration | `python -m pytest tests/test_engine.py -x` | Missing |
| ENG-04 | Duplicate wamid silently dropped | integration | `python -m pytest tests/test_webhook_dedup.py -x` | Missing (new file) |
| ENG-04 | wamid saved to Message model | unit | `python -m pytest tests/test_engine.py -x` | Missing |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_engine.py tests/test_intent_entities.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_engine.py` -- add 10-15 new test cases for: state transitions (all 6+1 states), language stickiness (es->en, en->es), NOTIFY intent, NOTIFY_WAIT state, wamid pass-through, error recovery
- [ ] `tests/test_webhook_dedup.py` -- new file for dedup integration tests (webhook-level, with wamid check)
- [ ] No framework gaps -- pytest + aiosqlite infrastructure already works

## Open Questions

1. **SQLite partial index compatibility**
   - What we know: PostgreSQL partial indexes use `WHERE` clause. SQLite supports partial indexes since 3.8.0.
   - What's unclear: Whether SQLAlchemy's `postgresql_where` kwarg on Index is silently ignored by SQLite or causes an error.
   - Recommendation: Test with SQLite first. If it fails, use a plain unique index (SQLite allows multiple NULLs in unique indexes by default) or conditionally define table_args. Alternatively, skip `postgresql_where` and rely on SQLite's NULL handling (multiple NULLs allowed in UNIQUE by default in SQLite but NOT in PostgreSQL). May need to use a composite approach: partial index for PostgreSQL, plain behavior for SQLite tests.

2. **Concurrent dedup race condition**
   - What we know: Two identical webhook deliveries can arrive within milliseconds.
   - What's unclear: Whether the SELECT-then-INSERT pattern is sufficient or if we need INSERT ... ON CONFLICT.
   - Recommendation: Belt-and-suspenders approach: do SELECT check first (fast reject), wrap Message insert in try/except IntegrityError for the race condition case. The unique index is the true guard.

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all 8 source files listed in phase context
- Existing test suite (32 tests across 2 files)
- Alembic migration history (2 existing migrations, pattern established)
- CLAUDE.md project conventions

### Secondary (MEDIUM confidence)
- WhatsApp Cloud API webhook payload format (msg.id = wamid) -- verified from adapter code structure and Meta documentation knowledge

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing
- Architecture: HIGH - direct code inspection of all files, clear patterns
- Pitfalls: HIGH - identified from actual bugs in source code (language switching logic)
- Dedup pattern: HIGH - standard database unique index approach

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain, no external dependency changes)
