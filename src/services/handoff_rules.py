"""Automatic handoff rules. When any rule triggers, bot stops and manager takes over."""

from typing import Optional
from src.services.intent import (
    HUMAN, FINANCING, TRADE_IN, VISIT, ASK_PHOTOS,
)

# Handoff reason constants
REASON_REQUESTED_HUMAN = "requested_human"
REASON_FINANCING = "financing"
REASON_TRADE_IN = "trade_in"
REASON_VISIT_SCHEDULING = "visit_scheduling"
REASON_PHOTOS_MISSING = "photos_missing"
REASON_BOT_UNHELPFUL = "bot_unhelpful"

# Human-readable labels
REASON_LABELS = {
    REASON_REQUESTED_HUMAN: "Customer requested a human",
    REASON_FINANCING: "Financing inquiry",
    REASON_TRADE_IN: "Trade-in inquiry",
    REASON_VISIT_SCHEDULING: "Visit scheduling",
    REASON_PHOTOS_MISSING: "Photos unavailable",
    REASON_BOT_UNHELPFUL: "Bot couldn't help",
}

REASON_LABELS_ES = {
    REASON_REQUESTED_HUMAN: "Cliente pidió hablar con una persona",
    REASON_FINANCING: "Consulta de financiación",
    REASON_TRADE_IN: "Consulta de permuta",
    REASON_VISIT_SCHEDULING: "Agenda de visita",
    REASON_PHOTOS_MISSING: "Fotos no disponibles",
    REASON_BOT_UNHELPFUL: "El bot no pudo ayudar",
}


def check_handoff(
    intent: str,
    state: dict,
    car_has_photos: bool = True,
) -> Optional[str]:
    """
    Check if any handoff rule triggers.
    Returns handoff_reason string or None.

    Rules:
    H1) Explicit human request
    H2) Financing intent
    H3) Trade-in intent
    H4) Visit intent (after lead created)
    H5) Photos requested but car has none
    H6) Bot unhelpful twice
    """
    # H1: Explicit human
    if intent == HUMAN:
        return REASON_REQUESTED_HUMAN

    # H2: Financing
    if intent == FINANCING:
        return REASON_FINANCING

    # H3: Trade-in
    if intent == TRADE_IN:
        return REASON_TRADE_IN

    # H4: Visit
    if intent == VISIT:
        return REASON_VISIT_SCHEDULING

    # H5: Photos missing
    if intent == ASK_PHOTOS and not car_has_photos:
        return REASON_PHOTOS_MISSING

    # H6: Unhelpful count
    unhelpful = state.get("unhelpful_count", 0)
    if unhelpful >= 2:
        return REASON_BOT_UNHELPFUL

    return None


def get_reason_label(reason: Optional[str], language: str = "es") -> str:
    """Get human-readable label for handoff reason."""
    if not reason:
        return ""
    labels = REASON_LABELS_ES if language.startswith("es") else REASON_LABELS
    return labels.get(reason, reason)
