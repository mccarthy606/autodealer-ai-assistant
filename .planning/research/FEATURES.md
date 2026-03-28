# Features Research — WhatsApp Car Dealership Chatbot SaaS

## Table Stakes (Must Have or Users Leave)

### Bot Conversation Quality
- **Accurate inventory search** — match customer queries to available cars ✓ EXISTS
- **Photo sharing** — send car photos via WhatsApp ✓ EXISTS
- **Multilingual** — at least Spanish + English ✓ EXISTS
- **Bot→human handoff** — seamless transfer when bot can't help ✓ EXISTS
- **Lead auto-creation** — capture every potential buyer ✓ EXISTS

### Manager Experience
- **Real-time lead notifications** — instant alert when hot lead arrives (PARTIAL — webhook/email exists, no real-time dashboard)
- **Conversation takeover** — manager can reply through the platform (MISSING — handoff exists but no reply UI)
- **Conversation history** — see full chat context before responding (PARTIAL — exists in admin but not optimized)
- **Lead management** — view, qualify, assign leads (PARTIAL — basic CRUD exists)

### Operations
- **Inventory management** — add/edit/remove cars (✓ EXISTS — admin UI + CSV import)
- **Uptime reliability** — bot must respond 24/7 (MISSING — no monitoring, no auto-restart in production)
- **WhatsApp compliance** — respect Meta policies on message templates, 24h window (PARTIALLY — needs template messages)

### Security & Data
- **Data isolation** — one dealership can't see another's data (MISSING for multi-tenant)
- **Secure admin access** — proper authentication (WEAK — in-memory sessions, plaintext password)
- **Webhook verification** — prevent fake messages (MISSING)

## Differentiators (Competitive Advantage)

### Follow-Up Automation
- Auto-reminder to customers who went silent (24h, 3d, 7d)
- Re-engagement with new inventory matching their preferences
- Visit confirmation day-of
- **Complexity: Medium** — needs Celery Beat + WhatsApp template messages

### Analytics Dashboard
- Conversion funnel: messages → leads → visits → sales
- Response time metrics
- Top searched brands/models
- Bot effectiveness (% handled without handoff)
- **Complexity: Medium** — SQL aggregations + charting

### Smart Responses
- LLM-enhanced replies for more natural conversation
- Context-aware responses based on conversation history
- **Complexity: Low** — OpenAI integration already partially built

### Multi-Channel
- MercadoLibre message integration (beyond just inventory sync)
- WhatsApp Business template messages for proactive outreach
- **Complexity: High** — ML messaging API is different from inventory API

## Anti-Features (Deliberately NOT Build)

| Anti-Feature | Reason |
|-------------|--------|
| Customer mobile app | WhatsApp IS the customer interface |
| AI car valuation | Not core business, high liability |
| CRM replacement | Integrate with existing CRMs, don't replace them |
| Payment processing for car purchases | Cars are sold in person |
| Automated price negotiation | Dealerships want human control on pricing |
| Social media posting | Out of scope — different product entirely |
| Multi-language beyond es/en | Argentina market only |

## Feature Dependencies

```
Webhook verification → Production deployment (prerequisite)
Multi-tenancy → Manager dashboard (needs tenant isolation first)
Follow-up automation → WhatsApp template messages (Meta approval needed)
Analytics → Data accumulation (needs traffic to be meaningful)
Billing → Multi-tenancy (billing per tenant)
```
