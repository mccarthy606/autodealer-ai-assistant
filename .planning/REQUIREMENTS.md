# Requirements: AutoDealer AI Assistant

**Defined:** 2026-03-27
**Core Value:** Бот ловит лиды с MercadoLibre, пишет клиенту в WhatsApp первым и закрывает на визит в автосалон.

## v1 Requirements

### Outbound Flow (Core Business)
- [ ] **OUT-01**: Система мониторит входящие заявки с MercadoLibre в реальном времени
- [ ] **OUT-02**: Система определяет конкретную машину, которой заинтересовался клиент
- [ ] **OUT-03**: Система автоматически пишет клиенту в WhatsApp первой с информацией о машине
- [ ] **OUT-04**: Бот ведёт диалог по скрипту с целью закрыть на визит в автосалон
- [ ] **OUT-05**: При подтверждении визита — создаётся лид и уведомляется менеджер

### Conversation Engine (Inbound — уже есть, доработать)
- [ ] **ENG-01**: Единый движок разговоров для всех каналов (merge двух engine)
- [ ] **ENG-02**: Стейт-машина корректно обрабатывает все интенты (search, photos, details, visit, financing, trade-in, human)
- [ ] **ENG-03**: Multilingual ответы (es-AR / en) с авто-определением языка
- [ ] **ENG-04**: Message deduplication по WhatsApp message ID (wamid)

### Follow-Up Automation
- [ ] **FUP-01**: Авто-напоминание клиенту через 24 часа если не ответил
- [ ] **FUP-02**: Повторное напоминание через 3 дня если всё ещё молчит
- [ ] **FUP-03**: Follow-up через WhatsApp template messages (не free-form — требование Meta)
- [ ] **FUP-04**: Максимум 2-3 follow-up на разговор, потом стоп
- [ ] **FUP-05**: Уважать opt-out (клиент сказал "нет" → прекратить)

### Multi-Tenancy
- [ ] **MT-01**: Несколько автосалонов на одном инстансе с полной изоляцией данных
- [ ] **MT-02**: Tenant middleware — автоматическое определение dealership из контекста запроса
- [ ] **MT-03**: Маппинг WhatsApp phone_number_id → dealership для роутинга вебхуков
- [ ] **MT-04**: Redis ключи с tenant-prefix для изоляции кэша

### Admin Dashboard & Analytics
- [ ] **DASH-01**: Личный кабинет автосалона с обзором активности
- [ ] **DASH-02**: Статистика: кол-во лидов, конверсия в визиты, время ответа
- [ ] **DASH-03**: Топ запрашиваемых марок/моделей
- [ ] **DASH-04**: Список всех диалогов с историей сообщений
- [ ] **DASH-05**: Список лидов с фильтрацией по статусу

### Billing (Lemon Squeezy)
- [ ] **BILL-01**: Subscription model (план → tenant → статус)
- [ ] **BILL-02**: Lemon Squeezy webhook handler для lifecycle событий
- [ ] **BILL-03**: Проверка активной подписки перед обработкой сообщений
- [ ] **BILL-04**: Grace period при проблемах с оплатой

### Security & Hardening
- [x] **SEC-01**: CORS ограничен конкретными доменами (не wildcard)
- [ ] **SEC-02**: Admin auth через Redis-сессии с хешированием паролей (bcrypt)
- [x] **SEC-03**: Lemon Squeezy webhook signature verification
- [x] **SEC-04**: Rate limiting на webhook endpoints

### Refactoring
- [x] **REF-01**: Объединить conversation_engine.py и orchestrator.py в единый движок
- [ ] **REF-02**: Разбить admin_ui.py (32KB) на модули по функциональности
- [ ] **REF-03**: Заменить datetime.utcnow() на datetime.now(UTC)

### Production Deployment
- [ ] **DEP-01**: Docker Compose production profile (без --reload, с workers)
- [ ] **DEP-02**: Caddy reverse proxy с автоматическим TLS
- [ ] **DEP-03**: Sentry для мониторинга ошибок
- [ ] **DEP-04**: PostgreSQL backup (pg_dump daily)
- [ ] **DEP-05**: Health check endpoint с проверкой зависимостей
- [ ] **DEP-06**: Alembic миграции отдельно от app startup

## v2 Requirements

### Manager Real-Time Dashboard
- **MGR-01**: SSE для real-time обновлений диалогов
- **MGR-02**: Менеджер может ответить клиенту прямо из дашборда через WhatsApp
- **MGR-03**: Очередь лидов с назначением на менеджеров

### Advanced Analytics
- **ANA-01**: Воронка конверсии: лид ML → контакт WA → визит → сделка
- **ANA-02**: ROI-метрики по каждому автосалону
- **ANA-03**: A/B тестирование скриптов бота

### Integrations
- **INT-01**: MercadoLibre messaging (не только inventory)
- **INT-02**: CRM интеграция (export лидов)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Мобильное приложение | WhatsApp = клиентский интерфейс, админка через web |
| Другие мессенджеры (Telegram, Instagram) | Фокус на WhatsApp для Аргентины |
| Международная локализация | Только Аргентина (es-AR) |
| AI-генерация описаний машин | Бот общается, не создаёт контент |
| Онлайн-оплата за машины | Сделки закрываются физически |
| Автоматическое ценообразование | Салоны хотят человеческий контроль цен |
| Self-hosted вариант | Только hosted SaaS |
| React/Vue SPA | HTMX + Jinja2 проще и быстрее для v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REF-01 | Phase 1 | Complete |
| REF-02 | Phase 1 | Pending |
| REF-03 | Phase 1 | Pending |
| SEC-01 | Phase 2 | Pending |
| SEC-02 | Phase 2 | Pending |
| SEC-03 | Phase 2 | Pending |
| SEC-04 | Phase 2 | Pending |
| ENG-01 | Phase 3 | Pending |
| ENG-02 | Phase 3 | Pending |
| ENG-03 | Phase 3 | Pending |
| ENG-04 | Phase 3 | Pending |
| OUT-01 | Phase 4 | Pending |
| OUT-02 | Phase 4 | Pending |
| OUT-03 | Phase 4 | Pending |
| OUT-04 | Phase 4 | Pending |
| OUT-05 | Phase 4 | Pending |
| FUP-01 | Phase 5 | Pending |
| FUP-02 | Phase 5 | Pending |
| FUP-03 | Phase 5 | Pending |
| FUP-04 | Phase 5 | Pending |
| FUP-05 | Phase 5 | Pending |
| MT-01 | Phase 6 | Pending |
| MT-02 | Phase 6 | Pending |
| MT-03 | Phase 6 | Pending |
| MT-04 | Phase 6 | Pending |
| DASH-01 | Phase 7 | Pending |
| DASH-02 | Phase 7 | Pending |
| DASH-03 | Phase 7 | Pending |
| DASH-04 | Phase 7 | Pending |
| DASH-05 | Phase 7 | Pending |
| BILL-01 | Phase 8 | Pending |
| BILL-02 | Phase 8 | Pending |
| BILL-03 | Phase 8 | Pending |
| BILL-04 | Phase 8 | Pending |
| DEP-01 | Phase 9 | Pending |
| DEP-02 | Phase 9 | Pending |
| DEP-03 | Phase 9 | Pending |
| DEP-04 | Phase 9 | Pending |
| DEP-05 | Phase 9 | Pending |
| DEP-06 | Phase 9 | Pending |
