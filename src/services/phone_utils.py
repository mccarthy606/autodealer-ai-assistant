"""Phone number normalization for Argentina."""

import re


def normalize_ar_phone(area_code: str = "", number: str = "") -> str:
    """
    Normalize Argentine phone number to WhatsApp E.164 format.

    WhatsApp expects: 5491XXXXXXXX (no + prefix, country=54, mobile=9, area+number).
    Handles common ML formats:
    - area_code="11", number="12345678" -> "5491112345678"
    - area_code="351", number="1234567" -> "5493511234567"
    - Full numbers like "01112345678" or "+5491112345678"

    Returns normalized number string, or empty string if unparseable.
    """
    # Combine and strip all non-digit characters
    raw = re.sub(r"[^\d]", "", f"{area_code}{number}")

    if not raw:
        return ""

    # Already starts with country code 54
    if raw.startswith("54"):
        raw = raw[2:]

    # Remove leading 0 (local format: 011...)
    if raw.startswith("0"):
        raw = raw[1:]

    # Remove leading 15 (old mobile prefix in local calls)
    # Only if area code is present (e.g., 11 15 XXXX XXXX)
    if len(raw) > 10 and "15" in raw[2:4]:
        raw = raw[:2] + raw[4:]

    # Remove mobile prefix 9 if already present (avoid double 9)
    if raw.startswith("9") and len(raw) == 11:
        raw = raw[1:]

    # Validate length: should be 8-12 digits (area + number)
    if len(raw) < 8 or len(raw) > 12:
        return ""

    # Build: 54 + 9 + area_code + number
    return f"549{raw}"
