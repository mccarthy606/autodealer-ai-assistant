"""FastAPI application entry point."""

import logging
from pathlib import Path

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
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(import_routes.router, prefix="/import")
app.include_router(import_routes.router, prefix="/admin/import")

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def startup():
    """Ensure default dealership exists and run migrations."""
    from sqlalchemy import select, text
    from src.db.session import AsyncSessionLocal
    from src.db.models import Dealership

    async with AsyncSessionLocal() as session:
        try:
            # Run alembic migrations automatically
            try:
                from alembic.config import Config
                from alembic import command
                alembic_cfg = Config("alembic.ini")
                command.upgrade(alembic_cfg, "head")
                logger.info("Alembic migrations applied successfully")
            except Exception as e:
                logger.warning("Could not run alembic migrations: %s", e)

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
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "app": "AutoDealer AI Assistant",
        "version": "1.0.0",
        "admin": "/admin/ui",
        "docs": "/docs",
    }
