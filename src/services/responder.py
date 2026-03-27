"""Multilingual response generation. Deterministic + optional LLM polish."""

from typing import Any, Optional

from src.services.intent import (
    SEARCH_CAR, ASK_PHOTOS, ASK_DETAILS, ASK_PRICE, ASK_KM,
    ASK_STATUS, VISIT, FINANCING, TRADE_IN, NOTIFY, HUMAN,
    GREETING, OTHER,
)
from src.services.handoff_rules import get_reason_label


def _format_car_line(car: dict, idx: int, lang: str = "es") -> str:
    """Format a single car as a text line."""
    km_str = f", {car.get('km', 0):,} km" if car.get("km") else ""
    price = car.get("price", 0)
    status = car.get("status", "available")
    status_tag = ""
    if status == "in_transit":
        status_tag = " 🚛 En camino" if lang == "es" else " 🚛 In transit"
    elif status == "reserved":
        status_tag = " 🔒 Reservado" if lang == "es" else " 🔒 Reserved"
    return f"{idx}. {car.get('brand', '')} {car.get('model', '')} {car.get('year', '')}{km_str} — ${price:,.0f}{status_tag}"


def _format_car_list(cars: list[dict], lang: str = "es") -> str:
    """Format list of cars as text."""
    lines = [_format_car_line(c, i, lang) for i, c in enumerate(cars[:3], 1)]
    return "\n".join(lines)


def format_car_whatsapp_message(car: dict, lang: str = "es") -> str:
    """Format a car for WhatsApp sharing."""
    title = f"{car.get('brand', '')} {car.get('model', '')} {car.get('trim', '') or ''} {car.get('year', '')}".strip()
    km_str = f"📏 {car.get('km', 0):,} km\n" if car.get("km") else ""
    cond = car.get("condition", "used")
    if lang == "es":
        cond_str = {"new": "Nuevo", "used": "Usado", "zero_km": "0 km"}.get(cond, cond)
        return (
            f"🚗 *{title}*\n"
            f"💰 ${car.get('price', 0):,.0f} {car.get('currency', 'ARS')}\n"
            f"{km_str}"
            f"📋 {cond_str}\n"
            f"📍 {car.get('location', 'Consultar')}\n\n"
            f"¿Te interesa? ¡Escribinos!"
        )
    else:
        cond_str = {"new": "New", "used": "Used", "zero_km": "0 km"}.get(cond, cond)
        return (
            f"🚗 *{title}*\n"
            f"💰 ${car.get('price', 0):,.0f} {car.get('currency', 'ARS')}\n"
            f"{km_str}"
            f"📋 {cond_str}\n"
            f"📍 {car.get('location', 'Contact us')}\n\n"
            f"Interested? Write to us!"
        )


# === Response templates ===

