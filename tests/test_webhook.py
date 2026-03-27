"""Tests for WhatsApp webhook extraction."""

import pytest

from src.webhooks.whatsapp import extract_whatsapp_message


def test_extract_twilio_style():
    payload = {"From": "+5491112345678", "Body": "Hola, tienen Hilux?"}
    result = extract_whatsapp_message(payload)
    assert result == ("+5491112345678", "Hola, tienen Hilux?")


def test_extract_meta_style():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": "5491112345678", "type": "text", "text": {"body": "Busco auto 0 km"}},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    result = extract_whatsapp_message(payload)
    assert result == ("5491112345678", "Busco auto 0 km")


def test_extract_generic():
    payload = {"user_phone": "+5491198765432", "message_text": "Hola"}
    result = extract_whatsapp_message(payload)
    assert result == ("+5491198765432", "Hola")


def test_extract_unparseable():
    result = extract_whatsapp_message({})
    assert result is None
