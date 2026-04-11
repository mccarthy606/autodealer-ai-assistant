"""FastAPI application entry point."""

import logging
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import admin, webhooks, import_routes, celery_routes
from src.api.routes import (
    admin_dashboard, admin_inventory, admin_leads,
    admin_conversations, admin_settings,
)
from src.api.routes.webhook_cloud import router as whatsapp_cloud_router
from src.api.routes.webhook_lemon import router as lemon_router
from src.api.routes.webhook_ml import router as ml_router
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os
if not settings.admin_password_hash and not settings.admin_password:
    import warnings
    warnings.warn(
        "ADMIN_PASSWORD / ADMIN_PASSWORD_HASH not configured — admin UI is open to everyone! "
        "Set ADMIN_PASSWORD_HASH in .env (generate: python -c \"import bcrypt; "
        "print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())\")",
        stacklevel=1,
    )

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release or "1.0.0",
        traces_sample_rate=0.1,
    )

app = FastAPI(
    title="AutoDealer AI Assistant",
    description="AI-powered assistant for car dealerships — WhatsApp, MercadoLibre, Admin UI",
    version="1.0.0",
)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Routers
app.include_router(admin.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_inventory.router)
app.include_router(admin_leads.router)
app.include_router(admin_conversations.router)
app.include_router(admin_settings.router)
app.include_router(webhooks.router)
app.include_router(whatsapp_cloud_router)
app.include_router(ml_router)
app.include_router(lemon_router)
app.include_router(celery_routes.router)
app.include_router(import_routes.router, prefix="/admin/import")

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def startup():
    """Initialize connections and ensure default dealership exists."""
    from sqlalchemy import select
    from src.db.session import AsyncSessionLocal
    from src.db.models import Dealership
    from src.api.rate_limit import get_redis
    await get_redis()  # Initialize Redis singleton at startup (MEDIUM-3)

    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Dealership).where(Dealership.id == settings.default_dealership_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                d = Dealership(
                    name="Mi Concesionario",
                    address="Av. Libertador 1234, CABA",
                    business_hours="Lun-Vie 9-18, Sab 9-13",
                    timezone="America/Argentina/Buenos_Aires",
                    default_language="es-AR",
                )
                session.add(d)
                await session.commit()
                logger.info("Created default dealership id=%s", settings.default_dealership_id)
        except Exception as e:
            logger.warning("Startup: %s", e)


@app.get("/health")
async def health():
    """Deep health check: DB, Redis, Celery."""
    from sqlalchemy import text
    from src.db.session import AsyncSessionLocal
    from src.api.rate_limit import get_redis
    import asyncio

    result = {"db": "ok", "redis": "ok", "celery": "ok"}

    # DB check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Health check DB failed: %s", e)
        result["db"] = "error"

    # Redis check
    try:
        r = await get_redis()
        if r is None:
            result["redis"] = "error"
        else:
            await r.ping()
    except Exception as e:
        logger.warning("Health check Redis failed: %s", e)
        result["redis"] = "error"

    # Celery check (best-effort, 1s timeout — per D-21)
    try:
        from src.tasks.celery_app import celery_app
        insp = celery_app.control.inspect(timeout=1)
        loop = asyncio.get_running_loop()
        ping_result = await loop.run_in_executor(None, insp.ping)
        if not ping_result:
            result["celery"] = "timeout"
    except Exception as e:
        logger.warning("Health check Celery failed: %s", e)
        result["celery"] = "error"

    any_error = any(v == "error" for v in result.values())
    result["status"] = "degraded" if any_error else "ok"

    status_code = 503 if any_error else 200
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result, status_code=status_code)


@app.get("/")
async def root():
    return {
        "app": "AutoDealer AI Assistant",
        "version": "1.0.0",
        "admin": "/admin/ui",
        "docs": "/docs",
    }