_RESPONSES = {
    # GREETING
    (GREETING, "es"): "¡Hola! 👋 Soy el asistente del concesionario. ¿En qué puedo ayudarte? Podés preguntarme por marcas, modelos o presupuesto.",
    (GREETING, "en"): "Hi! 👋 I'm the dealership assistant. How can I help? You can ask me about brands, models or budget.",

    # SEARCH results
    ("SEARCH_FOUND", "es"): "Tenemos estas opciones:\n{cars}\n\n¿Querés más detalles de alguno o pasar a verlo al salón?",
    ("SEARCH_FOUND", "en"): "We have these options:\n{cars}\n\nWould you like more details or to come see one?",

    ("SEARCH_NOT_FOUND", "es"): "No encontramos ese modelo en stock ahora. {alternatives}\n¿Querés que te avisemos cuando llegue o te interesa otra opción?",
    ("SEARCH_NOT_FOUND", "en"): "We don't have that model in stock right now. {alternatives}\nWant us to notify you when it arrives, or are you interested in something else?",

    ("SEARCH_ALTERNATIVES", "es"): "Pero tenemos opciones similares:\n{cars}",
    ("SEARCH_ALTERNATIVES", "en"): "But we have similar options:\n{cars}",

    # PHOTOS
    ("PHOTOS_SENT", "es"): "Acá tenés las fotos de {car_name}:\n{photo_links}\n\n¿Querés pasar a verlo en persona?",
    ("PHOTOS_SENT", "en"): "Here are the photos of {car_name}:\n{photo_links}\n\nWould you like to come see it in person?",

    ("PHOTOS_MISSING", "es"): "No tenemos fotos cargadas de ese vehículo todavía. Te conecto con un vendedor que te las puede enviar. 📷",
    ("PHOTOS_MISSING", "en"): "We don't have photos uploaded for this vehicle yet. I'll connect you with a salesperson who can send them. 📷",

    # DETAILS
    ("DETAILS", "es"): "📋 *{car_name}*\n💰 Precio: ${price:,.0f} {currency}\n📏 Km: {km}\n📍 Ubicación: {location}\n📝 {description}\n\n¿Querés pasar a verlo hoy o mañana?",
    ("DETAILS", "en"): "📋 *{car_name}*\n💰 Price: ${price:,.0f} {currency}\n📏 Km: {km}\n📍 Location: {location}\n📝 {description}\n\nWould you like to visit today or tomorrow?",

    # VISIT
    ("VISIT_CONFIRM", "es"): "¡Perfecto! 🙌 Te esperamos en {address}. {hours}\n¿A qué hora te queda bien?",
    ("VISIT_CONFIRM", "en"): "Perfect! 🙌 We'll be waiting for you at {address}. {hours}\nWhat time works for you?",

    ("VISIT_CONFIRM_WITH_TIME", "es"): "¡Perfecto{name_str}! 🙌 Te esperamos {time} en {address}. {hours}\nUn vendedor te va a atender personalmente.",
    ("VISIT_CONFIRM_WITH_TIME", "en"): "Perfect{name_str}! 🙌 We'll see you {time} at {address}. {hours}\nA salesperson will assist you personally.",

    # HANDOFF acknowledgements
    ("HANDOFF_HUMAN", "es"): "Te conecto con un vendedor ahora mismo. En breve te van a contactar. 👋",
    ("HANDOFF_HUMAN", "en"): "I'm connecting you with a salesperson right away. They'll contact you shortly. 👋",

    ("HANDOFF_FINANCING", "es"): "¡Buena consulta! Para financiación te paso con un asesor que te puede dar todas las opciones. Te contacta en breve. 💳",
    ("HANDOFF_FINANCING", "en"): "Great question! For financing, I'll connect you with an advisor who can give you all the options. They'll contact you shortly. 💳",

    ("HANDOFF_TRADE_IN", "es"): "¡Genial! Para evaluar tu auto en parte de pago, te paso con un tasador. Te contacta en breve. 🔄",
    ("HANDOFF_TRADE_IN", "en"): "Great! To evaluate your car for trade-in, I'll connect you with an appraiser. They'll contact you shortly. 🔄",

    ("HANDOFF_PHOTOS_MISSING", "es"): "No tenemos fotos cargadas todavía. Te conecto con un vendedor que te las envía. 📷",
    ("HANDOFF_PHOTOS_MISSING", "en"): "We don't have photos uploaded yet. I'll connect you with a salesperson who can send them. 📷",

    ("HANDOFF_UNHELPFUL", "es"): "Parece que no estoy pudiendo ayudarte bien. Te paso con un vendedor que te va a dar una mejor mano. 🤝",
    ("HANDOFF_UNHELPFUL", "en"): "It seems I'm not being very helpful. Let me connect you with a salesperson who can better assist you. 🤝",

    # NOTIFY
    ("NOTIFY", "es"): "Te anotamos para que te avisemos cuando llegue. ¿Hay alguna otra opción que te interese mientras tanto?",
    ("NOTIFY", "en"): "We'll note that and let you know when it arrives. Is there anything else you're interested in meanwhile?",

    # OTHER
    (OTHER, "es"): "No estoy seguro de entenderte. ¿Buscás un auto en particular? Podés decirme la marca, modelo o presupuesto.",
    (OTHER, "en"): "I'm not sure I understand. Are you looking for a specific car? You can tell me the brand, model or budget.",

    # Manager mode
    ("MANAGER_MODE", "es"): "Un vendedor está atendiendo tu consulta. En breve te responde. 👋",
    ("MANAGER_MODE", "en"): "A salesperson is handling your inquiry. They'll respond shortly. 👋",
}


