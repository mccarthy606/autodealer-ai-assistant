# Phase 2: Security Hardening - Research

**Researched:** 2026-03-27
**Domain:** Web application security (CORS, auth, webhook verification, rate limiting)
**Confidence:** HIGH

## Summary

Phase 2 hardens the existing AutoDealer AI Assistant against common attack vectors across four areas: CORS restriction, admin authentication upgrade, Lemon Squeezy webhook signature verification, and rate limiting on webhook endpoints. The existing codebase provides strong foundations -- Redis-based rate limiting (`rate_limit.py`) is already implemented but unwired, session management (`auth.py`) has clean abstractions ready for Redis migration, and bcrypt 5.0.0 is already installed in the environment.

All four requirements are well-scoped security improvements with no architectural changes. The work is primarily modifying existing modules (`auth.py`, `main.py`, `config.py`, `rate_limit.py`) and adding a new Lemon Squeezy webhook route. The `redis.asyncio` client is already in use for rate limiting, so extending it to session storage is straightforward.

**Primary recommendation:** Implement changes in dependency order -- config.py additions first, then CORS (independent), then auth (Redis sessions + bcrypt), then webhook signature verification (new route), then rate limiting wiring (touches multiple routes).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Replace `allow_origins=["*"]` with explicit whitelist in `main.py`. Whitelist configurable via `ALLOWED_ORIGINS` env var (comma-separated). Default: empty (deny all cross-origin in production).
- **D-02:** Move sessions from in-memory `set[str]` to Redis with TTL (24h). Key pattern: `admin:session:{token_hash}`.
- **D-03:** Hash admin passwords with bcrypt. Store hashed password in `ADMIN_PASSWORD_HASH` env var. Keep backward compat: if `ADMIN_PASSWORD` (plaintext) is set and `ADMIN_PASSWORD_HASH` is not, auto-hash on first use and warn in logs.
- **D-04:** Add `secure=True` to session cookie in production (when not localhost).
- **D-05:** Lemon Squeezy webhooks: verify HMAC-SHA256 signature from `X-Signature` header using `LEMON_SQUEEZY_WEBHOOK_SECRET` env var. Reject if invalid.
- **D-06:** WhatsApp Meta X-Hub-Signature-256 verification is deferred to Phase 4.
- **D-07:** Apply existing `check_rate_limit()` to WhatsApp webhook endpoint. Default: 20 requests per 60 seconds per phone number.
- **D-08:** Add rate limiting to admin login endpoint: 5 attempts per 60 seconds per IP.
- **D-09:** Return HTTP 429 with `Retry-After` header when rate limited.

### Claude's Discretion
- Redis connection reuse (use existing `get_redis()` from rate_limit.py)
- bcrypt library choice (use `bcrypt` package -- standard, already available in Python ecosystem)
- Error response format for rejected requests

### Deferred Ideas (OUT OF SCOPE)
- WhatsApp Meta X-Hub-Signature-256 verification -- belongs in Phase 4
- API key auth for external integrations -- future phase
- Two-factor authentication for admin -- v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | CORS restricted to specific domains (not wildcard) | D-01: Replace `allow_origins=["*"]` with env-configurable whitelist. FastAPI CORSMiddleware supports list of origins natively. |
| SEC-02 | Admin auth via Redis sessions with bcrypt password hashing | D-02, D-03, D-04: Migrate `_admin_sessions: set[str]` to Redis SET/GET with TTL. bcrypt 5.0.0 already installed. Cookie secure flag conditional on environment. |
| SEC-03 | Lemon Squeezy webhook signature verification | D-05: New webhook route with HMAC-SHA256 verification. No existing LS webhook code -- must create from scratch. |
| SEC-04 | Rate limiting on webhook endpoints | D-07, D-08, D-09: Wire existing `check_rate_limit()` to WhatsApp routes. Add IP-based variant for login. Return 429 + Retry-After. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| bcrypt | 5.0.0 (installed) | Password hashing | Industry standard for password hashing, already in environment |
| redis[asyncio] | 5.0+ (installed) | Session storage + rate limiting | Already used by rate_limit.py, extends naturally to sessions |
| FastAPI CORSMiddleware | built-in | CORS enforcement | Already configured in main.py, just needs origin restriction |
| hmac + hashlib (stdlib) | Python 3.12 | Webhook signature verification | Standard library, no extra dependency needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| secrets (stdlib) | Python 3.12 | Token generation | Already used in auth.py for session tokens |
| logging (stdlib) | Python 3.12 | Security event logging | Warn on plaintext password usage, log rejected requests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| bcrypt (direct) | passlib[bcrypt] | passlib adds abstraction layer but is unnecessary overhead for single-algorithm use. Direct bcrypt is simpler and already installed. |
| Redis sessions | itsdangerous signed cookies | Redis allows server-side session invalidation; signed cookies cannot be revoked. Redis is the correct choice per D-02. |

