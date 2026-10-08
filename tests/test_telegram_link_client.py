from __future__ import annotations

import asyncio
import socket

import aiohttp
import pytest
from aioresponses import aioresponses

from bot_app.config import get_settings
from bot_app.services import api_client

TOKEN = "A" * 43
URL = "http://localhost:8080/api/bot/telegram-link/confirm"


@pytest.mark.parametrize("username", ["current_owner", None])
async def test_confirmation_sends_trusted_current_identity_and_only204_succeeds(username):
    with aioresponses() as http:
        http.post(URL, status=204)
        assert await api_client.confirm_telegram_link(TOKEN, 111, username) is None
        http.assert_called_once_with(
            URL, method="POST",
            json={"challengeToken": TOKEN, "telegramId": 111, "telegramUsername": username},
            headers={
                "X-Bot-Secret": "synthetic_bot_api_secret_only",
                "Content-Type": "application/json",
            },
            allow_redirects=False,
        )


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, api_client.TelegramLinkInvalid), (409, api_client.TelegramLinkConflict),
     (410, api_client.AuthTokenExpired), (200, api_client.TelegramLinkUnavailable),
     (201, api_client.TelegramLinkUnavailable), (302, api_client.TelegramLinkUnavailable),
     (400, aiohttp.ClientResponseError), (403, aiohttp.ClientResponseError),
     (500, aiohttp.ClientResponseError)],
)
async def test_confirmation_error_statuses_never_report_success(status, error):
    with aioresponses() as http:
        http.post(URL, status=status)
        with pytest.raises(error):
            await api_client.confirm_telegram_link(TOKEN, 111, "current_owner")


async def test_redirect_does_not_forward_challenge_or_bot_secret():
    with aioresponses() as http:
        http.post(URL, status=307, headers={"Location": "https://elsewhere.example/steal"})
        with pytest.raises(api_client.TelegramLinkUnavailable):
            await api_client.confirm_telegram_link(TOKEN, 111)
        assert sum(len(v) for v in http.requests.values()) == 1


@pytest.mark.parametrize("telegram_id", [True, False, "111", 111.0, None, 0, -1, 2**63])
async def test_telegram_identity_is_a_strict_positive_database_integer(telegram_id):
    with aioresponses() as http:
        with pytest.raises(api_client.TelegramLinkInvalid):
            await api_client.confirm_telegram_link(TOKEN, telegram_id)
        assert http.requests == {}


@pytest.mark.parametrize("token", [None, "", "A" * 42, "A" * 44, "/" * 43, "A" * 42 + "\n"])
async def test_malformed_challenge_never_leaves_the_client(token):
    with aioresponses() as http:
        with pytest.raises(api_client.TelegramLinkInvalid):
            await api_client.confirm_telegram_link(token, 111)
        assert http.requests == {}


@pytest.mark.parametrize("username", [True, 1, "@owner", "", "x" * 33, "имя"])
async def test_invalid_username_cannot_be_forwarded(username):
    with aioresponses() as http:
        with pytest.raises(api_client.TelegramLinkInvalid):
            await api_client.confirm_telegram_link(TOKEN, 111, username)
        assert http.requests == {}


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError(), asyncio.TimeoutError()])
async def test_transport_failures_remain_failures_and_log_no_secrets(error, caplog):
    with aioresponses() as http:
        http.post(URL, exception=error)
        with pytest.raises(type(error)):
            await api_client.confirm_telegram_link(TOKEN, 111)
    assert TOKEN not in caplog.text
    assert "synthetic_bot_api_secret_only" not in caplog.text


def test_test_boundary_blocks_real_network_and_uses_no_dotenv():
    settings = get_settings()
    assert settings.bot_api_secret == "synthetic_bot_api_secret_only"
    assert settings.api_base_url == "http://localhost:8080"
    from bot_app import config

    assert config.load_dotenv() is False
    with pytest.raises(AssertionError, match="Environment files"), open(".env"):
        pass
    with socket.socket() as sock, pytest.raises(AssertionError, match="Real network"):
        sock.connect(("127.0.0.1", 9))
