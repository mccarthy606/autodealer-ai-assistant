"""Celery Beat task: automated follow-up messages for unresponsive leads."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker, Session

from src.adapters.whatsapp_cloud import WhatsAppCloudAdapter
from src.config import settings
from src.db.models import Conversation
from src.db.session import sync_engine  # reuse shared engine — do NOT create a second one
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Sync DB — reuses sync_engine from session.py (same pattern as import_tasks.py)
_SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)

# Follow-up thresholds (per D-02, D-03)
FOLLOWUP_1_HOURS = 24
FOLLOWUP_2_HOURS = 72

# Minimum gap between followup #1 and followup #2 (per BLOCKER 5 fix)
FOLLOWUP_2_MIN_GAP_HOURS = 48

# Eligible stages (per D-04)
ELIGIBLE_STAGES = {"PRESENTING", "DETAILS", "OUTBOUND_INIT", "BROWSING"}


def _build_components_24h(conv: Conversation) -> tuple[str, list[dict]]:
    """
    Build template components for followup_24h_v1.
    Template: "Hola {{1}}! Seguís interesado en {{2}}? Está disponible por {{3}}. Te esperamos en {{4}}!"
    Returns (template_name, components).
    """
    state = conv.state or {}
    name = state.get("name") or "cliente"
    car_title = state.get("selected_car_title") or "el vehículo"
    price = state.get("selected_car_price") or "consultar precio"
    # Dealership address not readily available here — use a generic value; real impl
    # can join Dealership. For now use a placeholder that dealership can configure.
    address = "nuestro salón"

    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": name},
                {"type": "text", "text": car_title},
                {"type": "text", "text": str(price)},
                {"type": "text", "text": address},
            ],
        }
    ]
    return "followup_24h_v1", components


def _build_components_3d(conv: Conversation) -> tuple[str, list[dict]]:
    """
    Build template components for followup_3d_v1.
    Template: "Hola {{1}}! Te escribimos de {{2}}. El {{3}} que consultaste sigue disponible. Querés pasar a verlo?"
    Returns (template_name, components).
    """
    state = conv.state or {}
    name = state.get("name") or "cliente"
    dealership_name = "nuestra concesionaria"
    car_title = state.get("selected_car_title") or "vehículo"

    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": name},
                {"type": "text", "text": dealership_name},
                {"type": "text", "text": car_title},
            ],
        }
    ]
    return "followup_3d_v1", components


def _get_candidates(session: Session, now: datetime) -> list[Conversation]:
    """
    Load conversations that are potentially eligible for a follow-up.
    Python-side filtering avoids JSONB cast issues (per research finding).
    Load mode=bot conversations with recent last_message_at in the right range.
    """
    # Upper bound: only look at conversations last active >= 24h ago (no point scanning fresh ones)
    # Lower bound: cap at 30 days to avoid resurrecting very old conversations
    cutoff_upper = now - timedelta(hours=FOLLOWUP_1_HOURS)
    cutoff_lower = now - timedelta(days=30)

    rows = (
        session.query(Conversation)
        .filter(
            Conversation.mode == "bot",
            Conversation.last_message_at <= cutoff_upper,
            Conversation.last_message_at >= cutoff_lower,
        )
        .all()
    )
    return rows


def _should_followup(conv: Conversation, now: datetime) -> tuple[bool, int]:
    """
    Determine if this conversation needs a follow-up and which one.
    Returns (should_send, followup_number) where followup_number is 1 or 2.
    Returns (False, 0) if no follow-up needed.
    """
    state = conv.state or {}

    # Hard stops (per D-08, D-11)
    if state.get("opted_out"):
        return False, 0
    if state.get("followup_count", 0) >= 2:
        return False, 0

    # Stage filter (per D-04)
    stage = state.get("stage", "NEW")
    if stage not in ELIGIBLE_STAGES:
        return False, 0

    # Skip BROWSING conversations without a selected car — template text would be unprofessional
    # (per WARNING 1 fix)
    if stage == "BROWSING" and state.get("selected_car_id") is None:
        return False, 0

    hours_silent = (now - conv.last_message_at.replace(tzinfo=UTC)).total_seconds() / 3600
    followup_count = state.get("followup_count", 0)

    if followup_count == 0 and hours_silent >= FOLLOWUP_1_HOURS:
        return True, 1

    if followup_count == 1 and hours_silent >= FOLLOWUP_2_HOURS:
        # Enforce minimum gap between followup #1 and followup #2 (per BLOCKER 5 fix).
        # last_followup_at is recorded as ISO string when followup #1 is sent.
        # Without this guard, if the Beat task ran before the 48h gap, a second
        # follow-up could be sent minutes after the first (e.g., if followup #1
        # was sent near the 72h boundary).
        last_followup_at_str = state.get("last_followup_at")
        if last_followup_at_str:
            last_followup_at = datetime.fromisoformat(last_followup_at_str)
            if last_followup_at.tzinfo is None:
                last_followup_at = last_followup_at.replace(tzinfo=UTC)
            if (now - last_followup_at) < timedelta(hours=FOLLOWUP_2_MIN_GAP_HOURS):
                return False, 0
        return True, 2

    return False, 0


@celery_app.task(name="src.tasks.followup_task.send_followups", bind=True, max_retries=3)
def send_followups(self) -> dict:
    """
    Celery Beat task. Scans for unresponsive conversations and sends template follow-ups.
    Runs every 15 minutes (per D-01).

    WhatsApp delivery: calls WhatsAppCloudAdapter.send_template() (per D-14) via asyncio.run().
    asyncio.run() is safe here — each Celery task runs in its own thread/process with no
    existing event loop.
    """
    now = datetime.now(UTC)
    sent = 0
    skipped = 0
    errors = 0

    wa_adapter = WhatsAppCloudAdapter()

    with _SyncSession() as session:
        candidates = _get_candidates(session, now)
        logger.info("followup_task: %d candidates loaded", len(candidates))

        for conv in candidates:
            try:
                should_send, followup_num = _should_followup(conv, now)
                if not should_send:
                    skipped += 1
                    continue

                # Build template payload
                if followup_num == 1:
                    template_name, components = _build_components_24h(conv)
                else:
                    template_name, components = _build_components_3d(conv)

                # Language: use stored language or default to es
                lang = (conv.state or {}).get("language", "es")
                language_code = "es" if lang.startswith("es") else "en"

                # Call async adapter via asyncio.run() — safe in sync Celery worker
                # (no existing event loop in this thread/process)
                api_result = asyncio.run(
                    wa_adapter.send_template(
                        to=conv.user_phone,
                        template_name=template_name,
                        language_code=language_code,
                        components=components,
                    )
                )

                if "error" in api_result:
                    logger.error(
                        "followup_task: failed to send to conv=%d phone=%s: %s",
                        conv.id, conv.user_phone, api_result["error"],
                    )
                    errors += 1
                    continue

                # Update state — JSONB-safe assignment (per research: use {**old, key: val})
                old_state = dict(conv.state or {})
                conv.state = {
                    **old_state,
                    "followup_count": old_state.get("followup_count", 0) + 1,
                    "last_followup_at": now.isoformat(),
                }
                session.add(conv)
                sent += 1
                logger.info(
                    "followup_task: sent followup #%d to conv=%d phone=%s template=%s",
                    followup_num, conv.id, conv.user_phone, template_name,
                )

            except Exception as exc:
                logger.exception("followup_task: unexpected error for conv=%d: %s", conv.id, exc)
                errors += 1
                continue

        session.commit()

    result = {"sent": sent, "skipped": skipped, "errors": errors}
    logger.info("followup_task complete: %s", result)
    return result
