# Phase 7: Admin Dashboard & Analytics - Research

**Researched:** 2026-03-27
**Domain:** FastAPI + SQLAlchemy 2.0 async — targeted route and template fixes
**Confidence:** HIGH (all findings from direct source inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Replace `pending_handoffs` stat card with `pending_visits` — Lead where intent=visit AND status in (new, contacted) AND dealership_id==did.
- D-02: Change the query in `dashboard()` — remove mode=="manager" Conversation query, add Lead intent/status query.
- D-03: Update dashboard.html stat card label from "Pending handoffs" to "Pending visits".
- D-04: Replace `convs_today` with `active_conversations` — Conversation where mode="bot" AND dealership_id==did AND last_message_at >= now - 7 days.
- D-05: Update dashboard.html stat card label from "Conversations today" to "Active conversations".
- D-06: Keep `leads_today` as-is on dashboard.
- D-07: Add `avg_response_seconds` to `metrics_page()` route.
- D-08: Python-side computation preferred over complex SQL for response time.
- D-09: No data → display "N/A". Format: seconds if < 60 ("23s"), minutes if >= 60 ("1m 12s"). Pass formatted string to template.
- D-10: Add new stat card to metrics.html alongside existing four cards.
- D-11: Files changed: `src/api/routes/admin_dashboard.py`, `src/templates/admin/dashboard.html`, `src/templates/admin/metrics.html`.
- D-12: No new routes, no new templates, no migrations.
- D-13: Python-side response time computation preferred.
- D-14: Unit tests for dashboard stats queries (mock DB, verify pending_visits logic).
- D-15: Unit test for avg_response_seconds with sample message timestamps.
- D-16: Template rendering not tested — only route logic.

### Claude's Discretion
- Exact SQL vs Python-side implementation for response time (prefer Python-side for simplicity)
- Cutoff for "active" conversations (7 days suggested; can adjust)
- Response time formatting (seconds/minutes display logic)
- Whether to show response time per-day chart or single average (single average is simpler)

### Deferred Ideas (OUT OF SCOPE)
- Date range selector for metrics page — v2
- Per-day chart/graph for leads and conversations — v2
- Export leads to CSV — v2
- Real-time dashboard updates (WebSocket) — v2
- Email digest / weekly report — v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Replace pending_handoffs with pending_visits; replace convs_today with active_conversations on dashboard | Enum values confirmed, query patterns verified from models.py |
| DASH-02 | Add avg_response_seconds to metrics page | Message.created_at and MessageDirectionEnum confirmed; Python-side computation pattern documented |
| DASH-03 | Top brands/models on metrics | Already implemented — no action needed |
| DASH-04 | Conversation history | Already implemented — no action needed |
| DASH-05 | Lead filtering | Already implemented — no action needed |
</phase_requirements>

---

## Summary

This is a narrow, three-gap patch to an existing admin dashboard. All findings come from direct inspection of the live source files — no external research required. The models, enums, and route signatures are fully understood. The only non-trivial design decision is the avg_response_seconds computation, which is documented below with a concrete Python snippet.

**Primary recommendation:** Make the three targeted edits as specified. No architectural decisions are open.

---

## Research Findings by Gap

### Gap 1: Enum and Column Values (DASH-01)

**Confirmed from `src/db/models.py`:**

| Enum | Member | String value |
|------|--------|--------------|
| `LeadIntentEnum` | `visit` | `"visit"` |
| `LeadStatusEnum` | `new` | `"new"` |
| `LeadStatusEnum` | `qualified` | `"qualified"` |
| `LeadStatusEnum` | `handed_off` | `"handed_off"` |
| `LeadStatusEnum` | `closed` | `"closed"` |

**CRITICAL FINDING:** `LeadStatusEnum` does NOT have a `contacted` member. The CONTEXT.md (D-01) references `status in (new, contacted)` but `contacted` does not exist in the codebase. The valid early-stage statuses are `new` and `qualified`. The pending_visits query must use `(LeadStatusEnum.new, LeadStatusEnum.qualified)`.

`Lead.intent` is an `Enum(LeadIntentEnum)` column (line 228).
`Lead.status` is an `Enum(LeadStatusEnum)` column (line 233).
`Lead.dealership_id` is an `Integer` FK column (line 224).
`Lead.created_at` is a `DateTime` column (line 243).

`Conversation.mode` is a plain `String(16)` column (not an Enum column), default `"bot"` (line 172). String comparison `== "bot"` is correct.
`Conversation.last_message_at` is a `DateTime` column (line 174).
`Conversation.dealership_id` is an `Integer` FK column (line 165).

**Pending visits query:**
```python
from src.db.models import Lead, LeadIntentEnum, LeadStatusEnum

r = await db.execute(select(func.count(Lead.id)).where(
    Lead.dealership_id == did,
    Lead.intent == LeadIntentEnum.visit,
    Lead.status.in_([LeadStatusEnum.new, LeadStatusEnum.qualified]),
))
pending_visits = r.scalar() or 0
```

**Active conversations query:**
```python
from datetime import UTC, datetime, timedelta

seven_days_ago = datetime.now(UTC) - timedelta(days=7)

r = await db.execute(select(func.count(Conversation.id)).where(
    Conversation.dealership_id == did,
    Conversation.mode == "bot",
    Conversation.last_message_at >= seven_days_ago,
))
active_conversations = r.scalar() or 0
```

---

### Gap 2: Dashboard Template Variable Mapping

**Confirmed from `src/api/routes/admin_dashboard.py` (lines 151-158) and `src/templates/admin/dashboard.html`:**

| Template variable | Current label in HTML | Stat card line |
|-------------------|-----------------------|----------------|
| `convs_today` | "Conversations today" | Line 12-13 |
| `leads_today` | "Leads today" | Line 15-16 |
| `pending_handoffs` | "Pending handoffs" | Line 19-20 |
| `cars_available` | "Cars available" | Line 22-23 |

**Two stat cards to change:**
1. Variable `convs_today` → rename to `active_conversations` in route dict; label `"Conversations today"` → `"Active conversations"` in template.
2. Variable `pending_handoffs` → rename to `pending_visits` in route dict; label `"Pending handoffs"` → `"Pending visits"` in template.

The `stat-card-warn` CSS class is currently on the `pending_handoffs` card (line 18). It should move to (or stay on) `pending_visits` — logically appropriate.

**Route template_response dict change:**
```python
# Remove:
"convs_today": convs_today,
"pending_handoffs": pending_handoffs,

# Add:
"active_conversations": active_conversations,
"pending_visits": pending_visits,
```

---

### Gap 3: avg_response_seconds (DASH-02)

**Message model confirmed from `src/db/models.py` (lines 194-217):**

| Column | Type | Notes |
|--------|------|-------|
| `Message.id` | Integer PK | — |
| `Message.conversation_id` | Integer FK | — |
| `Message.direction` | Enum(MessageDirectionEnum) | stored as `"in"` / `"out"` |
| `Message.created_at` | DateTime | UTC-aware via `_utcnow` |

**MessageDirectionEnum values (line 47-49):**
- `MessageDirectionEnum.inbound` → string `"in"`
- `MessageDirectionEnum.outbound` → string `"out"`

**Python-side computation approach (preferred per D-13):**

Load all messages for the dealership's conversations in the last 30 days, then compute in-memory. This avoids SQL self-join complexity and JSONB dialect issues.

```python
from src.db.models import Conversation, Message, MessageDirectionEnum

thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

# Step 1: get conversation IDs for this dealership
r = await db.execute(
    select(Conversation.id).where(Conversation.dealership_id == did)
)
conv_ids = [row[0] for row in r.all()]

avg_response_str = "—"
if conv_ids:
    # Step 2: load all messages in those conversations from last 30 days
    r = await db.execute(
        select(Message.conversation_id, Message.direction, Message.created_at)
        .where(
            Message.conversation_id.in_(conv_ids),
            Message.created_at >= thirty_days_ago,
        )
        .order_by(Message.conversation_id, Message.created_at)
    )
    rows = r.all()

    # Step 3: group by conversation, pair inbound -> next outbound
    from collections import defaultdict
    by_conv: dict[int, list] = defaultdict(list)
    for conv_id, direction, created_at in rows:
        by_conv[conv_id].append((direction, created_at))

    deltas: list[float] = []
    for msgs in by_conv.values():
        i = 0
        while i < len(msgs):
            if msgs[i][0] == MessageDirectionEnum.inbound:
                # find next outbound
                j = i + 1
                while j < len(msgs) and msgs[j][0] != MessageDirectionEnum.outbound:
                    j += 1
                if j < len(msgs):
                    delta = (msgs[j][1] - msgs[i][1]).total_seconds()
                    if delta >= 0:
                        deltas.append(delta)
                i = j + 1
            else:
                i += 1

    if deltas:
        avg_secs = sum(deltas) / len(deltas)
        if avg_secs < 60:
            avg_response_str = f"{int(avg_secs)}s"
        else:
            mins = int(avg_secs // 60)
            secs = int(avg_secs % 60)
            avg_response_str = f"{mins}m {secs}s"
```

Pass `avg_response_str` to the template. Template receives a pre-formatted string — no formatting logic needed in Jinja.

**metrics.html new stat card to append to the stats-grid div:**
```html
<div class="stat-card">
    <div class="stat-number">{{ avg_response_str }}</div>
    <div class="stat-label">Avg response time</div>
</div>
```

**metrics_page() template dict change:** add `"avg_response_str": avg_response_str` to the existing `TemplateResponse` call.

---

### Gap 4: Existing Tests and Fixtures

**No existing tests for `admin_dashboard.py` routes.** The `tests/` directory contains only `conftest.py` — no test files exist yet (`tests/test_admin*.py` glob returned zero matches).

**Available fixtures in `conftest.py`:**

| Fixture | Provides |
|---------|----------|
| `db_session` | `AsyncSession` backed by SQLite in-memory (aiosqlite) |
| `dealership` | `Dealership(id=1)` with full fields |
| `dealership2` | `Dealership(id=2)` for isolation tests |
| `sample_car` | `InventoryItem` linked to `dealership` |
| `sample_car_with_ml_id` | `InventoryItem` with `ml_item_id` |
| `sample_car_no_photos` | `InventoryItem` without photos |

**No fixtures exist for:** `Conversation`, `Message`, `Lead`. New test fixtures must create these inline or as new `conftest.py` fixtures.

**Test file to create:** `tests/test_admin_dashboard.py`

**Test framework:** pytest + pytest-asyncio (mode: `auto`, confirmed in CLAUDE.md stack). SQLite in-memory via `db_session` fixture.

**SQLite note:** The `MessageDirectionEnum` is stored as `Enum(MessageDirectionEnum, values_callable=lambda x: [e.value for e in x])` which stores the string value (`"in"` / `"out"`). SQLite handles this fine because `values_callable` uses raw strings. However, `Lead.intent` and `Lead.status` use `Enum(LeadIntentEnum)` without `values_callable` — SQLite will store the enum name (`"visit"`, `"new"`) by default in SQLAlchemy, which matches the `.value` since all enum values equal their names (e.g., `LeadIntentEnum.visit.value == "visit"`). Queries using `Lead.intent == LeadIntentEnum.visit` will work correctly.

**Suggested test structure for `test_admin_dashboard.py`:**

```python
# test pending_visits count
async def test_pending_visits_counts_visit_new(db_session, dealership):
    # create Lead(intent=visit, status=new) — should count
    # create Lead(intent=info, status=new) — should NOT count
    # create Lead(intent=visit, status=handed_off) — should NOT count
    # assert pending_visits == 1

# test active_conversations
async def test_active_conversations_bot_mode_7days(db_session, dealership):
    # create Conversation(mode="bot", last_message_at=now-3d) — should count
    # create Conversation(mode="manager", last_message_at=now-3d) — should NOT count
    # create Conversation(mode="bot", last_message_at=now-10d) — should NOT count
    # assert active_conversations == 1

# test avg response time computation
async def test_avg_response_seconds_basic(db_session, dealership):
    # create Conversation, add Message(direction="in", created_at=T0),
    # Message(direction="out", created_at=T0+30s)
    # assert avg == 30s, formatted == "30s"

# test avg response time no data
async def test_avg_response_seconds_no_data(db_session, dealership):
    # no messages → avg_response_str == "—"
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Enum value comparison in SQLAlchemy | Custom string coercion | `Lead.intent == LeadIntentEnum.visit` directly — SQLAlchemy handles it |
| In-list filter | Manual OR conditions | `Lead.status.in_([LeadStatusEnum.new, LeadStatusEnum.qualified])` |
| Timezone-aware cutoff | Manual UTC offset math | `datetime.now(UTC) - timedelta(days=7)` — already the pattern in this file |

---

## Common Pitfalls

### Pitfall 1: `contacted` does not exist in LeadStatusEnum
**What goes wrong:** CONTEXT.md D-01 mentions `status in (new, contacted)` but `LeadStatusEnum` has no `contacted` member. Using `LeadStatusEnum.contacted` raises `AttributeError` at import time.
**How to avoid:** Use `LeadStatusEnum.new` and `LeadStatusEnum.qualified` — these are the two pre-handoff statuses. Confirm with stakeholder if `qualified` is correct semantics, but it is the only valid second option.
**Warning signs:** `AttributeError: contacted is not a valid LeadStatusEnum` at startup.

### Pitfall 2: datetime naive vs aware comparison
**What goes wrong:** `Conversation.last_message_at` is stored as naive UTC (via `_utcnow` which returns `datetime.now(UTC)`). If the comparison value is `datetime.now(UTC) - timedelta(days=7)` (aware), PostgreSQL handles this fine but SQLite in tests may raise a comparison error.
**How to avoid:** Use `datetime.now(UTC) - timedelta(days=7)` consistently — same pattern already used in `admin_dashboard.py` for `today_start`. For SQLite tests, store Message/Conversation timestamps as naive datetimes (strip tzinfo) if needed.

### Pitfall 3: Message.direction enum storage
**What goes wrong:** `Message.direction` uses `values_callable=lambda x: [e.value for e in x]` which stores `"in"` / `"out"` as raw strings. Comparing with `== MessageDirectionEnum.inbound` works in SQLAlchemy (it resolves to the value). However, when loading rows via `select(Message.direction)`, SQLAlchemy returns the enum member, not the raw string — so `msgs[i][0] == MessageDirectionEnum.inbound` works correctly.
**How to avoid:** Always compare against the enum member, not the raw string.

### Pitfall 4: Large message set performance
**What goes wrong:** Loading all messages for all conversations in 30 days into Python could be large on busy dealerships.
**How to avoid:** The Python-side approach is acceptable for this phase (single dealership, admin dashboard). Add a LIMIT or index check if performance becomes an issue in v2. The existing `ix_events_dealer_type_created` index pattern shows the codebase already indexes (dealership_id, type, created_at) — a similar pattern on messages would help, but no new index is required for this phase (D-12: no migrations).

### Pitfall 5: Template variable name mismatch
**What goes wrong:** Route passes `active_conversations` but template still reads `convs_today` (or vice versa) → Jinja renders empty/zero.
**How to avoid:** Change both the route dict key AND the template `{{ variable }}` reference atomically. There are exactly two places each.

---

## Code Examples

### Existing route signature to modify
```python
# src/api/routes/admin_dashboard.py, line 97
@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
    # ... queries ...
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "convs_today": convs_today,      # ← rename key to active_conversations
        "leads_today": leads_today,
        "pending_handoffs": pending_handoffs,  # ← rename key to pending_visits
        "top_searches": top_searches,
        "cars_available": cars_available,
    })
