"""Unit tests for LLM settings save logic in admin_settings route."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def _make_dealer(**kwargs):
    d = MagicMock()
    d.llm_api_key = kwargs.get("llm_api_key", None)
    d.llm_model = kwargs.get("llm_model", None)
    d.llm_enabled = kwargs.get("llm_enabled", None)
    d.address = ""
    d.business_hours = ""
    d.name = "Test Dealer"
    d.default_language = "es-AR"
    return d


class TestLLMSettingsSave:
    @pytest.mark.asyncio
    async def test_save_enables_llm_with_key_and_model(self):
        """Saving form with key + model + checkbox enables LLM on dealer row."""
        from src.api.routes.admin_settings import settings_save

        dealer = _make_dealer()
        form_data = {
            "llm_api_key": "sk-test123",
            "llm_model": "gpt-4o-mini",
            "llm_enabled": "on",
            "name": "Test Dealer",
            "default_language": "es-AR",
        }

        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value=form_data)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dealer
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.api.routes.admin_settings.auth_check", return_value=1):
            await settings_save(mock_request, mock_db)

        assert dealer.llm_api_key == "sk-test123"
        assert dealer.llm_model == "gpt-4o-mini"
        assert dealer.llm_enabled is True

    @pytest.mark.asyncio
    async def test_save_disables_llm_when_checkbox_unchecked(self):
        """Saving form without checkbox sets llm_enabled=False on dealer row."""
        from src.api.routes.admin_settings import settings_save

        dealer = _make_dealer(llm_enabled=True)
        form_data = {
            "llm_model": "gpt-4o-mini",
            "name": "Test Dealer",
            "default_language": "es-AR",
        }

        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value=form_data)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dealer
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.api.routes.admin_settings.auth_check", return_value=1):
            await settings_save(mock_request, mock_db)

        assert dealer.llm_enabled is False

    @pytest.mark.asyncio
    async def test_blank_api_key_preserves_existing(self):
        """Submitting blank API key field leaves dealer.llm_api_key unchanged."""
        from src.api.routes.admin_settings import settings_save

        dealer = _make_dealer(llm_api_key="sk-existing-key")
        form_data = {
            "llm_api_key": "",
            "llm_model": "gpt-4o",
            "name": "Test Dealer",
            "default_language": "es-AR",
        }

        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value=form_data)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dealer
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.api.routes.admin_settings.auth_check", return_value=1):
            await settings_save(mock_request, mock_db)

        assert dealer.llm_api_key == "sk-existing-key"
        assert dealer.llm_model == "gpt-4o"
