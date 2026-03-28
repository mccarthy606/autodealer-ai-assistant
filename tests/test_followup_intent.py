"""Tests for OPT_OUT intent detection."""

import pytest
from src.services.intent import detect_intent, OPT_OUT, HUMAN, VISIT, SEARCH_CAR


class TestOptOutDetection:
    """OPT_OUT fires for opt-out phrases, does not fire for normal messages."""

    def test_bare_no_lowercase(self):
        assert detect_intent("no") == OPT_OUT

    def test_bare_no_with_exclamation(self):
        assert detect_intent("no!") == OPT_OUT

    def test_bare_no_with_trailing_space(self):
        assert detect_intent("  no  ") == OPT_OUT

    def test_no_me_interesa(self):
        assert detect_intent("no me interesa") == OPT_OUT

    def test_no_gracias(self):
        assert detect_intent("no gracias") == OPT_OUT

    def test_no_comma_gracias(self):
        assert detect_intent("no, gracias") == OPT_OUT

    def test_deja_de_escribir(self):
        assert detect_intent("deja de escribir") == OPT_OUT

    def test_stop_english(self):
        assert detect_intent("stop") == OPT_OUT

    def test_not_interested_english(self):
        assert detect_intent("not interested") == OPT_OUT


class TestOptOutNonRegression:
    """OPT_OUT must NOT fire when it shouldn't."""

    def test_no_tengo_auto(self):
        # "no tengo" is not opt-out
        result = detect_intent("no tengo auto pero busco uno")
        assert result != OPT_OUT

    def test_no_quiero_el_rojo_not_opt_out(self):
        # "no quiero" without a keyword match should NOT opt out a customer
        # who is simply expressing a colour preference — non-regression for BLOCKER 3
        result = detect_intent("no quiero el rojo, quiero el azul")
        assert result != OPT_OUT

    def test_no_quiero_otro_not_opt_out(self):
        # Another shopping-preference sentence with "no quiero"
        result = detect_intent("no quiero ese, mostramelo mas barato")
        assert result != OPT_OUT

    def test_human_intent_unaffected(self):
        # Plain human trigger still works
        result = detect_intent("quiero hablar con un vendedor")
        assert result == HUMAN

    def test_visit_intent_unaffected(self):
        result = detect_intent("quiero pasar manana")
        assert result == VISIT

    def test_search_intent_unaffected(self):
        result = detect_intent("busco una hilux")
        assert result == SEARCH_CAR
