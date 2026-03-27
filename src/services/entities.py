"""Entity extraction from user messages. Rule-based, no LLM."""

import re
from typing import Any, Optional

# Argentina-market brands and common models
BRANDS = {
    "toyota": "Toyota", "ford": "Ford", "volkswagen": "Volkswagen", "vw": "Volkswagen",
    "fiat": "Fiat", "chevrolet": "Chevrolet", "chevy": "Chevrolet",
    "honda": "Honda", "nissan": "Nissan", "renault": "Renault",
    "peugeot": "Peugeot", "citroen": "Citroën", "citroën": "Citroën",
    "hyundai": "Hyundai", "kia": "Kia", "jeep": "Jeep",
    "ram": "Ram", "dodge": "Dodge", "bmw": "BMW", "mercedes": "Mercedes-Benz",
    "audi": "Audi", "mitsubishi": "Mitsubishi", "suzuki": "Suzuki",
    "chery": "Chery", "geely": "Geely", "haval": "Haval",
}

MODELS = {
    "hilux": "Hilux", "ranger": "Ranger", "amarok": "Amarok",
    "cronos": "Cronos", "onix": "Onix", "corolla": "Corolla",
    "hr-v": "HR-V", "hrv": "HR-V", "civic": "Civic", "city": "City",
    "kicks": "Kicks", "frontier": "Frontier", "versa": "Versa",
    "cruze": "Cruze", "tracker": "Tracker", "montana": "Montana",
    "taos": "Taos", "tiguan": "Tiguan", "polo": "Polo", "virtus": "Virtus",
    "t-cross": "T-Cross", "tcross": "T-Cross",
    "208": "208", "2008": "2008", "3008": "3008", "partner": "Partner",
    "duster": "Duster", "logan": "Logan", "sandero": "Sandero", "kangoo": "Kangoo",
    "argo": "Argo", "toro": "Toro", "strada": "Strada", "pulse": "Pulse",
    "renegade": "Renegade", "compass": "Compass", "wrangler": "Wrangler",
    "etios": "Etios", "yaris": "Yaris", "rav4": "RAV4", "sw4": "SW4",
    "fortuner": "Fortuner", "camry": "Camry",
    "ecosport": "EcoSport", "territory": "Territory", "maverick": "Maverick",
    "bronco": "Bronco", "f-150": "F-150", "f150": "F-150",
    "tucson": "Tucson", "creta": "Creta", "santa fe": "Santa Fe",
    "seltos": "Seltos", "sportage": "Sportage", "sorento": "Sorento",
    "ram 1500": "1500", "ram 2500": "2500",
}

# English stop words for language detection
_EN_STOPS = {
    "the", "is", "are", "was", "were", "do", "does", "did",
    "have", "has", "had", "will", "would", "could", "should",
    "can", "may", "might", "must", "shall", "this", "that",
    "these", "those", "am", "been", "being",
    "i", "you", "he", "she", "it", "we", "they",
    "my", "your", "his", "her", "its", "our", "their",
    "what", "which", "who", "when", "where", "why", "how",
    "looking", "want", "need", "interested", "please",
}

_EN_TRIGGER_PHRASES = [
    "do you have", "i'm looking", "i am looking", "how much",
    "can you", "i want to", "i need", "is it available",
    "send me", "tell me", "let me", "show me",
    "good morning", "good afternoon", "good evening",
    "thank you", "thanks",
]


def detect_language(text: str) -> str:
    """Simple heuristic language detection. Returns 'es' or 'en'."""
    t = text.lower().strip()

    # Check for explicit English phrases
    for phrase in _EN_TRIGGER_PHRASES:
        if phrase in t:
            return "en"

    # Count English stop words
    words = set(re.findall(r"\b\w+\b", t))
    en_count = len(words & _EN_STOPS)

    # If >30% of words are English stop words, likely English
    if len(words) > 0 and en_count / len(words) > 0.3:
        return "en"

    return "es"


def extract_name(text: str) -> Optional[str]:
    """Extract name from 'me llamo X' / 'my name is X' patterns."""
    t = text.strip()
    # Spanish
    m = re.search(r"(?:me llamo|soy|mi nombre es)\s+([A-ZÁÉÍÓÚa-záéíóú]+(?:\s+[A-ZÁÉÍÓÚa-záéíóú]+)?)", t, re.IGNORECASE)
    if m:
        return m.group(1).strip().title()
    # English
    m = re.search(r"(?:my name is|i'm|i am|call me)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", t, re.IGNORECASE)
    if m:
        return m.group(1).strip().title()
    return None


