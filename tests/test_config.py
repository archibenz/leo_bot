import os
from unittest.mock import patch

import pytest

from bot_app.config import get_settings, _parse_admin_ids


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def no_dotenv():
    with patch("bot_app.config.load_dotenv"):
        yield


def test_missing_bot_token_raises(no_dotenv):
    env = {"ADMIN_IDS": "123", "BOT_API_SECRET": "secret"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(RuntimeError, match="BOT_TOKEN"):
            get_settings()


def test_missing_admin_ids_raises(no_dotenv):
    env = {
        "BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "BOT_API_SECRET": "secret",
        "API_BASE_URL": "http://localhost:8080",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(RuntimeError, match="ADMIN_IDS"):
            get_settings()


def test_missing_bot_api_secret_raises(no_dotenv):
    env = {
        "BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "ADMIN_IDS": "123",
        "API_BASE_URL": "http://localhost:8080",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(RuntimeError, match="BOT_API_SECRET"):
            get_settings()


def test_parse_admin_ids_valid():
    result = _parse_admin_ids("111, 222, 333")
    assert result == (111, 222, 333)


def test_parse_admin_ids_empty():
    assert _parse_admin_ids("") == ()
    assert _parse_admin_ids(None) == ()
