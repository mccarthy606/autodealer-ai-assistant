# Pitfalls Research — WhatsApp Car Dealership SaaS

## Critical Pitfalls

### P1: WhatsApp 24-Hour Window Violation
**Risk:** Meta enforces a 24-hour messaging window. After 24h of no customer message, you can ONLY send pre-approved template messages. Violating this gets your number banned.

**Warning signs:** Follow-up messages failing silently, "error 131047" in Meta API responses.

**Prevention:**
- Track `last_customer_message_at` per conversation
- Follow-ups MUST use template messages (not free-form text)
- Submit templates to Meta for approval BEFORE building follow-up feature
- Rate limit outbound messages per phone number

**Phase:** Follow-Up Automation — must be designed around this constraint from day 1.

### P2: Multi-Tenancy Data Leaks
**Risk:** Without proper tenant isolation, one dealership could see another's customers, inventory, or conversations. Lawsuit-grade problem.

**Warning signs:** Missing `WHERE dealership_id = ?` in any query. Shared Redis keys without tenant prefix.

**Prevention:**
- SQLAlchemy session-level filter (automatically add `dealership_id` to all queries)
- Test with 2+ dealerships in dev from the start
- Redis key prefix: `tenant:{dealership_id}:*`
- Never pass `dealership_id` from client — always resolve from auth context

**Phase:** Multi-Tenancy — this is the entire point of that phase.

### P3: Webhook Replay Attacks
**Risk:** Without signature verification, anyone who discovers your webhook URL can send fake messages, create fake leads, or DoS your system.

**Warning signs:** Unexplained conversations, leads from unknown numbers, webhook traffic spikes.

**Prevention:**
- Verify `X-Hub-Signature-256` on every Meta webhook request (HMAC-SHA256)
- Verify Lemon Squeezy webhook signatures
- Idempotency: deduplicate by `message_id` (Meta sends duplicates)
- Rate limit per phone number

**Phase:** Security Hardening — must be Phase 1.

### P4: Two Engine Divergence
**Risk:** `conversation_engine.py` and `orchestrator.py` handle the same use case differently. Features added to one won't appear in the other. Bugs fixed in one persist in the other.

**Warning signs:** "It works in admin test but not in WhatsApp" or vice versa.

**Prevention:**
- Merge into single engine BEFORE adding features
- Single `process_message()` entry point for all channels
- Test through both webhook and admin paths

**Phase:** Refactoring — must be early to avoid compounding the problem.

### P5: In-Memory Session Loss
**Risk:** Current admin auth uses `_admin_sessions: set[str]` in memory. Any restart logs out all admins. With multiple workers, sessions aren't shared.

**Warning signs:** Admins randomly logged out, sessions not working after deploy.

**Prevention:**
- Move sessions to Redis (simple key-value, TTL-based)
- Or use JWT tokens (stateless, no server storage)
- Hash passwords (bcrypt), don't store plaintext

**Phase:** Security Hardening.

## High-Priority Pitfalls

### P6: Lemon Squeezy Webhook Reliability
**Risk:** Payment webhooks can fail, be delayed, or arrive out of order. If you miss a "subscription_cancelled" webhook, you keep serving a non-paying customer.

**Prevention:**
- Store webhook events with idempotency keys
- Periodic reconciliation job (poll Lemon Squeezy API to verify subscription status)
- Grace period (don't cut off immediately on missed webhook)

**Phase:** Billing.

### P7: Follow-Up Spam
**Risk:** Sending too many follow-ups annoys customers and violates WhatsApp policies. Too aggressive = number gets reported and banned.

**Prevention:**
- Max 2-3 follow-ups per conversation
- Respect opt-out (customer says "no" → stop)
- Cool-down period between follow-ups (minimum 24h)
- Track follow-up count per conversation

**Phase:** Follow-Up Automation.

### P8: Admin UI Monolith (32KB)
**Risk:** `admin_ui.py` at 32KB is already painful. Adding manager dashboard, analytics, and billing UI to the same file makes it unmaintainable.

**Prevention:**
- Split into route modules BEFORE adding new UI
- Separate: `admin_inventory.py`, `admin_leads.py`, `admin_conversations.py`, `manager_dashboard.py`, `admin_analytics.py`, `admin_billing.py`

**Phase:** Refactoring.

### P9: Missing Message Deduplication
**Risk:** Meta sends duplicate webhook payloads (at-least-once delivery). Without dedup, customer messages are processed twice → duplicate bot replies.

**Prevention:**
- Store `wamid` (WhatsApp message ID) in Message model
- Check for existing `wamid` before processing
- Unique constraint on `wamid` column

**Phase:** Security Hardening.

## Medium-Priority Pitfalls

### P10: No Database Backup
**Risk:** Losing customer data, conversation history, inventory = business-ending for the client.

**Prevention:**
- `pg_dump` cron job (daily minimum)
- Store backups off-server (S3 or similar)
- Test restore procedure

**Phase:** Production Deployment.

### P11: Sync Alembic on Startup
**Risk:** Running migrations on app startup can cause race conditions with multiple workers and slow startup times.

**Prevention:**
- Run migrations in a separate init container or entrypoint script
- Not in `@app.on_event("startup")`

**Phase:** Production Deployment.

### P12: No Health Monitoring
**Risk:** Bot goes down, nobody notices until customer complains. Lost leads = lost money for the client.

**Prevention:**
- Sentry for error tracking
- Health check endpoint with dependency checks (DB, Redis, WhatsApp API)
- External uptime monitoring (UptimeRobot, Better Uptime)
- Alert to owner on failures

**Phase:** Production Deployment.
