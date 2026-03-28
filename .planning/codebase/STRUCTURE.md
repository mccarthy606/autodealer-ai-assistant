# Project Structure

## Directory Tree

```
autodealer-ai-assistant/
├── src/                          # Application source code
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry point, router registration, startup
│   ├── config.py                 # Pydantic Settings (env vars → typed config)
│   │
│   ├── db/                       # Database layer
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy ORM models (12+ models, enums)
│   │   └── session.py            # Async + sync engine setup, get_db dependency
│   │
│   ├── api/                      # HTTP layer
│   │   ├── __init__.py
│   │   ├── auth.py               # Admin authentication
│   │   ├── deps.py               # FastAPI dependencies
│   │   ├── rate_limit.py         # Rate limiting middleware
│   │   └── routes/               # Route modules
│   │       ├── __init__.py
│   │       ├── admin.py          # REST API: dealerships, inventory, leads, metrics
│   │       ├── admin_ui.py       # Admin dashboard UI (Jinja2 templates, 32KB)
│   │       ├── webhook_cloud.py  # WhatsApp Business Cloud API webhook
│   │       ├── webhook_ml.py     # MercadoLibre webhook
│   │       ├── webhooks.py       # Generic webhook handler
│   │       ├── debug_routes.py   # Debug/test endpoints
│   │       ├── celery_routes.py  # Task management endpoints
│   │       └── import_routes.py  # CSV inventory import
│   │
│   ├── services/                 # Business logic layer
│   │   ├── __init__.py
│   │   ├── conversation_engine.py  # CORE: state machine (500 lines)
│   │   ├── orchestrator.py         # LLM-aware conversation orchestration
│   │   ├── intent.py               # Rule-based intent detection
│   │   ├── entities.py             # Entity extraction + language detection
│   │   ├── inventory.py            # Car search service
│   │   ├── responder.py            # Multilingual response builder
│   │   ├── deterministic_responder.py  # Standalone rule-based responses
│   │   ├── lead_service.py         # Lead creation and management
│   │   ├── handoff_rules.py        # Bot→human handoff conditions
│   │   ├── llm_service.py          # OpenAI API integration
│   │   ├── notifications.py        # Webhook + email notifications
│   │   └── visit_confirmation.py   # Visit scheduling logic
│   │
│   ├── adapters/                 # External API clients
│   │   ├── __init__.py
│   │   ├── base.py               # Adapter interface
│   │   ├── whatsapp_cloud.py     # Meta WhatsApp Cloud API client
│   │   └── mercadolibre.py       # MercadoLibre API client
│   │
│   ├── webhooks/                 # Webhook payload parsing
│   │   └── whatsapp.py           # Supports Twilio + Meta formats
│   │
│   ├── tasks/                    # Background jobs
│   │   ├── __init__.py
│   │   ├── celery_app.py         # Celery configuration
│   │   └── import_tasks.py       # CSV import background tasks
│   │
│   ├── templates/                # Jinja2 HTML templates
│   │   └── admin/                # Admin UI pages (9 templates)
│   │
│   └── static/                   # Static assets
│       └── admin.css             # Admin dashboard styles
│
├── alembic/                      # Database migrations
│   ├── env.py                    # Alembic environment config
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_mvp_schema_extensions.py
│
├── tests/                        # Test suite
│   ├── conftest.py               # Shared fixtures
│   ├── test_engine.py            # Conversation engine tests
│   ├── test_intent_entities.py   # Intent + entity extraction tests
│   ├── test_inventory.py         # Inventory search tests
│   ├── test_visit_confirmation.py
│   ├── test_webhook.py           # Webhook parsing tests
│   ├── test_orchestrator.py
│   └── test_debug_routes.py
│
├── examples/
│   └── curl_examples.sh          # 8 API call examples
│
├── scripts/                      # Utility scripts
│
├── docker-compose.yml            # Multi-container: api + postgres + redis
├── Dockerfile                    # Python 3.12 slim image
├── pyproject.toml                # Dependencies + project metadata
├── alembic.ini                   # Alembic config
├── Makefile                      # Dev commands (up, down, migrate, test, logs)
├── start_local.py                # Local dev runner
├── sample_inventory.csv          # 7 sample vehicles
├── README.md                     # Documentation
└── .env.example                  # Environment variable template
```

## Key Files by Role

### Entry Points
| File | Purpose |
|------|---------|
| `src/main.py` | FastAPI app creation, middleware, routers, startup hook |
| `start_local.py` | `uvicorn.run()` for local dev |
| `src/tasks/celery_app.py` | Celery worker setup |

### Core Business Logic
| File | Lines | Purpose |
|------|-------|---------|
| `conversation_engine.py` | ~500 | State machine — THE core of the product |
| `orchestrator.py` | ~278 | LLM-aware wrapper, debug mode |
| `intent.py` | — | Regex-based intent classification |
| `entities.py` | — | NER: brand, model, year, budget, name, time |
| `inventory.py` | — | Filtered search with fallback strategies |

### Configuration Chain
```
.env → Pydantic Settings (config.py) → settings singleton → imported everywhere
docker-compose.yml → env vars → .env
```

## Module Dependencies

```
main.py
  ├── config.py (settings)
  ├── routes/admin.py → db/models, db/session
  ├── routes/admin_ui.py → services/orchestrator → services/llm_service
  │                                              → services/deterministic_responder
  │                                              → services/visit_confirmation
  │                                              → services/lead_service
  ├── routes/webhook_cloud.py → services/conversation_engine → services/intent
  │                                                           → services/entities
  │                                                           → services/inventory
  │                                                           → services/responder
  │                                                           → services/handoff_rules
  │                                                           → services/lead_service
  │                           → adapters/whatsapp_cloud
  ├── routes/webhook_ml.py → adapters/mercadolibre
  ├── routes/import_routes.py → tasks/import_tasks
  └── routes/celery_routes.py → tasks/celery_app
```

## Where to Add New Code

| Type | Location |
|------|----------|
| New API endpoint | `src/api/routes/` — new file or extend existing |
| New service | `src/services/` — new file, import from routes |
| New external API | `src/adapters/` — new adapter file |
| New DB model | `src/db/models.py` + new Alembic migration |
| New background job | `src/tasks/` — register in celery_app |
| New admin page | `src/templates/admin/` + route in `admin_ui.py` |
| New intent | `src/services/intent.py` — add patterns + constant |
| New entity type | `src/services/entities.py` — add extractor |
