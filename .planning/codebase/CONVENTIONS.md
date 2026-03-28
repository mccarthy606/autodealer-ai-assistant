# Coding Conventions

**Analysis Date:** 2026-03-27

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `conversation_engine.py`, `lead_service.py`, `rate_limit.py`
- Test files: `test_<module>.py` pattern: `test_engine.py`, `test_webhook.py`, `test_inventory.py`
- `__init__.py` in every package (most are empty or minimal)

**Functions:**
- Use `snake_case` for all functions: `detect_intent()`, `extract_brand()`, `process_message()`
- Private/helper functions prefixed with underscore: `_get_or_create_conversation()`, `_car_to_dict()`, `_format_car_line()`
- Async functions use `async def` with no special naming prefix

**Variables:**
- Use `snake_case`: `dealership_id`, `budget_max`, `car_summary`
- Constants use `UPPER_SNAKE_CASE`: `SEARCH_CAR`, `REASON_VISIT_SCHEDULING`, `GRAPH_API_URL`
- Private module-level variables prefixed with underscore: `_RESPONSES`, `_EN_STOPS`, `_redis`

**Classes:**
- Use `PascalCase`: `InventoryService`, `WhatsAppCloudAdapter`, `EngineResult`
- Enums use `PascalCase` with `Enum` suffix: `ConditionEnum`, `StatusEnum`, `LeadIntentEnum`
- Enum members use `snake_case` string values: `zero_km`, `in_transit`, `handed_off`

**Types:**
- No Pydantic models for request/response schemas (uses raw dicts)
- Pydantic only for `Settings` config via `pydantic-settings`
- SQLAlchemy models use `PascalCase` class names with plural `snake_case` table names: `class Lead` -> `__tablename__ = "leads"`

## Code Style

**Formatting:**
- No `.prettierrc`, `.editorconfig`, `black.toml`, or `ruff.toml` detected
- No autoformatter is configured; follow the existing style manually
- Use 4-space indentation (Python standard)
- Strings: prefer double quotes `"` for all strings

**Linting:**
- No `.flake8`, `pylintrc`, `ruff.toml`, or `mypy.ini` detected
- No linter is enforced; follow PEP 8 conventions by inspection

## Import Organization

**Order:**
1. Standard library imports (`re`, `logging`, `enum`, `datetime`)
2. Third-party imports (`sqlalchemy`, `fastapi`, `httpx`, `pydantic_settings`)
3. Local imports (`from src.db.models import ...`, `from src.services.intent import ...`)

**Style:**
- Use explicit named imports, not wildcard (except `conftest.py` which uses `from src.db.models import *`)
- Group related imports on one line when reasonable:
  ```python
  from src.db.models import (
      Conversation, Dealership, Message, MessageDirectionEnum,
      Event, InventoryItem,
  )
  ```
- Trailing commas in multi-line import tuples

**Path Aliases:**
- No path aliases configured
- All imports use relative package paths from `src`: `from src.services.intent import detect_intent`
- No `__init__.py` re-exports; import directly from the source module

## Error Handling

**Patterns:**
- Broad `except Exception` with logging, never bare `except:`
- Pattern: try/except -> log warning -> return graceful fallback

Example from `src/services/notifications.py`:
```python
try:
    await aiosmtplib.send(msg, ...)
except Exception as e:
    logger.warning("Failed to send handoff email: %s", e)
```

- Database race conditions handled with rollback + retry in `src/services/conversation_engine.py`:
```python
try:
    session.add(conv)
    await session.flush()
except Exception:
    await session.rollback()
    r = await session.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        raise
```

- API dependency `get_db()` in `src/api/deps.py` uses try/except/finally for commit/rollback/close
- Enum parsing uses try/except ValueError with `pass` to silently skip invalid values (`src/services/inventory.py`)
- No custom exception classes exist; all errors use built-in exceptions

## Logging

**Framework:** Python standard `logging` module

**Setup:** Configured once in `src/main.py`:
```python
logging.basicConfig(level=logging.INFO)
```

**Per-module pattern:** Every module that logs creates a module-level logger:
```python
logger = logging.getLogger(__name__)
```

**When to log:**
- `logger.info()` for business events: handoffs, lead creation, startup, mock API calls
- `logger.warning()` for recoverable failures: failed emails, Redis connection, migration issues
- `logger.error()` for API/integration failures: WhatsApp API errors
- Use `%s` string formatting, not f-strings: `logger.info("Lead created: id=%s intent=%s", lead.id, intent)`

