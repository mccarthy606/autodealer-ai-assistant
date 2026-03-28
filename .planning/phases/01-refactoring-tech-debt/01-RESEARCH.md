# Phase 1: Refactoring & Tech Debt - Research

**Researched:** 2026-03-27
**Domain:** Python/FastAPI codebase refactoring -- engine merge, module split, deprecated API fix
**Confidence:** HIGH

## Summary

This phase is a pure structural refactoring with no new features. The codebase has three clear problems: (1) two parallel conversation engines (`conversation_engine.py` and `orchestrator.py`) that handle the same user messages differently, (2) a 32KB monolithic admin UI route file (`admin_ui.py`, 939 lines) that should be split by domain, and (3) `datetime.utcnow()` calls scattered across 7 files (17 occurrences total) that must be replaced with `datetime.now(datetime.UTC)`.

The engine merge is the riskiest task because `conversation_engine.py` is the core product (all webhooks route through it) and 10 integration tests validate its behavior. The admin UI split is mechanical but large. The datetime fix is a simple find-and-replace with one tricky edge case: SQLAlchemy model `default=datetime.utcnow` callables in `models.py` (9 occurrences) must also be updated.

**Primary recommendation:** Merge engines first (highest risk, smallest surface), then split admin_ui (largest scope, lowest risk), then fix datetime calls (global, mechanical). Run tests after each step.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `conversation_engine.py` as the base -- it has the complete state machine (NEW -> BROWSING -> PRESENTING -> DETAILS -> CLOSING -> HANDOFF) and handles all 7 intents deterministically.
- **D-02:** Absorb LLM integration from `orchestrator.py` as an optional layer. When `LLM_ENABLED=true`, pass the deterministic response through LLM for phrasing improvement. When false (default), pure deterministic.
- **D-03:** Delete `orchestrator.py` and `deterministic_responder.py` after merge. All routes must use the single unified engine.
- **D-04:** Keep `llm_service.py` as a separate service -- engine calls it optionally, not the other way around.
- **D-05:** Split by domain into separate route modules: admin_dashboard.py, admin_inventory.py, admin_leads.py, admin_conversations.py, admin_settings.py
- **D-06:** Keep Jinja2 templates in `templates/admin/` -- one template per module.
- **D-07:** Shared admin auth middleware stays in `api/auth.py` -- each module imports it.
- **D-08:** Each module should be under 300 lines. If over, split further.
- **D-09:** Replace all `datetime.utcnow()` with `datetime.now(datetime.UTC)` across the entire codebase (models, engine, services).

### Claude's Discretion
- Test approach: refactor first, then fix tests. Existing tests cover engine behavior -- adapt imports and function signatures after merge. Add tests for any new edge cases discovered during refactoring.
- File naming: use `snake_case` matching existing convention.
- Import paths: keep relative imports matching existing pattern.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REF-01 | Merge conversation_engine.py and orchestrator.py into single engine | Engine merge analysis: orchestrator has 3 unique features to absorb (LLM optional layer, visit intent priority bypass, debug mode). All other orchestrator functionality duplicates engine. |
| REF-02 | Split admin_ui.py (32KB) into domain modules | Admin split analysis: 939 lines naturally group into 5 domains. Shared auth helper and template setup must be factored out or duplicated. |
| REF-03 | Replace datetime.utcnow() with datetime.now(UTC) | Full audit: 17 call-site occurrences across 5 files + 9 model default callables in models.py = 26 total changes. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Stack locked:** Python 3.12 + FastAPI + SQLAlchemy 2.0 -- do not change
- **GSD Workflow:** Do not make direct repo edits outside a GSD workflow unless user explicitly asks to bypass
- **Conventions:** snake_case files, relative imports from `src`, double quotes, 4-space indent, no autoformatter
- **Logging:** Use `%s` formatting, not f-strings in logger calls
- **Error handling:** Broad `except Exception` with logging, never bare `except:`
- **Docstrings:** Module-level docstrings on every .py file, public functions get triple-quoted docstrings

## Architecture Patterns

### Engine Merge Strategy

The `orchestrator.py` (278 lines) has **three features not in `conversation_engine.py`**:

1. **Visit intent priority bypass** (`_try_handle_visit_intent`): Checks visit intent BEFORE any other processing. The engine already handles VISIT intent in its main flow (lines 287-306), so this is redundant but uses `visit_confirmation.py` directly. The engine's VISIT handler is more complete (creates lead, does handoff, builds response with address/hours). **Action:** Keep engine's VISIT handling, drop orchestrator's bypass.

2. **Optional LLM layer** (`process_message` method): When `openai_api_key` is set, sends message through `LLMService.generate_response()` with tool calling. **Action:** Add optional LLM pass-through in engine -- after deterministic response is built, if `settings.llm_enabled`, call `llm_service` to rephrase. Keep it as a post-processing step, not an alternative path.