```

### Existing imports already available in admin_dashboard.py
```python
# Already imported — no new imports needed for Gap 1 and 2:
from sqlalchemy import select, func
from datetime import UTC, datetime, timedelta
from src.db.models import Dealership, InventoryItem, Lead, Conversation, Event, StatusEnum
# Need to ADD to the models import:
# LeadIntentEnum, LeadStatusEnum, Message, MessageDirectionEnum
```

### metrics_page() return dict (current, lines 270-278)
```python
return templates.TemplateResponse("admin/metrics.html", {
    "request": request,
    "convs_today": convs_today,
    "leads_today": leads_today,
    "leads_by_source": leads_by_source,
    "top_searches": top_searches,
    "handoffs_today": handoffs_today,
    "conversion": conversion,
    # ADD: "avg_response_str": avg_response_str,
})
```

---

## Project Constraints (from CLAUDE.md)

| Constraint | Directive |
|------------|-----------|
| Stack | Python 3.12 + FastAPI + SQLAlchemy 2.0 — do not change |
| File naming | `snake_case.py` for Python modules |
| Test files | `test_<module>.py` pattern → use `test_admin_dashboard.py` |
| Imports | Explicit named imports; no wildcards (except conftest.py) |
| Strings | Prefer double quotes |
| Logging | `%s` formatting, not f-strings |
| Error handling | `except Exception` with logging, never bare `except:` |
| Async | `async def` with `AsyncSession`, `await db.execute(...)` |
| No Pydantic models | Raw dicts for route data transfer |
| GSD workflow | Changes must go through GSD execute-phase |

---

## Environment Availability

Step 2.6: SKIPPED — this phase is purely Python route + Jinja template edits. No external CLI tools, services, or runtimes beyond the existing project stack are required.

---

## Validation Architecture

`nyquist_validation` is `false` in `.planning/config.json`. This section is skipped.

---

## Open Questions

1. **`contacted` vs `qualified` for pending_visits status filter**
   - What we know: `LeadStatusEnum` has `new`, `qualified`, `handed_off`, `closed`. No `contacted` member exists.
   - What's unclear: Was `contacted` an intended future enum value, or did the CONTEXT.md author mean `qualified`?
   - Recommendation: Use `(LeadStatusEnum.new, LeadStatusEnum.qualified)` — these are the two non-terminal statuses before handoff. Flag to stakeholder if semantics differ.

---

## Sources

### Primary (HIGH confidence)
- `src/db/models.py` — all enum values, column names, column types verified by direct inspection
- `src/api/routes/admin_dashboard.py` — route signatures, variable names, template dict keys verified
- `src/templates/admin/dashboard.html` — stat card labels and template variable names verified
- `src/templates/admin/metrics.html` — existing stat card structure verified
- `tests/conftest.py` — available fixtures and test database setup verified
- `.planning/config.json` — nyquist_validation: false confirmed

### Secondary (MEDIUM confidence)
- `.planning/phases/07-admin-dashboard-analytics/07-CONTEXT.md` — implementation decisions; one discrepancy found (contacted enum value)

---

## Metadata

**Confidence breakdown:**
- Enum values: HIGH — read directly from models.py
- Route variable names: HIGH — read directly from admin_dashboard.py
- Template variable names: HIGH — read directly from dashboard.html and metrics.html
- avg_response_seconds snippet: HIGH — follows existing patterns in the codebase
- Test fixtures: HIGH — read directly from conftest.py
- contacted enum discrepancy: HIGH confidence it is an error in CONTEXT.md

**Research date:** 2026-03-27
**Valid until:** Until models.py enum definitions change (stable)
