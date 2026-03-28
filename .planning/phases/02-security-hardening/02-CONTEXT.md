# Phase 2: Security Hardening - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Harden security: lock down CORS, replace in-memory admin auth with Redis sessions + bcrypt, add Lemon Squeezy webhook signature verification, enforce rate limiting on webhook endpoints. No new features — pure security improvement.

</domain>

<decisions>
## Implementation Decisions

### CORS (SEC-01)
- **D-01:** Replace `allow_origins=["*"]` with explicit whitelist in `main.py`. Whitelist configurable via `ALLOWED_ORIGINS` env var (comma-separated). Default: empty (deny all cross-origin in production).

### Admin Auth (SEC-02)
- **D-02:** Move sessions from in-memory `set[str]` to Redis with TTL (24h). Key pattern: `admin:session:{token_hash}`.
- **D-03:** Hash admin passwords with bcrypt. Store hashed password in `ADMIN_PASSWORD_HASH` env var. Keep backward compat: if `ADMIN_PASSWORD` (plaintext) is set and `ADMIN_PASSWORD_HASH` is not, auto-hash on first use and warn in logs.
- **D-04:** Add `secure=True` to session cookie in production (when not localhost).

### Webhook Signature Verification (SEC-03)
- **D-05:** Lemon Squeezy webhooks: verify HMAC-SHA256 signature from `X-Signature` header using `LEMON_SQUEEZY_WEBHOOK_SECRET` env var. Reject if invalid.
- **D-06:** Note: WhatsApp webhook verification (Meta X-Hub-Signature-256) is deferred — it's not in SEC requirements. Can be added in Phase 4 (Outbound Flow) where webhooks are critical.

### Rate Limiting (SEC-04)
- **D-07:** Apply existing `check_rate_limit()` from `rate_limit.py` to WhatsApp webhook endpoint. Default: 20 requests per 60 seconds per phone number.
- **D-08:** Add rate limiting to admin login endpoint: 5 attempts per 60 seconds per IP. Prevents brute force.
- **D-09:** Return HTTP 429 with `Retry-After` header when rate limited.

### Claude's Discretion
- Redis connection reuse (use existing `get_redis()` from rate_limit.py)
- bcrypt library choice (use `bcrypt` package — standard, already available in Python ecosystem)
- Error response format for rejected requests

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current Security Code
- `src/api/auth.py` — Current admin auth (in-memory sessions, plaintext password check)
- `src/api/rate_limit.py` — Existing rate limiter (Redis-based, not wired to routes)
- `src/main.py` — CORS middleware config (allow_origins=["*"])
- `src/config.py` — Settings (env vars)

### Codebase Context
- `.planning/codebase/CONCERNS.md` — Security concerns section (11 items)
- `.planning/codebase/ARCHITECTURE.md` — Request flow, middleware patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `rate_limit.py:check_rate_limit()` — Already implemented, Redis-based, just needs to be called from routes
- `rate_limit.py:get_redis()` — Redis connection singleton, reusable for sessions
- `auth.py:_hash_token()` — SHA256 token hashing, already used for session tokens
- `auth.py:_make_token()` — Secure token generation via `secrets.token_hex()`

### Established Patterns
- Pydantic Settings for env vars — add new vars to `config.py`
- FastAPI middleware for cross-cutting concerns — CORS is already middleware
- `Depends(get_db)` for route dependencies — can add rate limit as dependency

### Integration Points
- `main.py` — CORS middleware (modify origins)
- `auth.py` — Session management (switch to Redis)
- Webhook routes — Add rate limit dependency
- `admin_dashboard.py` — Login route (add rate limit + bcrypt)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — all decisions delegated to Claude. Standard security best practices.

</specifics>

<deferred>
## Deferred Ideas

- WhatsApp Meta X-Hub-Signature-256 verification — belongs in Phase 4 (Outbound Flow)
- API key auth for external integrations — future phase
- Two-factor authentication for admin — v2

</deferred>

---

*Phase: 02-security-hardening*
*Context gathered: 2026-03-27*
