"""Rule-based intent detection. No LLM needed."""

import re
from typing import Optional

# Intent constants
SEARCH_CAR = "SEARCH_CAR"
ASK_PHOTOS = "ASK_PHOTOS"
ASK_DETAILS = "ASK_DETAILS"
ASK_PRICE = "ASK_PRICE"
ASK_KM = "ASK_KM"
ASK_STATUS = "ASK_STATUS"
VISIT = "VISIT"
FINANCING = "FINANCING"
TRADE_IN = "TRADE_IN"
NOTIFY = "NOTIFY"
HUMAN = "HUMAN"
GREETING = "GREETING"
OTHER = "OTHER"
OPT_OUT = "OPT_OUT"

# --- Keyword maps (ES + EN) ---
_PHOTO_KEYWORDS = [
    "foto", "fotos", "photo", "photos", "pics", "pic",
    "imagen", "imagenes", "imágenes", "pictures", "send me a pic",
    "mandarme foto", "mandame foto", "pasame foto", "ver foto",
    "show me", "let me see",
]

_DETAIL_KEYWORDS = [
    "detalle", "detalles", "detail", "details", "more info",
    "mas info", "más info", "contame más", "tell me more",
    "especificaciones", "specs", "ficha", "ficha técnica",
    "que tiene", "qué tiene", "what does it have",
]

_PRICE_KEYWORDS = [
    "precio", "cuánto", "cuanto", "cuánto sale", "cuanto sale",
    "price", "how much", "cost", "cuesta", "valor",
]

_KM_KEYWORDS = [
    "kilometraje", "kilómetros", "kilometros", "km",
    "mileage", "cuantos km", "cuántos km", "how many km",
]

_STATUS_KEYWORDS = [
    "disponible", "available", "está disponible", "is it available",
    "lo tienen", "lo tenés", "do you have it", "en stock",
]

_VISIT_KEYWORDS = [
    "quiero pasar", "quiero ir", "voy a pasar", "me acerco",
    "puedo ir", "puedo pasar", "paso", "visitar", "visitarlos",
    "quiero verla", "quiero verlo", "quiero conocer",
    "i want to visit", "i want to come", "can i come",
    "i'd like to visit", "i'll come", "i want to see it",
    "want to visit", "come see",
    # Time-based triggers that imply visit
    "mañana", "hoy", "a la tarde", "a la mañana",
    "este finde", "sábado", "sabado", "domingo",
    "tomorrow", "today", "this weekend", "saturday", "sunday",
]

_FINANCING_KEYWORDS = [
    "financiación", "financiacion", "financiar", "financing", "finance",
    "cuotas", "installments", "crédito", "credito", "credit",
    "plan de ahorro", "prenda", "loan", "planes",
]

_TRADE_IN_KEYWORDS = [
    "permuta", "trade-in", "trade in", "tradein",
    "entregar", "tomar", "tomo mi auto",
    "tengo un", "tengo una",  # "tengo un golf para entregar"
    "parte de pago", "give my car",
]

_NOTIFY_KEYWORDS = [
    "avisame", "avisá", "avísame", "notify me", "let me know",
    "cuando llegue", "when it arrives", "me interesa reservar",
]

_HUMAN_KEYWORDS = [
    "vendedor", "asesor", "humano", "persona", "llamame",
    "hablar con alguien", "human", "agent", "salesperson",
    "talk to someone", "call me", "speak to a person",
    "quiero hablar con", "necesito hablar con",
]

_GREETING_KEYWORDS = [
    "hola", "buen día", "buenas", "buenos días", "buenas tardes",
    "buenas noches", "hi", "hello", "hey", "good morning",
    "good afternoon", "good evening",
]

_OPT_OUT_KEYWORDS = [
    "no me interesa", "no gracias", "no, gracias",
    "dejá de escribir", "deja de escribir", "dejame de escribir",
    "no estoy interesado", "no estoy interesada",
    "not interested", "stop", "unsubscribe", "leave me alone",
    "don't contact me", "do not contact",
]
_OPT_OUT_BARE_NO = re.compile(r'^\s*no[\s!.?]*$')

_SEARCH_KEYWORDS = [
    "busco", "quiero", "necesito", "tienen", "tenés",
    "looking for", "i want", "i need", "do you have",
    "hay", "algún", "alguna", "some", "any",
]


def detect_intent(text: str, state: dict | None = None) -> str:
    """Detect user intent from message text. Returns intent constant."""
    t = text.lower().strip()
    state = state or {}
    stage = state.get("stage", "NEW")

    # OPT_OUT — highest priority (before human)
    if _OPT_OUT_BARE_NO.match(t) or any(k in t for k in _OPT_OUT_KEYWORDS):
        return OPT_OUT

    # Priority order matters: human first, then specific, then search

    # Human request (highest priority)
    if any(k in t for k in _HUMAN_KEYWORDS):
        return HUMAN

    # Financing
    if any(k in t for k in _FINANCING_KEYWORDS):
        return FINANCING

    # Trade-in
    if any(k in t for k in _TRADE_IN_KEYWORDS):
        return TRADE_IN

    # Photos
    if any(k in t for k in _PHOTO_KEYWORDS):
        return ASK_PHOTOS

    # Visit (check AFTER photos — "quiero verla" could be photos or visit)
    # Visit only if there's a selected car or explicit visit keywords
    _explicit_visit = [
        "quiero pasar", "quiero ir", "voy a pasar", "me acerco",
        "puedo ir", "puedo pasar", "visitar", "visitarlos",
        "quiero verla", "quiero verlo", "quiero conocer",
        "i want to visit", "i want to come", "can i come",
        "i'd like to visit", "i'll come", "i want to see it",
        "want to visit", "come see",
    ]
    _time_words = [
        "mañana", "hoy", "a la tarde", "a la mañana",
        "este finde", "sábado", "sabado", "domingo",
        "tomorrow", "today", "this weekend", "saturday", "sunday",
    ]
    has_explicit_visit = any(k in t for k in _explicit_visit)
    has_time_word = any(k in t for k in _time_words)
    if has_explicit_visit or (has_time_word and stage in ("PRESENTING", "DETAILS", "CLOSING")):
        return VISIT

    # Notify (in_transit context)
    if any(k in t for k in _NOTIFY_KEYWORDS):
        return NOTIFY

    # Details
    if any(k in t for k in _DETAIL_KEYWORDS):
        return ASK_DETAILS

    # Price
    if any(k in t for k in _PRICE_KEYWORDS):
        # If we already have a selected car, this is about that car
        if state.get("selected_car_id") or stage in ("PRESENTING", "DETAILS"):
            return ASK_PRICE
        return SEARCH_CAR  # Price query without context = searching

    # KM
    if any(k in t for k in _KM_KEYWORDS):
        return ASK_KM

    # Status
    if any(k in t for k in _STATUS_KEYWORDS):
        return ASK_STATUS

    # Search — car brand/model mentioned or general search words
    has_search = any(k in t for k in _SEARCH_KEYWORDS)
    if has_search:
        return SEARCH_CAR

    # Greeting — only if no other intent matched and message is short
    if any(k in t for k in _GREETING_KEYWORDS) and len(t.split()) <= 5:
        return GREETING

    # If any brand/model is mentioned, it's a search
    # (Will be refined with entity extraction in the engine)
    return OTHER
