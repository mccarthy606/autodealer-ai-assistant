"""Visit intent detection - rule-based, no LLM. Creates lead when client wants to visit."""

import re
from typing import Optional

# Triggers for visit intent (case-insensitive, ES-AR)
VISIT_INTENT_TRIGGERS = [
    "quiero pasar", "quiero ir", "voy", "me acerco",
    "mañana", "hoy", "a la tarde", "a la mañana",
    "este finde", "sábado", "sabado", "domingo",
    "paso", "puedo ir", "horario",  # extra for common phrases
]


def detect_visit_intent(text: str) -> bool:
    """Rule-based: True if message indicates visit intent."""
    t = text.lower().strip()
    return any(trigger in t for trigger in VISIT_INTENT_TRIGGERS)


def extract_visit_details(text: str) -> tuple[Optional[str], str]:
    """
    Extract name ("me llamo X") and parsed time from message.
    Returns (name, parsed_time) for lead.notes.
    """
    t = text.lower().strip()
    name = None
    time_parts = []

    # Name: "me llamo X" (1-2 words)
    m = re.search(r"me llamo\s+(\w+(?:\s+\w+)?)", t, re.IGNORECASE)
    if m:
        name = m.group(1).strip().title()

    # Time markers
    if "mañana a la mañana" in t or "manana a la mañana" in t:
        time_parts.append("mañana a la mañana")
    elif "mañana a la tarde" in t:
        time_parts.append("mañana a la tarde")
    elif "hoy a la mañana" in t:
        time_parts.append("hoy a la mañana")
    elif "hoy a la tarde" in t:
        time_parts.append("hoy a la tarde")
    elif "a la mañana" in t:
        time_parts.append("a la mañana")
    elif "a la tarde" in t:
        time_parts.append("a la tarde")
    elif "mañana" in t or "manana" in t:
        time_parts.append("mañana")
    elif "hoy" in t:
        time_parts.append("hoy")
    elif "sábado" in t or "sabado" in t:
        time_parts.append("sábado")
    elif "domingo" in t:
        time_parts.append("domingo")
    elif "finde" in t:
        time_parts.append("este finde")

    # Hours: "15:00", "3pm", "14hs"
    hour_m = re.search(r"(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|hs?))?)", t, re.IGNORECASE)
    if hour_m:
        time_parts.append(hour_m.group(1))

    parsed_time = ", ".join(time_parts) if time_parts else "no especificado"
    return name, parsed_time


def format_visit_response(name: Optional[str], address: Optional[str]) -> str:
    """Fixed response for visit intent."""
    greeting = f"Perfecto, {name} 🙌 " if name else "Perfecto 🙌 "
    if address:
        return f"{greeting}Te esperamos en {address}. ¿A qué hora te queda bien?"
    return f"{greeting}Te esperamos en el salón. ¿A qué hora te queda bien?"


# Alias for backward compat
def is_visit_confirmation(text: str) -> bool:
    return detect_visit_intent(text)
