# Testing

## Framework & Tools

- **pytest** + **pytest-asyncio** — async test support
- **aiosqlite** — in-memory SQLite for test DB (no PostgreSQL needed)
- **No mocking libraries** — tests use real DB via SQLite in-memory
- Run: `docker compose run --rm api pytest tests/ -v` or `make test`

## Test Organization

```
tests/
├── conftest.py                  # Shared fixtures (db_session, dealership, sample cars)
├── test_engine.py               # Conversation engine integration tests (10 tests)
├── test_intent_entities.py      # Intent detection + entity extraction unit tests (22 tests)
├── test_inventory.py            # Inventory search tests
├── test_visit_confirmation.py   # Visit scheduling logic tests
├── test_webhook.py              # Webhook payload parsing tests
├── test_orchestrator.py         # Orchestrator tests
└── test_debug_routes.py         # Debug endpoint tests
```

## Fixtures (conftest.py)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | function | SQLite async in-memory session, creates/drops all tables per test |
| `dealership` | function | Test dealership (id=1, "Test Dealership", CABA, es-AR) |
| `sample_car` | function | Toyota Hilux 2023, used, 45k km, ARS 18M, **with photos** |
| `sample_car_no_photos` | function | Ford Ranger 2024, 0km, ARS 25M, **no photos** |

**Pattern:** SQLite in-memory replaces PostgreSQL — no external DB needed. Tables created via `Base.metadata.create_all`, dropped after each test.

## Test Categories

### Conversation Engine Tests (`test_engine.py`)
Integration tests — full `process_message()` flow:
- English language detection and response
- Photo request sends URLs when available
- Photo request triggers handoff when missing
- Visit creates lead + switches to manager mode
- Financing triggers handoff
- Search → visit does NOT re-search
- Greeting response
- Trade-in triggers handoff
- Human request triggers handoff
- Manager mode suppresses auto-reply

### Intent & Entity Tests (`test_intent_entities.py`)
Unit tests — pure functions, no DB:
- **Intent detection:** greeting (es/en), search, photos, visit, financing, trade-in, human request
- **Language detection:** Spanish, English, default (Spanish)
- **Entity extraction:** name (es/en), time (tomorrow, afternoon, today), brand (Toyota, VW→Volkswagen), model (Hilux), year (2023), budget (millones, K notation), condition (0km, used)

### Other Test Files
- **test_inventory.py** — `InventoryService.search()` with various filters
- **test_visit_confirmation.py** — visit intent detection + detail extraction
- **test_webhook.py** — WhatsApp webhook payload parsing (Twilio + Meta formats)
- **test_orchestrator.py** — `ConversationOrchestrator` flow
- **test_debug_routes.py** — debug endpoint responses

## Testing Patterns

### Async Tests
All DB-touching tests use `@pytest.mark.asyncio` + `async def`:
```python
@pytest.mark.asyncio
async def test_something(db_session: AsyncSession, dealership: Dealership):
    result = await process_message(db_session, ...)
    assert result.text
```

### Multi-Step Conversation Tests
Tests simulate multi-turn conversations by calling `process_message` multiple times with the same phone number:
```python
# Step 1: search
await process_message(session, dealer_id, phone, "Tienen Hilux?", "admin_test")
# Step 2: visit (same phone → same conversation)
result = await process_message(session, dealer_id, phone, "Quiero pasar mañana", "admin_test")
assert result.mode == "manager"
```

### No Mocking
- No `unittest.mock` usage found
- Tests use real SQLite DB session
- No external API mocking (WhatsApp, MercadoLibre, OpenAI)
- LLM tests would need OpenAI mocking (not currently present)

## Coverage Gaps

### Well-tested
- Conversation engine state machine (all major intents)
- Intent detection (Spanish + English)
- Entity extraction (all types)
- Handoff triggers (all 6 reasons)

### Not tested
- Admin API endpoints (CRUD operations)
- Admin UI routes
- WhatsApp Cloud adapter (actual API calls)
- MercadoLibre adapter
- LLM service (OpenAI integration)
- Notification service (webhook, SMTP)
- Celery background tasks
- CSV import
- Rate limiting
- Authentication
- Error handling / edge cases
- Database migrations