**Modules with loggers:**
- `src/main.py`
- `src/services/conversation_engine.py`
- `src/services/lead_service.py`
- `src/services/notifications.py`
- `src/adapters/whatsapp_cloud.py`
- `src/api/routes/webhooks.py`
- `src/api/rate_limit.py`

## Comments

**When to Comment:**
- Module-level docstrings on every `.py` file (triple-quoted, one-line):
  ```python
  """Rule-based intent detection. No LLM needed."""
  ```
- Section separator comments with `# --- Section Name ---` in longer files:
  ```python
  # --- Enums ---
  # --- Models ---
  # --- Keyword maps (ES + EN) ---
  ```
- Inline comments for business logic rules: `# H1: Explicit human`, `# Idempotency check`
- `# noqa` used sparingly: `from src.db.models import *  # noqa - import all models`

**Docstrings:**
- Use triple-quoted strings for all public functions
- Brief one-line docstrings preferred:
  ```python
  def detect_intent(text: str, state: dict | None = None) -> str:
      """Detect user intent from message text. Returns intent constant."""
  ```
- Multi-line docstrings for complex functions use imperative mood:
  ```python
  """
  Create lead from conversation state. Idempotent: won't duplicate
  if a lead with same intent exists for this conversation in last 30 minutes.
  Returns lead_id or None if duplicate.
  """
  ```
- No docstrings on private helper functions (underscore-prefixed)

## Type Annotations

**Usage:** Moderate -- present on function signatures, not on local variables

**Patterns:**
- All function parameters and return types are annotated:
  ```python
  async def process_message(
      session: AsyncSession,
      dealership_id: int,
      phone: str,
      text: str,
      channel: str = "whatsapp",
  ) -> EngineResult:
  ```
- Use `Optional[X]` from `typing` (not `X | None`), except for `dict | None` in newer code
- Use `list[dict]`, `dict[str, Any]`, `tuple[Optional[float], Optional[float]]` (Python 3.12 syntax)
- `AsyncGenerator` used for dependency injection: `async def get_db() -> AsyncGenerator[AsyncSession, None]`
- No `TypedDict` or `Protocol` usage; plain dicts used for data transfer

## Pydantic Model Patterns

**Config only:** Pydantic is used exclusively for settings via `pydantic-settings`:

```python
# src/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = "postgresql://postgres:postgres@localhost:5432/autodealer"
    openai_api_key: str = ""
    llm_enabled: bool = False
```

- All settings have defaults (app works with zero env vars)
- Singleton instance: `settings = Settings()` at module level
- No Pydantic models for API request/response validation; raw dicts and SQLAlchemy models used instead

## Data Transfer Patterns

**Dict-based:** The codebase passes data as plain `dict[str, Any]` rather than typed models:
- `InventoryService.search()` returns `list[dict[str, Any]]`
- `EngineResult` is a plain class with `to_dict()` method (not a Pydantic model)
- `_car_to_dict()` converts SQLAlchemy model to dict manually
- Conversation state stored as `dict` in JSONB column

**When adding new data structures:** Follow the existing dict-based pattern. If adding API schemas, consider introducing Pydantic models for validation, but keep internal service interfaces as dicts.

## Module Design

**Exports:** No barrel files or `__init__.py` re-exports. Import directly from source module.

**Service pattern:** Two styles coexist:
1. **Static method class** (`src/services/inventory.py`):
   ```python
   class InventoryService:
       @staticmethod
       async def search(session, dealership_id, *, brand=None, ...):
   ```
2. **Module-level functions** (`src/services/conversation_engine.py`, `src/services/intent.py`):
   ```python
   async def process_message(session, dealership_id, phone, text, channel):
   ```

**When to use which:** Use module-level functions for the primary pattern. Use static method classes only if grouping related operations under a namespace (like `InventoryService`).

## Multilingual Patterns

**Language handling:** The codebase supports Spanish (es) and English (en):
- Language detected per-message via `detect_language()` in `src/services/entities.py`
- Response templates keyed by `(intent, language)` tuples in `src/services/responder.py`
- Use `lang.startswith("es")` to check Spanish (handles `es-AR`, `es`, etc.)
- Default language is Spanish (`es-AR`)

**When adding new responses:** Add both `("KEY", "es")` and `("KEY", "en")` entries to the `_RESPONSES` dict in `src/services/responder.py`.

---

*Convention analysis: 2026-03-27*