3. **Debug mode** (`process_message_debug`): Returns extra tuple with `(text, matched_inventory, state, conversation_id, lead_id)`. **Action:** The engine already returns `EngineResult` with all these fields. The debug endpoint (`debug_routes.py`) already uses `conversation_engine.process_message` directly. The admin UI test chat also already uses `process_message`. No absorption needed -- orchestrator's debug mode is already superseded.

**Key finding:** The orchestrator imports `create_visit_lead` from `lead_service.py`, but **this function does not exist** in the current lead_service.py. This is a dead import -- further evidence the orchestrator is already stale/deprecated.

**Who imports what:**
- `conversation_engine.process_message` is imported by: webhook_cloud.py, webhook_ml.py, webhooks.py, debug_routes.py, admin_ui.py, test_engine.py
- `ConversationOrchestrator` is imported by: **nobody** (only defined in orchestrator.py itself)
- `deterministic_responder.respond` is imported by: only orchestrator.py

**Conclusion:** The orchestrator is already effectively dead code. No route or test imports it. The merge is primarily about absorbing the LLM optional layer concept into the engine, then deleting the files.

### Admin UI Split Plan

Current `admin_ui.py` (939 lines) natural domain groupings:

| New Module | Routes | Lines (est) | Templates Used |
|------------|--------|-------------|----------------|
| `admin_dashboard.py` | `GET /admin/ui` (dashboard), auth routes (login/logout), `GET /admin/ui/test`, `POST /admin/ui/test/send`, `GET /admin/ui/metrics` | ~180 | dashboard.html, login.html, test_chat.html, metrics.html |
| `admin_inventory.py` | `GET/POST /admin/ui/cars/*`, CSV import, ML URL import | ~350 | cars.html, car_form.html, car_detail.html |
| `admin_leads.py` | `GET /admin/ui/leads` | ~40 | leads.html |
| `admin_conversations.py` | `GET /admin/ui/conversations/*`, send, takeover, return-bot | ~150 | conversations.html, conversation_detail.html |
| `admin_settings.py` | `GET/POST /admin/ui/settings`, `GET /admin/ui/integrations` | ~80 | settings.html, integrations.html |

**Problem:** `admin_inventory.py` will be ~350 lines (over 300 limit). The ML URL import routes (lines 635-769) are ~135 lines and could be a separate section or file. **Recommendation:** Keep in one file but use clear section separators (`# --- ML Import ---`). If planner insists on strict <300, split ML import into `admin_inventory_ml.py`.

**Shared infrastructure each module needs:**
```python
from src.api.auth import is_authenticated, _check_password, create_session, clear_session, remove_session
from src.api.deps import get_db
from src.config import settings

# Each module creates its own router with prefix
router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])

# Templates setup (shared path)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Auth check helper
def _auth_check(request: Request) -> Optional[RedirectResponse]:
    session = request.cookies.get("admin_session")
    if not is_authenticated(session):
        return RedirectResponse(url="/admin/ui/login", status_code=302)
    return None
```

**Option:** Extract `_auth_check` and template setup into a shared `admin_common.py` helper to avoid duplication in 5 files.

### Router Registration Update

`src/main.py` currently does:
```python
from src.api.routes import admin_ui
app.include_router(admin_ui.router)
```

After split, must register all 5 new routers. All share prefix `/admin/ui`.

### Recommended File Structure After Refactoring

```
src/
  api/
    routes/
      admin_common.py          # NEW: shared auth check, template setup
      admin_dashboard.py       # NEW: dashboard, auth, test chat, metrics
      admin_inventory.py       # NEW: car CRUD, CSV import, ML import
      admin_leads.py           # NEW: lead listing
      admin_conversations.py   # NEW: conversation viewer, send, takeover
      admin_settings.py        # NEW: settings, integrations
      admin_ui.py              # DELETE after split
      debug_routes.py          # KEEP (already uses conversation_engine)
      webhook_cloud.py         # KEEP (already uses conversation_engine)
      webhooks.py              # KEEP
      admin.py                 # KEEP (REST API, separate from UI)
  services/
    conversation_engine.py     # MODIFY: add optional LLM layer
    orchestrator.py            # DELETE after merge
    deterministic_responder.py # DELETE after merge
    llm_service.py             # KEEP as-is
```

## datetime.utcnow() Audit

### Call Sites (17 occurrences)

| File | Line(s) | Context |
|------|---------|---------|
| `conversation_engine.py` | 107, 398, 490 | `conv.last_message_at`, `conv.last_handoff_at` |
| `orchestrator.py` | 125, 159, 203, 262 | Same patterns (will be deleted) |
| `admin_ui.py` | 89, 343, 358, 518, 539, 743, 822 | Dashboard date calc, update timestamps |
| `admin.py` | 198 | Metrics date calc |
| `lead_service.py` | 41 | Idempotency cutoff |