**No new dependencies required.** bcrypt 5.0.0 is already installed. All other needs are met by stdlib or existing packages.

## Architecture Patterns

### Files to Modify
```
src/
  config.py                     # Add new env vars (ALLOWED_ORIGINS, ADMIN_PASSWORD_HASH, LEMON_SQUEEZY_WEBHOOK_SECRET)
  main.py                       # CORS whitelist from settings
  api/
    auth.py                     # Redis sessions + bcrypt password check
    rate_limit.py               # Add generic rate_limit_check() + IP-based variant
    routes/
      webhook_cloud.py          # Wire rate limiting
      webhooks.py               # Wire rate limiting (legacy Twilio route)
      admin_dashboard.py        # Wire login rate limiting
      webhook_lemon.py          # NEW: Lemon Squeezy webhook with signature verification
```

### Pattern 1: Redis Session Storage
**What:** Replace in-memory `set[str]` with Redis keys having TTL
**When to use:** Any server-side session that must survive restarts

```python
# Key pattern: admin:session:{sha256_of_token}
# TTL: 86400 seconds (24 hours)

async def create_session(response: Response) -> None:
    token = _make_token()
    token_hash = _hash_token(token)
    r = await get_redis()
    if r:
        await r.set(f"admin:session:{token_hash}", "1", ex=86400)
    else:
        _admin_sessions.add(token_hash)  # fallback if Redis unavailable
    secure = not _is_localhost()
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, samesite="lax",
        max_age=86400, secure=secure,
    )

async def is_authenticated(session: Optional[str] = None) -> bool:
    if not settings.admin_password and not settings.admin_password_hash:
        return True
    if not session:
        return False
    token_hash = _hash_token(session)
    r = await get_redis()
    if r:
        return await r.exists(f"admin:session:{token_hash}") > 0
    return token_hash in _admin_sessions
```

**Important:** `is_authenticated` becomes async. All callers must be updated.

### Pattern 2: bcrypt Password Verification with Backward Compat
**What:** Check password against bcrypt hash, with auto-hash fallback for plaintext
**When to use:** D-03 specifies backward compatibility

```python
import bcrypt

def _check_password(password: str) -> bool:
    if settings.admin_password_hash:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            settings.admin_password_hash.encode("utf-8"),
        )
    if settings.admin_password:
        logger.warning(
            "ADMIN_PASSWORD (plaintext) is set without ADMIN_PASSWORD_HASH. "
            "Generate a hash: python -c \"import bcrypt; print(bcrypt.hashpw(b'PASSWORD', bcrypt.gensalt()).decode())\""
        )
        return secrets.compare_digest(password, settings.admin_password)
    return True  # no password configured
```

### Pattern 3: HMAC-SHA256 Webhook Signature Verification
**What:** Verify Lemon Squeezy webhook signature
**When to use:** D-05

