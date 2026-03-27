"""Tests for visit intent."""

import pytest

from src.services.visit_confirmation import (
    detect_visit_intent,
    extract_visit_details,
    format_visit_response,
)


def test_detect_visit_intent_positive():
    assert detect_visit_intent("quiero pasar mañana") is True
    assert detect_visit_intent("Sí, voy mañana a la mañana") is True
    assert detect_visit_intent("Me llamo Juan, paso hoy") is True
    assert detect_visit_intent("a la tarde puedo") is True
    assert detect_visit_intent("Quiero pasar mañana") is True
    assert detect_visit_intent("puedo ir este finde") is True
    assert detect_visit_intent("horario del salón") is True


def test_detect_visit_intent_negative():
    assert detect_visit_intent("tienen Hilux?") is False
    assert detect_visit_intent("cuanto cuesta") is False


def test_extract_name():
    name, _ = extract_visit_details("Me llamo Juan, quiero pasar")
    assert name == "Juan"

    name, _ = extract_visit_details("Sí, me llamo María")
    assert name == "María"


def test_extract_time():
    _, time_str = extract_visit_details("quiero pasar mañana a la mañana")
    assert "mañana" in time_str

    _, time_str = extract_visit_details("voy hoy")
    assert "hoy" in time_str


def test_format_response():
    r = format_visit_response("Juan", "Av. Libertador 1234")
    assert "Juan" in r
    assert "Av. Libertador 1234" in r
    assert "¿A qué hora te queda bien?" in r

    r2 = format_visit_response(None, None)
    assert "Perfecto" in r2
    assert "en el salón" in r2
