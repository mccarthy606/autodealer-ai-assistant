"""Tests for intent detection and entity extraction."""

import pytest

from src.services.intent import detect_intent, SEARCH_CAR, ASK_PHOTOS, VISIT, FINANCING, TRADE_IN, HUMAN, GREETING
from src.services.entities import (
    detect_language, extract_name, extract_time, extract_brand,
    extract_model, extract_year, extract_budget, extract_condition,
)


class TestIntentDetection:
    def test_greeting_es(self):
        assert detect_intent("Hola!") == GREETING

    def test_greeting_en(self):
        assert detect_intent("Hello") == GREETING

    def test_search_brand(self):
        assert detect_intent("Tienen Toyota?") == SEARCH_CAR

    def test_search_model(self):
        assert detect_intent("Busco una Hilux") == SEARCH_CAR

    def test_photos_es(self):
        assert detect_intent("Mandame fotos") == ASK_PHOTOS

    def test_photos_en(self):
        assert detect_intent("Can you send me photos?") == ASK_PHOTOS

    def test_visit_es(self):
        assert detect_intent("Quiero pasar mañana") == VISIT

    def test_visit_en(self):
        assert detect_intent("I want to come tomorrow") == VISIT

    def test_financing(self):
        assert detect_intent("Me interesa financiar en cuotas") == FINANCING

    def test_trade_in(self):
        assert detect_intent("Quiero hacer una permuta") == TRADE_IN

    def test_human_request(self):
        assert detect_intent("Quiero hablar con un vendedor") == HUMAN


class TestLanguageDetection:
    def test_spanish(self):
        assert detect_language("Hola, quiero saber el precio") == "es"

    def test_english(self):
        assert detect_language("Hi, do you have any cars?") == "en"

    def test_english_looking(self):
        assert detect_language("I'm looking for a Toyota") == "en"

    def test_spanish_default(self):
        assert detect_language("Hilux") == "es"  # Default


class TestEntityExtraction:
    def test_name_es(self):
        assert extract_name("Me llamo Juan Carlos") == "Juan Carlos"

    def test_name_en(self):
        assert extract_name("My name is John") == "John"

    def test_time_tomorrow(self):
        assert extract_time("Quiero ir mañana") == "mañana"

    def test_time_tomorrow_afternoon(self):
        assert extract_time("Paso mañana a la tarde") == "mañana a la tarde"

    def test_time_today(self):
        assert extract_time("Puedo ir hoy") == "hoy"

    def test_brand_toyota(self):
        assert extract_brand("Tienen alguna Toyota?") == "Toyota"

    def test_brand_vw(self):
        assert extract_brand("Me interesa vw") == "Volkswagen"

    def test_model_hilux(self):
        assert extract_model("Busco una Hilux") == "Hilux"

    def test_year(self):
        assert extract_year("Quiero modelo 2023") == 2023

    def test_budget_millones(self):
        _, bmax = extract_budget("Tengo hasta 15 millones")
        assert bmax == 15_000_000

    def test_budget_k(self):
        _, bmax = extract_budget("Budget around 500k")
        assert bmax == 500_000

    def test_condition_0km(self):
        assert extract_condition("Busco 0 km") == "zero_km"

    def test_condition_used(self):
        assert extract_condition("Quiero usado") == "used"