```python
import hmac
import hashlib

def verify_lemon_squeezy_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify X-Signature header from Lemon Squeezy."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Pattern 4: Generic Rate Limiting with IP Support
**What:** Extend `check_rate_limit()` to support arbitrary key prefixes
**When to use:** D-07 (phone-based) and D-08 (IP-based)

```python
async def check_rate_limit(
    key: str,
    limit: int = 20,
    window_seconds: int = 60,
    prefix: str = "rate",
) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    r = await get_redis()
    if not r:
        return True, 0
    redis_key = f"{prefix}:{key}"
    pipe = r.pipeline()
    pipe.incr(redis_key)
    pipe.ttl(redis_key)
    pipe.expire(redis_key, window_seconds)
    results = await pipe.execute()
    count = results[0]
    ttl = results[1]
    if count > limit:
        retry_after = max(ttl, 1)
        return False, retry_after
    return True, 0
```

### Pattern 5: CORS with Configurable Origins
**What:** Parse comma-separated env var into list
**When to use:** D-01

```python
# In config.py
allowed_origins: str = ""  # comma-separated

# In main.py
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # empty list = deny all cross-origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Anti-Patterns to Avoid
- **In-memory sessions in production:** Current `_admin_sessions: set[str]` is lost on restart/redeploy. Redis fixes this.
- **Plaintext password comparison:** `secrets.compare_digest(password, settings.admin_password)` is constant-time but stores/transmits plaintext. bcrypt hash is the fix.
- **Blocking bcrypt in async context:** `bcrypt.checkpw()` is CPU-bound. For the admin login endpoint (low traffic), this is acceptable without `run_in_executor`. If future profiling shows issues, wrap in executor.
- **Timing oracle in signature verification:** Always use `hmac.compare_digest()`, never `==` for signature comparison.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom hash scheme | `bcrypt.hashpw()` / `bcrypt.checkpw()` | bcrypt handles salt generation, work factor, timing-safe comparison |
| HMAC verification | Manual digest comparison | `hmac.compare_digest()` | Prevents timing attacks |
| Session tokens | UUID or timestamp-based | `secrets.token_hex()` (already used) | Cryptographically secure random |
| Rate limiting sliding window | Custom counter logic | Existing Redis INCR + EXPIRE pattern | Already implemented in `rate_limit.py` |

## Common Pitfalls

### Pitfall 1: is_authenticated Becomes Async
**What goes wrong:** `auth.py:is_authenticated()` is currently sync. Moving to Redis makes it async. All callers break.
**Why it happens:** `auth_check()` in `admin_common.py` and direct calls in routes use sync `is_authenticated()`.
**How to avoid:** Grep all callers of `is_authenticated` and `auth_check` -- update to `await`. This is the most pervasive change in this phase.
**Warning signs:** `RuntimeWarning: coroutine 'is_authenticated' was never awaited`

### Pitfall 2: Redis Unavailable Fallback
**What goes wrong:** If Redis is down, all admin sessions and rate limiting fail.
**Why it happens:** `get_redis()` returns None on connection failure.
**How to avoid:** Keep the in-memory `_admin_sessions` set as fallback. Rate limiting already returns `True` (allow) when Redis is unavailable. Log warnings when falling back.
**Warning signs:** Watch for `Redis connection failed` in logs.

### Pitfall 3: bcrypt Hash Format in Env Var
**What goes wrong:** bcrypt hashes contain `$` characters which can be misinterpreted by shell/docker-compose.
**Why it happens:** bcrypt output looks like `$2b$12$LJ3m4ys...`
**How to avoid:** In `.env` file, wrap value in single quotes: `ADMIN_PASSWORD_HASH='$2b$12$...'`. In docker-compose.yml, use the `.env` file mechanism (not inline environment variables). Document this clearly.
**Warning signs:** `ValueError: Invalid salt` from bcrypt.

