# AutoDealer AI Assistant

AI-powered inventory assistant for car dealerships in Argentina. Manages conversations via WhatsApp and MercadoLibre, handles inventory, auto-creates leads, and hands off to managers when needed.

**Works fully without LLM** (deterministic mode). LLM is optional and only improves phrasing.

## Quick start (2 minutes)

### 1. Start services

```bash
docker compose up -d --build
```

Wait 15-20 seconds for Postgres to start and migrations to run.

### 2. Open admin panel

Go to **http://localhost:8000/admin/ui**

### 3. Configure your dealership

Go to **Settings** → fill in:
- Address (e.g. "Av. Libertador 1234, CABA")
- Business hours (e.g. "Lun-Vie 9-18, Sab 9-13")

### 4. Add a car

Go to **Cars** → **+ Add car**:
- Brand: Toyota
- Model: Hilux
- Year: 2023
- Price: 18000000
- Photos (paste URLs, one per line):
  ```
  https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/2021_Toyota_Hilux_Invincible_2.8_Front.jpg/1280px-2021_Toyota_Hilux_Invincible_2.8_Front.jpg
  https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/2020_Toyota_Hilux_Invincible_X_D-4D_2.8_Rear.jpg/1280px-2020_Toyota_Hilux_Invincible_X_D-4D_2.8_Rear.jpg
  ```
- Click **Save car**

### 5. Test the bot

Go to **Test Bot** and try this conversation:

1. `Hi, do you have Hilux?` → Bot responds in **English** with car options
2. `Can you send photos?` → Bot sends photo URLs/previews
3. `I want to come tomorrow morning. My name is Juan.` → Bot confirms visit, **creates lead**, switches to **MANAGER mode**

### 6. Check results

- **Leads** → Lead exists with intent "Visit", name "Juan"
- **Conversations** → Badge shows **MANAGER ACTIVE** + reason "Visit scheduling"
- **Metrics** → Shows conversations, leads, searches

### 7. Optional: WhatsApp / MercadoLibre

Set environment variables in `.env`:

```bash
# WhatsApp Business Cloud API
WHATSAPP_CLOUD_TOKEN=your_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_VERIFY_TOKEN=your_verify_token

# MercadoLibre
ML_ACCESS_TOKEN=your_token
ML_USER_ID=your_seller_id
```

Restart: `docker compose restart api`

Webhook endpoints:
- WhatsApp: `POST /webhooks/whatsapp_cloud`
- MercadoLibre: `POST /webhooks/mercadolibre`

## Architecture

```
src/
├── main.py                     # FastAPI entry point
├── config.py                   # Environment config
├── db/
│   ├── models.py               # SQLAlchemy models
│   └── session.py              # Database sessions
├── api/routes/
│   ├── admin.py                # REST API
│   ├── admin_ui.py             # Admin UI (Jinja2)
│   ├── webhook_cloud.py        # WhatsApp Cloud webhook
│   ├── webhook_ml.py           # MercadoLibre webhook
│   └── debug_routes.py         # Debug endpoint
├── services/
│   ├── conversation_engine.py  # Main engine (state machine)
│   ├── intent.py               # Rule-based intent detection
│   ├── entities.py             # Entity extraction
│   ├── handoff_rules.py        # Auto handoff rules
│   ├── responder.py            # Multilingual responses
│   ├── inventory.py            # Inventory search
│   └── lead_service.py         # Lead creation
├── adapters/
│   ├── whatsapp_cloud.py       # WhatsApp Cloud API
│   └── mercadolibre.py         # MercadoLibre API
├── templates/                  # Jinja2 HTML templates
└── static/admin.css            # Admin UI styles
```

## Conversation engine

The bot uses a **deterministic state machine** (no LLM required):

**Stages:** NEW → BROWSING → PRESENTING → DETAILS → CLOSING → HANDOFF

**Intents detected:**
- SEARCH_CAR, ASK_PHOTOS, ASK_DETAILS, ASK_PRICE
- VISIT, FINANCING, TRADE_IN
- HUMAN (explicit request for salesperson)

**Auto handoff rules:**
1. Customer asks for human → manager
2. Financing inquiry → manager
3. Trade-in inquiry → manager
4. Visit scheduling → manager (after lead creation)
5. Photos missing → manager
6. Bot unhelpful twice → manager

**Multilingual:** Bot auto-detects language (Spanish/English) and responds accordingly.

## Running tests

```bash
# Install dev dependencies
pip install aiosqlite

# Run tests
pytest tests/ -v
```

## Tech stack

- **FastAPI** + **Jinja2** (Admin UI)
- **PostgreSQL** + **SQLAlchemy 2.0** (async)
- **Redis** + **Celery** (background tasks)
- **Alembic** (migrations)
- **Docker Compose** (deployment)

## License

Private — for dealership use.
