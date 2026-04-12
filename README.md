<div align="center">

# AutoDealer AI Assistant

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)
![CI](https://img.shields.io/github/actions/workflow/status/mccarthy606/autodealer-ai-assistant/ci.yml?style=flat-square&label=CI)

**AI-powered inventory assistant for car dealerships in Argentina.**
Manages conversations via WhatsApp and MercadoLibre, handles inventory, auto-creates leads, and hands off to managers when needed.

Works fully without LLM (deterministic mode). LLM is optional and only improves phrasing.

</div>

---

## Quick Start

```bash
docker compose up -d --build
```

Open **http://localhost:8000/admin/ui** — add a car, test the bot.

<details>
<summary><b>Step-by-step setup</b></summary>

### 1. Start services
```bash
docker compose up -d --build
```
Wait 15-20 seconds for Postgres to start and migrations to run.

### 2. Configure your dealership
Go to **Settings** → fill in address and business hours.

### 3. Add a car
Go to **Cars** → **+ Add car** → fill brand, model, year, price, photos → Save.

### 4. Test the bot
Go to **Test Bot** and try:
1. `Hi, do you have Hilux?` → Bot responds with car options
2. `Can you send photos?` → Bot sends photo URLs
3. `I want to come tomorrow. My name is Juan.` → Bot confirms, creates lead, switches to MANAGER mode

### 5. Optional: WhatsApp / MercadoLibre
Set environment variables in `.env` and restart.

</details>

## Conversation Engine

Deterministic state machine — no LLM required:

```
NEW → BROWSING → PRESENTING → DETAILS → CLOSING → HANDOFF
```

**Auto handoff rules:** human request, financing, trade-in, visit scheduling, missing photos, bot unhelpful twice.

**Multilingual:** auto-detects Spanish/English.

## Architecture

```
src/
├── main.py                     # FastAPI entry point
├── api/routes/                 # Admin UI, webhooks, debug
├── services/
│   ├── conversation_engine.py  # State machine
│   ├── intent.py               # Rule-based intent detection
│   ├── inventory.py            # Search engine
│   └── lead_service.py         # Lead creation
├── adapters/
│   ├── whatsapp_cloud.py       # WhatsApp Cloud API
│   └── mercadolibre.py         # MercadoLibre API
└── templates/                  # Jinja2 admin UI
```

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI + Uvicorn |
| UI | Jinja2 templates |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Queue | Redis 7 + Celery |
| Migrations | Alembic |
| Deploy | Docker Compose + Caddy |
| Security | Fernet encryption for credentials |

## Running Tests

```bash
pytest tests/ -v
```