### Pitfall 4: Raw Body vs Parsed JSON for Signature Verification
**What goes wrong:** Signature is computed over raw bytes, but FastAPI may have already consumed `request.body()`.
**Why it happens:** If you call `request.json()` before `request.body()`, the body stream may be exhausted.
**How to avoid:** Read raw body FIRST with `await request.body()`, verify signature, THEN parse JSON from the raw bytes.
**Warning signs:** Empty body on second read, signature always fails.

### Pitfall 5: CORS Empty Origins List Behavior
**What goes wrong:** An empty `allow_origins=[]` in CORSMiddleware means NO origins are allowed, which is correct for API-only endpoints but breaks the admin UI if accessed from a browser on a different origin.
**Why it happens:** Admin UI is server-rendered (Jinja2), so it's same-origin and CORS doesn't apply. But if admin is on a subdomain, it would be blocked.
**How to avoid:** The admin UI is served from the same FastAPI app (same origin), so empty CORS is fine. Just ensure the deployment URL is in the whitelist if admin is accessed cross-origin.
**Warning signs:** Browser console shows CORS errors on admin UI.

### Pitfall 6: `create_session` Must Become Async
**What goes wrong:** `create_session()` currently sets a cookie synchronously. With Redis, it needs `await r.set()`.
**Why it happens:** Session creation now involves a Redis write.
**How to avoid:** Make `create_session()` async, update the login route in `admin_dashboard.py` to `await create_session(resp)`.
**Warning signs:** Same coroutine-never-awaited warning as Pitfall 1.

## Code Examples

### Generate bcrypt Hash (CLI utility for operators)
```python
# One-liner for generating ADMIN_PASSWORD_HASH value:
# python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt(rounds=12)).decode())"
```

### Lemon Squeezy Webhook Route (new file)
```python
"""Lemon Squeezy webhook handler with signature verification."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.config import settings

router = APIRouter(prefix="/webhooks/lemon-squeezy", tags=["webhooks-billing"])
logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def lemon_squeezy_webhook(request: Request):
    secret = settings.lemon_squeezy_webhook_secret
    if not secret:
        logger.warning("LEMON_SQUEEZY_WEBHOOK_SECRET not configured, rejecting webhook")
        return JSONResponse({"error": "not configured"}, status_code=500)

    raw_body = await request.body()
    signature = request.headers.get("x-signature", "")

    if not signature or not _verify_signature(raw_body, signature, secret):
        logger.warning("Lemon Squeezy webhook: invalid signature")
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    event_name = payload.get("meta", {}).get("event_name", "unknown")
    logger.info("Lemon Squeezy event: %s", event_name)

    # Placeholder: actual event handling comes in Phase 8 (BILL-02)
    return {"status": "ok", "event": event_name}
```

### Rate-Limited Webhook Dependency
```python
from fastapi import Request
from fastapi.responses import JSONResponse

async def rate_limit_webhook(request: Request, phone: str):
    allowed, retry_after = await check_rate_limit(
        key=f"whatsapp:{phone}", limit=20, window_seconds=60
    )
    if not allowed:
        return JSONResponse(
            {"error": "rate limited"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    return None
```

## Config.py Additions

New settings fields needed in `Settings` class:

```python
# Security
allowed_origins: str = ""                    # SEC-01: comma-separated CORS origins
admin_password_hash: str = ""                # SEC-02: bcrypt hash
lemon_squeezy_webhook_secret: str = ""       # SEC-03: HMAC secret
```

