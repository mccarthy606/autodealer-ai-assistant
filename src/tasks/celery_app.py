"""Celery application."""

from celery import Celery

from src.config import settings

celery_app = Celery(
    "ai_inventory_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.import_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
)