def extract_time(text: str) -> Optional[str]:
    """Extract time/day preference from message."""
    t = text.lower().strip()
    parts = []

    # Day
    if "mañana a la mañana" in t or "tomorrow morning" in t:
        parts.append("mañana a la mañana")
    elif "mañana a la tarde" in t or "tomorrow afternoon" in t or "tomorrow evening" in t:
        parts.append("mañana a la tarde")
    elif "hoy a la mañana" in t or "today morning" in t or "this morning" in t:
        parts.append("hoy a la mañana")
    elif "hoy a la tarde" in t or "today afternoon" in t or "this afternoon" in t:
        parts.append("hoy a la tarde")
    elif "a la mañana" in t or "in the morning" in t:
        parts.append("a la mañana")
    elif "a la tarde" in t or "in the afternoon" in t or "in the evening" in t:
        parts.append("a la tarde")
    elif "mañana" in t or "tomorrow" in t:
        parts.append("mañana")
    elif "hoy" in t or "today" in t:
        parts.append("hoy")
    elif "sábado" in t or "sabado" in t or "saturday" in t:
        parts.append("sábado")
    elif "domingo" in t or "sunday" in t:
        parts.append("domingo")
    elif "finde" in t or "weekend" in t:
        parts.append("este finde")

    # Hours
    hour_m = re.search(r"(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm|hs?))?)", t, re.IGNORECASE)
    if hour_m:
        parts.append(hour_m.group(1))

    return ", ".join(parts) if parts else None


def extract_brand(text: str) -> Optional[str]:
    """Extract car brand from text."""
    t = text.lower().strip()
    for key, val in BRANDS.items():
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            return val
    return None


def extract_model(text: str) -> Optional[str]:
    """Extract car model from text."""
    t = text.lower().strip()
    for key, val in MODELS.items():
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            return val
    return None


def extract_year(text: str) -> Optional[int]:
    """Extract year from text (2000-2030 range)."""
    m = re.search(r"\b(20[0-3]\d)\b", text)
    if m:
        return int(m.group(1))
    return None


def extract_budget(text: str) -> tuple[Optional[float], Optional[float]]:
    """Extract budget range from text. Returns (min, max)."""
    t = text.lower().strip()
    budget_max = None
    budget_min = None

    # "entre X y Y millones"
    m = re.search(r"entre\s+(\d+)\s+y\s+(\d+)\s*(?:millones?|m|mills?)", t)
    if m:
        budget_min = int(m.group(1)) * 1_000_000
        budget_max = int(m.group(2)) * 1_000_000
        return budget_min, budget_max

    # "between X and Y"
    m = re.search(r"between\s+(\d+)\s+and\s+(\d+)", t)
    if m:
        v1, v2 = int(m.group(1)), int(m.group(2))
        if v1 < 100:
            v1 *= 1_000_000
        if v2 < 100:
            v2 *= 1_000_000
        return v1, v2

    # "X millones" / "Xm" pattern
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:millones?|m\b|mills?)", t)
    if m:
        budget_max = float(m.group(1)) * 1_000_000
        return None, budget_max

    # "$X" or plain large numbers
    m = re.search(r"\$?\s*(\d{6,})", t.replace(".", "").replace(",", ""))
    if m:
        budget_max = float(m.group(1))
        return None, budget_max

    # "Xk" pattern
    m = re.search(r"(\d+)\s*k\b", t)
    if m:
        budget_max = int(m.group(1)) * 1_000
        return None, budget_max

    return budget_min, budget_max


def extract_condition(text: str) -> Optional[str]:
    """Extract condition preference."""
    t = text.lower().strip()
    if "0 km" in t or "0km" in t or "cero km" in t or "zero km" in t or "brand new" in t:
        return "zero_km"
    if "nuevo" in t or "new" in t:
        return "new"
    if "usado" in t or "used" in t or "second hand" in t:
        return "used"
    return None


def extract_all(text: str) -> dict[str, Any]:
    """Extract all entities from a message."""
    return {
        "name": extract_name(text),
        "time": extract_time(text),
        "brand": extract_brand(text),
        "model": extract_model(text),
        "year": extract_year(text),
        "budget_min": extract_budget(text)[0],
        "budget_max": extract_budget(text)[1],
        "condition": extract_condition(text),
        "language": detect_language(text),
    }
