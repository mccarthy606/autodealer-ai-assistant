---
phase: 09-production-deployment
plan: "02"
subsystem: observability-health
tags: [sentry, health-check, alembic, fastapi, monitoring]
dependency_graph:
  requires: ["09-01"]
  provides: ["sentry-monitoring", "deep-health-endpoint", "migration-separation"]
  affects: ["src/main.py", "src/config.py", "pyproject.toml"]
tech_stack:
  added: ["sentry-sdk[fastapi]>=2.0.0"]
  patterns: ["module-level Sentry init", "async deep health check", "dependency injection via local imports"]
key_files:
  modified:
    - src/main.py
    - src/config.py
    - pyproject.toml
decisions:
  - "Sentry init placed at module level before app = FastAPI() to capture errors from all workers from first request"
  - "Celery timeout maps to 'timeout' (not 'error') — health returns HTTP 200 so load balancers don't remove pods when Celery is temporarily unreachable"
  - "Alembic block removed from startup(); migrations now managed via migrate service in docker-compose.prod.yml (established in 09-01)"
metrics:
  duration: "8 minutes"
  completed: "2026-03-27"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 9 Plan 02: Sentry Monitoring, Deep Health Check, Startup Cleanup Summary

**One-liner:** Conditional Sentry SDK init at module level, DB/Redis/Celery deep health check with HTTP 503 on hard failures, and removal of inline Alembic migration from app startup.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add sentry_dsn to config.py and sentry-sdk to pyproject.toml | a6988fa | src/config.py, pyproject.toml |
| 2 | Rewrite src/main.py — Sentry init, deep /health, startup cleanup | fe64366 | src/main.py |

## What Was Built

### Sentry Error Monitoring (DEP-03)
- `sentry-sdk[fastapi]>=2.0.0` added to `pyproject.toml` dependencies
- `sentry_dsn: str = ""` added to `Settings` class in `src/config.py` under `# Monitoring` comment
- Module-level conditional init in `src/main.py` before `app = FastAPI(...)`:
  ```python
  if settings.sentry_dsn:
      sentry_sdk.init(dsn=settings.sentry_dsn, environment="production", release="1.0.0", traces_sample_rate=0.1)
  ```
- No-op when `SENTRY_DSN` env var is empty — safe for local dev and CI

### Deep /health Endpoint (DEP-05)
- Replaced trivial `{"status": "ok"}` with a full dependency check handler
- DB check: `AsyncSessionLocal()` + `text("SELECT 1")`
- Redis check: `get_redis()` from `src/api/rate_limit.py` + `await r.ping()`
- Celery check: `celery_app.control.inspect(timeout=1).ping()` via `run_in_executor` (non-blocking)
- Response shape: `{"status": "ok"|"degraded", "db": "ok"|"error", "redis": "ok"|"error", "celery": "ok"|"timeout"|"error"}`
- HTTP 503 if `db` or `redis` = `"error"`; HTTP 200 if only Celery times out
- Celery timeout → `"celery": "timeout"` still returns 200 (load-balancer safe)

### Alembic Startup Removal (DEP-06)
- Deleted the inner `try/except` block importing `alembic.config.Config` and running `command.upgrade(alembic_cfg, "head")`
- `startup()` now only creates the default dealership if absent — no migration side effects
- `@app.on_event("startup")` decorator preserved (no lifespan refactor — out of scope)

## Verification Results

All acceptance criteria confirmed:

- `grep "sentry_dsn: str" src/config.py` — PASS
- `grep "sentry-sdk\[fastapi\]" pyproject.toml` — PASS
- `grep -n "sentry_sdk.init\|app = FastAPI" src/main.py` — line 25 < line 32 (PASS)
- `grep "SELECT 1" src/main.py` — PASS
- `grep "alembic upgrade\|from alembic" src/main.py` — no output (PASS)
- `grep "default dealership" src/main.py` — PASS
- `grep "on_event.*startup" src/main.py` — PASS
- Python syntax: `py -3 -c "import ast; ast.parse(...)"` — PASS for both files

## Deviations from Plan

None — plan executed exactly as written. All three changes (Sentry init, deep health, alembic removal) implemented per specification without structural deviations.

## Known Stubs

None. The `/health` endpoint uses real dependency checks with no hardcoded values. Sentry DSN defaults to empty string (intentional — operator fills via env var). The celery `"timeout"` path is a legitimate operational state, not a stub.

## Self-Check: PASSED

- `src/main.py` exists and contains `sentry_sdk.init`, `SELECT 1`, no alembic references
- `src/config.py` exists and contains `sentry_dsn: str = ""`
- `pyproject.toml` exists and contains `sentry-sdk[fastapi]>=2.0.0`
- Commits a6988fa and fe64366 both present in `git log --oneline -5`
