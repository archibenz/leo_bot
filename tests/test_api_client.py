import os
from unittest.mock import patch

import pytest
from aioresponses import aioresponses

from bot_app.config import get_settings
from bot_app.services.api_client import bot_login, check_user, UserNotFound, AuthTokenExpired

API_BASE = "http://localhost:8080"
ENV = {
    "BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    "ADMIN_IDS": "111",
    "BOT_API_SECRET": "test-secret",
    "API_BASE_URL": API_BASE,
}


@pytest.fixture(autouse=True)
def setup_env():
    get_settings.cache_clear()
    with patch.dict(os.environ, ENV, clear=True):
        yield
    get_settings.cache_clear()


async def test_bot_login_success():
    with aioresponses() as m:
        m.post(f"{API_BASE}/api/bot/login", payload={"loginToken": "tok123"})
        token = await bot_login(telegram_id=111, auth_token="auth_abc")
        assert token == "tok123"


async def test_bot_login_user_not_found():
    with aioresponses() as m:
        m.post(f"{API_BASE}/api/bot/login", status=404)
        with pytest.raises(UserNotFound):
            await bot_login(telegram_id=999, auth_token="auth_abc")


async def test_bot_login_token_expired():
    with aioresponses() as m:
        m.post(f"{API_BASE}/api/bot/login", status=410)
        with pytest.raises(AuthTokenExpired):
            await bot_login(telegram_id=111, auth_token="expired_tok")


async def test_check_user_registered():
    with aioresponses() as m:
        m.post(f"{API_BASE}/api/bot/check-user", payload={"registered": True, "name": "Alice"})
        result = await check_user(telegram_id=111)
        assert result == {"registered": True, "name": "Alice"}
