"""Celery application."""

from celery import Celery

from src.config import settings

celery_app = Celery(
    "ai_inventory_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.import_tasks", "src.tasks.followup_task"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    beat_schedule={
        "followup-every-15-min": {
            "task": "src.tasks.followup_task.send_followups",
            # Note: the task function is named send_followups (not scan_and_send_followups —
            # the research doc used a provisional name; the implementation uses send_followups)
            "schedule": 900,  # 15 minutes in seconds (per D-01)
        },
        "ml-inventory-sync-every-4h": {
            "task": "src.tasks.import_tasks.sync_ml_inventory_all_dealers",
            "schedule": 14400,  # 4 hours
        },
    },
)
