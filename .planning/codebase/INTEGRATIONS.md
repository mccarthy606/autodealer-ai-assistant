# External Integrations

**Analysis Date:** 2026-03-27

## APIs & External Services

### OpenAI (LLM)

- **Purpose:** AI-powered conversation responses with tool/function calling
- **SDK/Client:** `openai` Python SDK (`AsyncOpenAI`)
- **Implementation:** `src/services/llm_service.py`
- **Model:** Configurable via `OPENAI_MODEL` env var, default `gpt-4o-mini`
- **Auth:** API key via `OPENAI_API_KEY` env var
- **Optional:** System works fully without it (`LLM_ENABLED=false`). Deterministic responder handles conversations when LLM is disabled.
- **Features used:**
  - Chat completions with function calling (tools)
  - 3 tool definitions: `search_inventory`, `create_lead`, `handoff_to_manager`
  - Temperature: 0.3, max_tokens: 200
  - Max 5 tool-call iterations per message
  - System prompt in Argentine Spanish

### WhatsApp Business Cloud API (Meta)

- **Purpose:** Receive and send WhatsApp messages to car dealership customers
- **SDK/Client:** Direct HTTP via `httpx` (no official SDK)
- **Implementation:**
  - Adapter: `src/adapters/whatsapp_cloud.py` (class `WhatsAppCloudAdapter`)
  - Webhook routes: `src/api/routes/webhook_cloud.py`
  - Legacy Twilio-compatible webhook: `src/api/routes/webhooks.py` + `src/webhooks/whatsapp.py`
- **Base URL:** `https://graph.facebook.com/v18.0`
- **Auth:** Bearer token via `WHATSAPP_CLOUD_TOKEN` env var
- **Env vars:**
  - `WHATSAPP_CLOUD_TOKEN` - Meta API access token
  - `WHATSAPP_PHONE_NUMBER_ID` - Phone number ID for sending
  - `WHATSAPP_VERIFY_TOKEN` - Webhook verification token
  - `WHATSAPP_WEBHOOK_SECRET` - Signature verification secret
- **Optional:** Falls back to mock mode (logs only) when tokens are empty
- **Message types supported (inbound):** text, button, interactive (button_reply, list_reply)
- **Message types supported (outbound):** text, image (with caption, max 3 images)

### MercadoLibre API

- **Purpose:** Sync vehicle listings, fetch/answer buyer questions, import inventory
- **SDK/Client:** Direct HTTP via `httpx` (no official SDK)
- **Implementation:**
  - Adapter: `src/adapters/mercadolibre.py` (class `MercadoLibreAdapter`)
  - Webhook route: `src/api/routes/webhook_ml.py`
  - Public scraping functions (no auth): `fetch_seller_items_public()`, `fetch_single_item_public()`
- **Base URL:** `https://api.mercadolibre.com`
- **Auth:** Bearer token via `ML_ACCESS_TOKEN` env var
- **Env vars:**
  - `ML_ACCESS_TOKEN` - OAuth access token
  - `ML_USER_ID` - Seller user ID
  - `ML_NICKNAME` - Seller nickname (default: "GRUPOAUTODEAL"), used for public scraping
- **Optional:** Falls back to mock mode when tokens are empty
- **API endpoints used:**
  - `GET /users/{user_id}/items/search` - List active items
  - `GET /items?ids={ids}` - Batch item details (up to 20)
  - `GET /items/{id}` - Single item details
  - `GET /items/{id}/description` - Item description
  - `GET /questions/search` - Fetch unanswered questions
  - `GET /questions/{id}` - Fetch single question details
  - `POST /answers` - Answer a question
- **HTML scraping fallback:**
  - Scrapes `listado.mercadolibre.com.ar` when API returns 403
  - Extracts: item IDs, titles, prices, photos from listing HTML
  - Fetches additional high-res photos from individual item pages
  - Parses JSON-LD structured data for images
  - User-Agent spoofing for scraping requests

### Google Sheets (CSV Import)

- **Purpose:** Import inventory from published Google Sheets
- **Implementation:** `src/tasks/import_tasks.py` (Celery task `import_from_google_sheet`)
- **SDK/Client:** `httpx` (sync client, runs in Celery worker)
- **Auth:** None (sheet must be published to web as CSV)
- **Supports:** Spanish and English column headers (brand/marca, model/modelo, year/ano, price/precio)

## Data Storage

**Primary Database: PostgreSQL 16**
- Connection env var: `DATABASE_URL`
- Async client: SQLAlchemy + asyncpg (`src/db/session.py`)
- Sync client: SQLAlchemy + psycopg2 (Celery tasks, Alembic)
- Tables: `dealerships`, `inventory_items`, `conversations`, `messages`, `leads`, `events`
- JSONB columns for flexible data: photos, tags, state, raw payloads, attachments

**Cache/Broker: Redis 7**
- Connection env var: `REDIS_URL`
- Client: `redis.asyncio` (`src/api/rate_limit.py`)
- Uses: Celery broker/backend, rate limiting (20 req/min per phone)

**File Storage:**
- None. Photos stored as URL references in JSONB columns (pointing to MercadoLibre CDN or external URLs).

## Authentication & Identity