def get_response(key: str, lang: str = "es", **kwargs) -> str:
    """Get a response template and format it."""
    effective_lang = "es" if lang.startswith("es") else "en"
    template = _RESPONSES.get((key, effective_lang), _RESPONSES.get((key, "es"), ""))
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def build_search_response(
    cars: list[dict],
    alternatives: list[dict],
    lang: str = "es",
) -> str:
    """Build response for car search results."""
    effective_lang = "es" if lang.startswith("es") else "en"
    if cars:
        cars_text = _format_car_list(cars, effective_lang)
        return get_response("SEARCH_FOUND", lang, cars=cars_text)
    elif alternatives:
        alt_text = _format_car_list(alternatives, effective_lang)
        alt_intro = get_response("SEARCH_ALTERNATIVES", lang, cars=alt_text)
        return get_response("SEARCH_NOT_FOUND", lang, alternatives=alt_intro)
    else:
        return get_response("SEARCH_NOT_FOUND", lang, alternatives="")


def build_details_response(car: dict, lang: str = "es") -> str:
    """Build detail response for a specific car."""
    name = f"{car.get('brand', '')} {car.get('model', '')} {car.get('year', '')}"
    km = f"{car.get('km', 0):,} km" if car.get("km") else ("0 km" if car.get("condition") == "zero_km" else "N/A")
    desc = car.get("description") or ("Sin descripción" if lang.startswith("es") else "No description")
    return get_response("DETAILS", lang,
                        car_name=name.strip(),
                        price=car.get("price", 0),
                        currency=car.get("currency", "ARS"),
                        km=km,
                        location=car.get("location", "Consultar" if lang.startswith("es") else "Contact us"),
                        description=desc)


def build_photos_response(car: dict, lang: str = "es") -> tuple[str, list[str]]:
    """Build photo response. Returns (text, photo_urls)."""
    photos = car.get("photos", []) or []
    name = f"{car.get('brand', '')} {car.get('model', '')} {car.get('year', '')}"
    if photos:
        photo_links = "\n".join(f"📸 {url}" for url in photos[:3])
        text = get_response("PHOTOS_SENT", lang, car_name=name.strip(), photo_links=photo_links)
        return text, photos[:3]
    else:
        text = get_response("PHOTOS_MISSING", lang)
        return text, []


def build_visit_response(
    address: str,
    business_hours: str,
    name: Optional[str] = None,
    time: Optional[str] = None,
    lang: str = "es",
) -> str:
    """Build visit confirmation response."""
    hours = f"Horario: {business_hours}" if business_hours else ""
    if time:
        name_str = f", {name}" if name else ""
        return get_response("VISIT_CONFIRM_WITH_TIME", lang,
                            name_str=name_str, time=time, address=address, hours=hours)
    return get_response("VISIT_CONFIRM", lang, address=address, hours=hours)


def build_handoff_response(reason: str, lang: str = "es") -> str:
    """Build handoff acknowledgement message."""
    key_map = {
        "requested_human": "HANDOFF_HUMAN",
        "financing": "HANDOFF_FINANCING",
        "trade_in": "HANDOFF_TRADE_IN",
        "photos_missing": "HANDOFF_PHOTOS_MISSING",
        "bot_unhelpful": "HANDOFF_UNHELPFUL",
        "visit_scheduling": "VISIT_CONFIRM",
    }
    key = key_map.get(reason, "HANDOFF_HUMAN")
    if key == "VISIT_CONFIRM":
        return ""  # Visit has its own response built separately
    return get_response(key, lang)