### Model Defaults (9 occurrences in models.py)

| Model | Column(s) |
|-------|-----------|
| `InventoryItem` | `created_at` |
| `Conversation` | `last_message_at`, `created_at`, `updated_at` |
| `Message` | `created_at` |
| `Lead` | `created_at` |
| `Event` | `created_at` |

**Pattern change:**
```python
# Before
from datetime import datetime
created_at = Column(DateTime, default=datetime.utcnow)
updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# After
from datetime import datetime, UTC
created_at = Column(DateTime, default=lambda: datetime.now(UTC))
updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

**Important:** SQLAlchemy `default=datetime.utcnow` passes the function as a callable (no parentheses). The replacement `datetime.now(UTC)` needs a lambda wrapper because `datetime.now(UTC)` is not a zero-argument callable -- it requires the `UTC` argument.

**Alternative (cleaner):** Define a helper:
```python
def _utcnow():
    return datetime.now(UTC)
```
Then use `default=_utcnow, onupdate=_utcnow`.

### Import Change

All files currently use `from datetime import datetime`. After the fix:
```python
from datetime import datetime, UTC
```

Python 3.12 has `datetime.UTC` available (added in 3.11 as `datetime.UTC` alias for `datetime.timezone.utc`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Admin auth middleware | Per-route auth decorator | Shared `_auth_check()` in `admin_common.py` | Already exists, just extract to shared module |
| Template config per module | Separate Jinja2Templates per file | Single shared templates instance from `admin_common.py` | Avoid 5 copies of same path resolution |
| Router prefix management | Different prefixes per module | All modules use same `/admin/ui` prefix | Maintains URL compatibility |

## Common Pitfalls

### Pitfall 1: Breaking Import Paths After File Deletion
**What goes wrong:** After deleting `orchestrator.py` and `deterministic_responder.py`, any remaining import of these modules causes `ImportError` at startup.
**Why it happens:** Imports can be hidden in lazy imports, conditional imports, or test files.
**How to avoid:** After deletion, grep the entire codebase for `orchestrator` and `deterministic_responder` strings. Current state: orchestrator is only imported by itself (self-referential), deterministic_responder only by orchestrator. Test files `test_orchestrator.py` and `test_debug_routes.py` are stubs with no actual imports. Safe to delete.
**Warning signs:** App fails to start after file deletion.

### Pitfall 2: Admin Router Prefix Collision
**What goes wrong:** Multiple admin modules registering routers with the same prefix `/admin/ui` can cause route conflicts if two modules define the same path.
**Why it happens:** FastAPI allows multiple routers with same prefix, but identical path+method combinations will shadow each other.
**How to avoid:** Each module owns distinct URL paths. No two modules should define the same route. Current grouping ensures no overlap.
**Warning signs:** 404 on previously working URLs, or wrong handler executing.

### Pitfall 3: SQLAlchemy Model Default Callable Syntax
**What goes wrong:** Using `default=datetime.now(UTC)` (with parentheses) evaluates once at import time, giving all rows the same timestamp.
**Why it happens:** Python evaluates the expression immediately. Need a callable (no parens) or lambda.
**How to avoid:** Always use `default=lambda: datetime.now(UTC)` or define a helper function.
**Warning signs:** All new records have identical timestamps.

### Pitfall 4: LLM Layer Changes Engine Return Contract
**What goes wrong:** Adding optional LLM rephrasing might change the text format that downstream code (WhatsApp adapter, test assertions) expects.
**Why it happens:** LLM output is non-deterministic.
**How to avoid:** LLM layer should ONLY modify `result.text` for phrasing. Never modify state, intent, matched_cars, or other structured fields. Default `LLM_ENABLED=false` means tests run deterministically.
**Warning signs:** Flaky tests that sometimes pass, sometimes fail.

### Pitfall 5: Circular Import When Extracting admin_common.py
**What goes wrong:** If `admin_common.py` imports from a module that imports back from it.
**Why it happens:** Python circular imports are a common issue when extracting shared code.
**How to avoid:** `admin_common.py` should only import from `src.api.auth`, `src.config`, `fastapi`, `pathlib`, `jinja2`. No imports from route modules.
**Warning signs:** `ImportError: cannot import name ... (most likely due to a circular import)`.

## Code Examples

### Engine LLM Optional Layer Addition

```python
# In conversation_engine.py, after building deterministic result (around line 400):