Corresponding `.env.example` additions:
```
ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com
ADMIN_PASSWORD_HASH=
LEMON_SQUEEZY_WEBHOOK_SECRET=
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4+ with pytest-asyncio (mode: auto) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/ -x --no-header -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | CORS rejects non-whitelisted origins | unit | `pytest tests/test_security.py::test_cors_rejects_unknown_origin -x` | Wave 0 |
| SEC-01 | CORS allows whitelisted origin | unit | `pytest tests/test_security.py::test_cors_allows_whitelisted_origin -x` | Wave 0 |
| SEC-02 | Login with bcrypt hash succeeds | unit | `pytest tests/test_security.py::test_login_bcrypt_success -x` | Wave 0 |
| SEC-02 | Login with wrong password fails | unit | `pytest tests/test_security.py::test_login_bcrypt_wrong_password -x` | Wave 0 |
| SEC-02 | Session stored in Redis with TTL | unit | `pytest tests/test_security.py::test_session_redis_ttl -x` | Wave 0 |
| SEC-02 | Backward compat: plaintext password works with warning | unit | `pytest tests/test_security.py::test_plaintext_password_backward_compat -x` | Wave 0 |
| SEC-03 | Valid Lemon Squeezy signature accepted | unit | `pytest tests/test_security.py::test_lemon_squeezy_valid_signature -x` | Wave 0 |
| SEC-03 | Invalid signature returns 401 | unit | `pytest tests/test_security.py::test_lemon_squeezy_invalid_signature -x` | Wave 0 |
| SEC-04 | WhatsApp webhook returns 429 after limit | unit | `pytest tests/test_security.py::test_webhook_rate_limit_429 -x` | Wave 0 |
| SEC-04 | Login rate limit: 5 attempts per IP | unit | `pytest tests/test_security.py::test_login_rate_limit -x` | Wave 0 |
| SEC-04 | 429 response includes Retry-After header | unit | `pytest tests/test_security.py::test_429_retry_after_header -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_security.py -x --no-header -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before verify

### Wave 0 Gaps
- [ ] `tests/test_security.py` -- covers SEC-01 through SEC-04 (all new tests)
- [ ] Redis mock fixture in `tests/conftest.py` -- needed for session and rate limit tests
- [ ] FastAPI TestClient fixture in `tests/conftest.py` -- needed for CORS and endpoint tests

## Open Questions

1. **Admin UI same-origin assumption**
   - What we know: Admin UI is Jinja2 rendered by the same FastAPI app, so it is same-origin
   - What's unclear: Whether any deployment puts admin on a different subdomain
   - Recommendation: Default to empty ALLOWED_ORIGINS (safe). Document that admin subdomain must be added if used.

2. **Lemon Squeezy webhook event handling**
   - What we know: SEC-03 only requires signature verification. Actual event processing (subscription lifecycle) is Phase 8 (BILL-02).
   - What's unclear: Nothing -- scope is clear
   - Recommendation: Create the route with signature verification + placeholder handler. Return 200 on valid signature.

3. **Existing `check_rate_limit` signature change**
   - What we know: Current function takes `phone: str` with hardcoded key prefix `rate:whatsapp:`
   - What's unclear: Whether other code calls `check_rate_limit` directly
   - Recommendation: Grep confirms no route currently calls it. Safe to refactor the signature to be generic (add `prefix` parameter) without breaking existing callers.

## Sources

### Primary (HIGH confidence)
- Source code inspection: `src/api/auth.py`, `src/api/rate_limit.py`, `src/main.py`, `src/config.py`, `src/api/routes/webhook_cloud.py`, `src/api/routes/admin_dashboard.py`
- bcrypt 5.0.0 verified installed via `pip show bcrypt`
- FastAPI CORSMiddleware behavior: well-documented, confirmed via source code usage in `main.py`

### Secondary (MEDIUM confidence)
- Lemon Squeezy X-Signature header uses HMAC-SHA256 -- standard documented pattern for Lemon Squeezy webhooks
- bcrypt `$` character in env vars issue -- well-known Docker/shell pitfall

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed, no new dependencies
- Architecture: HIGH - modifications to existing well-understood modules
- Pitfalls: HIGH - async migration and raw body reading are well-documented patterns
- Lemon Squeezy specifics: MEDIUM - signature header name/algorithm based on standard Lemon Squeezy docs

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain, no fast-moving dependencies)