**Admin UI Auth:**
- Custom cookie-based session auth (`src/api/auth.py`)
- Password: `ADMIN_PASSWORD` env var (plain text comparison via `secrets.compare_digest`)
- Session: In-memory set of SHA-256 hashed tokens
- Cookie: `admin_session`, httponly, samesite=lax, 24h expiry
- If `ADMIN_PASSWORD` is empty, admin is open (no auth required)

**API Auth:**
- No API key auth for webhook endpoints (relies on webhook verification tokens)
- WhatsApp webhook verification: Meta hub.verify_token challenge-response
- WhatsApp signature verification: HMAC-SHA256 (`src/webhooks/whatsapp.py`)

**External Service Auth:**
- All via Bearer tokens in Authorization header
- OpenAI: API key
- WhatsApp: Meta access token
- MercadoLibre: OAuth access token

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)

**Logs:**
- Python `logging` module, basicConfig level=INFO
- Structured log messages throughout all services
- Console output (stdout via Docker)
- No log aggregation service

**Metrics:**
- Custom admin UI metrics page: `src/templates/admin/metrics.html`
- Event tracking via `events` table in PostgreSQL (message_in, message_out, search_performed, handoff)

## CI/CD & Deployment

**Hosting:**
- Docker Compose deployment (target platform not specified)

**CI Pipeline:**
- None detected (no GitHub Actions, GitLab CI, etc.)

**Build:**
- `docker compose up -d` via `make up`
- Alembic migrations auto-run on API container start

## Notifications (Outbound)

### Email (SMTP)

- **Purpose:** Notify dealership manager on lead handoff
- **Implementation:** `src/services/notifications.py`
- **Client:** `aiosmtplib`
- **Env vars:**
  - `SMTP_HOST` - SMTP server hostname
  - `SMTP_PORT` - SMTP port (default: 587)
  - `SMTP_USER` - SMTP username
  - `SMTP_PASS` - SMTP password
  - `SMTP_TO` - Recipient email for notifications
- **Optional:** Silently skipped if SMTP not configured
- **TLS:** Enabled (`use_tls=True`)

### Manager Webhook (HTTP POST)

- **Purpose:** Push lead handoff events to external system (CRM, Slack, etc.)
- **Implementation:** `src/services/notifications.py`
- **Client:** `httpx`
- **Env var:** `MANAGER_WEBHOOK_URL`
- **Payload format:** JSON with event, lead_id, dealership_id, phone, name, summary, body
- **Optional:** Silently skipped if URL not configured

## Webhook Endpoints (Incoming)

### WhatsApp Cloud API Webhook

- **GET** `/webhooks/whatsapp_cloud` - Meta verification challenge-response
- **POST** `/webhooks/whatsapp_cloud` - Receive incoming WhatsApp messages
- **Implementation:** `src/api/routes/webhook_cloud.py`
- **Auth:** `WHATSAPP_VERIFY_TOKEN` for GET verification

### WhatsApp Legacy Webhook (Twilio-compatible)

- **POST** `/webhooks/whatsapp` - Receive WhatsApp messages (Twilio format or generic)
- **Implementation:** `src/api/routes/webhooks.py`
- **Supports:** JSON, form-encoded, Twilio-style (`From`/`Body`) and generic (`user_phone`/`message_text`) payloads
- **Auth:** HMAC-SHA256 signature verification (optional, via `WHATSAPP_WEBHOOK_SECRET`)

### MercadoLibre Webhook

- **POST** `/webhooks/mercadolibre` - Receive ML notifications (questions topic)
- **Implementation:** `src/api/routes/webhook_ml.py`
- **Behavior:** On question notification, fetches question text from ML API, processes through conversation engine, posts answer back

## Environment Variables Summary

**Required for core functionality:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/autodealer` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `DEFAULT_DEALERSHIP_ID` | Default dealership for all channels | `1` |

**Optional - OpenAI:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `""` (disabled) |
| `OPENAI_MODEL` | Model name | `gpt-4o-mini` |
| `LLM_ENABLED` | Enable LLM responses | `false` |

**Optional - WhatsApp:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `WHATSAPP_CLOUD_TOKEN` | Meta API access token | `""` (mock mode) |
| `WHATSAPP_PHONE_NUMBER_ID` | Phone number ID for sending | `""` |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification token | `""` |
| `WHATSAPP_WEBHOOK_SECRET` | Signature verification secret | `""` |

**Optional - MercadoLibre:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `ML_ACCESS_TOKEN` | OAuth access token | `""` (mock mode) |
| `ML_USER_ID` | Seller user ID | `""` |

**Optional - Notifications:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `MANAGER_WEBHOOK_URL` | HTTP webhook for handoff events | `""` |
| `SMTP_HOST` | SMTP server | `""` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `""` |
| `SMTP_PASS` | SMTP password | `""` |
| `SMTP_TO` | Notification recipient email | `""` |

**Optional - App behavior:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `ADMIN_PASSWORD` | Admin UI password (empty = no auth) | `""` |
| `FOLLOWUPS_ENABLED` | Enable follow-up messages | `false` |
| `DEFAULT_LANGUAGE` | Default bot language | `es-AR` |
| `FALLBACK_LANGUAGE` | Fallback language | `en` |

---

*Integration audit: 2026-03-27*