# Optional LLM rephrasing
if settings.llm_enabled and result.text and result.mode == "bot":
    try:
        from src.services.llm_service import LLMService
        llm = LLMService()
        rephrased = await llm.rephrase(result.text, lang)
        if rephrased:
            result.text = rephrased
    except Exception as e:
        logger.warning("LLM rephrase failed, using deterministic: %s", e)
        # Keep deterministic response on failure
```

### Admin Common Module

```python
# src/api/routes/admin_common.py
"""Shared utilities for admin UI route modules."""

from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.auth import is_authenticated

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def auth_check(request: Request) -> Optional[RedirectResponse]:
    """Return redirect to login if not authenticated, else None."""
    session = request.cookies.get("admin_session")
    if not is_authenticated(session):
        return RedirectResponse(url="/admin/ui/login", status_code=302)
    return None
```

### datetime.now(UTC) Migration

```python
# Before (any file):
from datetime import datetime
conv.last_message_at = datetime.utcnow()

# After:
from datetime import datetime, UTC
conv.last_message_at = datetime.now(UTC)

# Models before:
created_at = Column(DateTime, default=datetime.utcnow)

# Models after:
from datetime import datetime, UTC
def _utcnow():
    return datetime.now(UTC)

created_at = Column(DateTime, default=_utcnow)
updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
```

### Router Registration in main.py

```python
# Before:
from src.api.routes import admin_ui
app.include_router(admin_ui.router)

# After:
from src.api.routes import (
    admin_dashboard, admin_inventory, admin_leads,
    admin_conversations, admin_settings,
)
app.include_router(admin_dashboard.router)
app.include_router(admin_inventory.router)
app.include_router(admin_leads.router)
app.include_router(admin_conversations.router)
app.include_router(admin_settings.router)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4+ with pytest-asyncio 0.23+ |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `docker compose run --rm api pytest tests/ -x -v` |
| Full suite command | `docker compose run --rm api pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REF-01 | Single engine processes all messages; orchestrator deleted | integration | `pytest tests/test_engine.py -x -v` | Yes |
| REF-01 | No import errors after orchestrator/deterministic_responder deletion | smoke | `python -c "from src.services.conversation_engine import process_message"` | Manual |
| REF-02 | Admin UI split: all routes still accessible | smoke | `pytest tests/ -x -v` (no admin UI tests exist) | No tests |
| REF-02 | Each admin module under 300 lines | manual | `wc -l src/api/routes/admin_*.py` | Manual |
| REF-03 | No datetime.utcnow() in codebase | unit | `grep -r "datetime.utcnow" src/ && exit 1 \|\| exit 0` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -v` (quick, all existing tests)
- **Per wave merge:** `pytest tests/ -v` (full suite)
- **Phase gate:** Full suite green + grep confirms no datetime.utcnow + no orchestrator imports

### Wave 0 Gaps
- [ ] No admin UI route tests exist -- cannot validate REF-02 with automated tests. Manual smoke test needed (or add basic route tests).
- [ ] Need a grep-based validation script to confirm no `datetime.utcnow()` remains after REF-03.
- [ ] `test_orchestrator.py` and `test_debug_routes.py` are stubs -- should be deleted along with the orchestrator.

## Open Questions

1. **LLM rephrase API on LLMService**
   - What we know: `LLMService.generate_response()` exists and does full tool-calling flow. Decision D-02 says "pass deterministic response through LLM for phrasing improvement."
   - What's unclear: Whether to add a lightweight `rephrase()` method to LLMService or reuse `generate_response()` with modified prompt.
   - Recommendation: Add a simple `rephrase(text, lang)` method to LLMService that takes the deterministic response and returns a polished version. Simpler, cheaper, no tool calling needed.

2. **admin_inventory.py line count**
   - What we know: Inventory routes + CSV import + ML URL import = ~350 lines, exceeding 300 limit.
   - What's unclear: Whether to split ML import into separate file or relax the limit.
   - Recommendation: Split ML import into admin_inventory.py and keep CSV import inline. If still over 300, extract CSV import too. The planner should measure after splitting.

## Sources

### Primary (HIGH confidence)
- Direct source code analysis of all affected files
- `conversation_engine.py` (502 lines), `orchestrator.py` (278 lines), `deterministic_responder.py` (94 lines)
- `admin_ui.py` (939 lines) -- full route analysis
- `models.py` -- grep for datetime.utcnow default callables
- All import dependency chains verified via grep

### Secondary (MEDIUM confidence)
- Python 3.12 `datetime.UTC` availability -- confirmed in Python docs (added 3.11)
- SQLAlchemy default callable behavior -- standard documented behavior

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure refactoring of existing code
- Architecture: HIGH -- all files read in full, dependency graph fully traced
- Pitfalls: HIGH -- based on direct code analysis, not speculation

**Research date:** 2026-03-27
**Valid until:** No expiration -- this is codebase-specific structural analysis
