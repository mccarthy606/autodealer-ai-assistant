# AutoDealer AI Assistant

## What This Is

SaaS WhatsApp-бот для автосалонов Аргентины. Автоматически общается с клиентами через WhatsApp: отвечает на вопросы об автомобилях, показывает фото и цены, создаёт лиды, записывает на визит и передаёт менеджеру когда нужно. Интегрирован с MercadoLibre для синхронизации инвентаря.

## Core Value

Бот должен корректно обрабатывать входящие WhatsApp-сообщения клиентов автосалона и вовремя передавать горячие лиды менеджерам — это то, за что платят.

## Requirements

### Validated

- ✓ Conversation engine с детерминистической стейт-машиной (NEW → BROWSING → PRESENTING → DETAILS → CLOSING → HANDOFF) — existing
- ✓ Intent detection (rule-based): search, photos, details, price, km, status, visit, financing, trade-in, greeting, human — existing
- ✓ Entity extraction: brand, model, year, budget, name, time, condition, language — existing
- ✓ WhatsApp Business Cloud API webhook (receive + send) — existing
- ✓ MercadoLibre webhook integration — existing
- ✓ Inventory search with fallback strategies — existing
- ✓ Auto lead creation on visit/financing/trade-in/human request — existing
- ✓ Bot→manager handoff (6 trigger reasons) — existing
- ✓ Multilingual responses (Spanish/English auto-detect) — existing
- ✓ Admin UI with dashboard, inventory CRUD, leads, conversations — existing
- ✓ CSV inventory import — existing
- ✓ PostgreSQL + Redis + Celery background tasks — existing
- ✓ Docker Compose deployment — existing

### Active

- [ ] Production hardening (security, CORS, webhook verification, auth)
- [ ] Рефакторинг: объединить два conversation engine, разбить admin_ui.py
- [ ] Дашборд менеджера: реал-тайм панель для подхвата лидов и ответов клиентам
- [ ] Аналитика: конверсия, время ответа, кол-во лидов, топ запросы
- [ ] Follow-up автоматика: авто-напоминания клиентам (24ч, 3 дня)
- [ ] Multi-tenancy: несколько автосалонов на одном инстансе с изоляцией данных
- [ ] Биллинг через Lemon Squeezy (подписка/месяц)
- [ ] Production deployment (VPS, TLS, reverse proxy, monitoring)

### Out of Scope

- Международная локализация — фокус только Аргентина (es-AR)
- Поддержка других мессенджеров (Telegram, Instagram) — только WhatsApp
- Мобильное приложение — только web admin
- AI-генерация описаний автомобилей — бот отвечает на вопросы, не создаёт контент
- Self-hosted вариант — только hosted SaaS

## Context

**Существующий код:** Полноценный MVP на Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16 + Redis 7. Работает в Docker Compose. Тесты на pytest + SQLite in-memory.

**Первый клиент:** Конкретный автосалон в Аргентине ждёт запуска. Это не спекуляция — реальный клиент.

**Рынок:** Аргентина, MercadoLibre как основной маркетплейс, ARS валюта, GRUPOAUTODEAL nickname.

**Технический долг (из CONCERNS.md):**
- Два параллельных conversation engine (conversation_engine.py и orchestrator.py)
- admin_ui.py — 32KB монолит
- CORS allow_all, нет webhook signature verification
- Admin auth in-memory, нет rate limiting на webhooks
- datetime.utcnow() deprecated

**Тесты:** 7 файлов, покрывают engine + intent + entities. Нет тестов для admin API, adapters, LLM service, notifications.

## Constraints

- **Stack**: Python 3.12 + FastAPI + SQLAlchemy 2.0 — не менять, всё уже написано
- **Market**: Аргентина only — es-AR, ARS, MercadoLibre
- **Timeline**: Клиент ждёт — нужен working product ASAP
- **Budget**: Один разработчик, минимальные затраты на инфраструктуру
- **Payments**: Lemon Squeezy для биллинга (monthly subscription)
- **WhatsApp**: Meta Business Cloud API (не Twilio)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Детерминистический engine без LLM по умолчанию | Надёжность > креативность, LLM опционален | — Pending |
| Lemon Squeezy для биллинга | Простая интеграция, поддержка подписок | — Pending |
| Фокус только Аргентина | Первый клиент там, не распылять ресурсы | — Pending |
| VPS deployment (Claude's discretion) | Один инстанс, Docker, дёшево для старта | — Pending |
| Monthly subscription модель | Предсказуемый доход для SaaS | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after initialization*
