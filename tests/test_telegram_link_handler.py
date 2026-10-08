from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import GetMe, SendMessage
from aiogram.types import Chat, Message, Update, User

from bot_app.handlers import register_handlers, registration, telegram_link
from bot_app.services import api_client
from bot_app.states import AdminStates, RegistrationStates

TOKEN = "A" * 43


class FakeTelegramSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[SendMessage] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=123456, is_bot=True, first_name="Synthetic", username="synthetic_test_bot")
        if not isinstance(method, SendMessage):
            raise TypeError("Unexpected Telegram operation in synthetic test")
        self.messages.append(method)
        return Message(
            message_id=99, date=datetime.now(timezone.utc), text=method.text,
            chat=Chat(id=int(method.chat_id), type="private"),
        )

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("Telegram downloads are disabled in synthetic tests")
        yield b""


@pytest.fixture(scope="module")
def dispatcher() -> Dispatcher:
    dp = Dispatcher()
    register_handlers(dp)
    return dp


@pytest.fixture
def link_api(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    confirm = AsyncMock()
    monkeypatch.setattr(api_client, "confirm_telegram_link", confirm)
    monkeypatch.setattr(registration, "log_visit", AsyncMock())
    monkeypatch.setattr(registration, "bot_login", AsyncMock(return_value="synthetic_login_token"))
    monkeypatch.setattr(registration, "check_user", AsyncMock(return_value={"registered": True, "name": "Owner"}))
    return confirm


async def _dispatch(dispatcher, text, *, username="current_owner", chat_type="private", sender=True):
    session = FakeTelegramSession()
    bot = Bot(token="123456:synthetic_bot_token_only_123456789", session=session)
    update = Update(
        update_id=1,
        message=Message(
            message_id=1, date=datetime.now(timezone.utc), text=text,
            chat=Chat(id=111 if chat_type == "private" else -100, type=chat_type),
            from_user=User(id=111, is_bot=False, first_name="Owner", username=username) if sender else None,
        ),
    )
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    return [m.text for m in session.messages]


@pytest.mark.parametrize("username", ["current_owner", None])
async def test_link_uses_authenticated_sender_and_current_username(dispatcher, link_api, username, caplog):
    replies = await _dispatch(dispatcher, f"/start link_{TOKEN}", username=username)
    link_api.assert_awaited_once_with(TOKEN, 111, username)
    assert len(replies) == 1 and "Telegram подтверждён" in replies[0]
    assert "Вернитесь на сайт" in replies[0]
    registration.bot_login.assert_not_awaited()
    registration.check_user.assert_not_awaited()
    registration.log_visit.assert_not_awaited()
    assert TOKEN not in caplog.text and all(TOKEN not in reply for reply in replies)


async def test_link_accepts_command_mention_without_real_getme(dispatcher, link_api):
    replies = await _dispatch(dispatcher, f"/start@synthetic_test_bot link_{TOKEN}")
    link_api.assert_awaited_once_with(TOKEN, 111, "current_owner")
    assert "Telegram подтверждён" in replies[0]


@pytest.mark.parametrize("payload", ["link_", "link_short", "link_" + "A" * 42,
                                      "link_" + "A" * 44, "link_" + "/" * 43,
                                      "link_" + TOKEN + " extra"])
async def test_malformed_link_is_handled_without_registration_or_api(dispatcher, link_api, payload):
    replies = await _dispatch(dispatcher, f"/start {payload}")
    assert replies == [telegram_link.INVALID_LINK]
    link_api.assert_not_awaited()
    registration.check_user.assert_not_awaited()
    registration.log_visit.assert_not_awaited()


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
async def test_group_challenge_is_not_confirmed(dispatcher, link_api, chat_type):
    replies = await _dispatch(dispatcher, f"/start link_{TOKEN}", chat_type=chat_type)
    assert len(replies) == 1 and "личном чате" in replies[0]
    link_api.assert_not_awaited()
    registration.check_user.assert_not_awaited()


async def test_missing_sender_is_not_confirmed(dispatcher, link_api):
    replies = await _dispatch(dispatcher, f"/start link_{TOKEN}", sender=False)
    assert len(replies) == 1 and "личном чате" in replies[0]
    link_api.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [(api_client.TelegramLinkConflict(), "другой учётной записью"),
     (api_client.AuthTokenExpired(), "истёк или она уже использована"),
     (api_client.TelegramLinkInvalid(), "Ссылка недействительна"),
     (api_client.TelegramLinkUnavailable(), "Попробуйте позже"),
     (aiohttp.ClientConnectionError(), "Попробуйте позже"),
     (asyncio.TimeoutError(), "Попробуйте позже")],
)
async def test_api_errors_are_safe_russian_replies(dispatcher, link_api, error, expected, caplog):
    link_api.side_effect = error
    replies = await _dispatch(dispatcher, f"/start link_{TOKEN}")
    assert len(replies) == 1 and expected in replies[0]
    assert "Telegram подтверждён" not in replies[0]
    assert TOKEN not in caplog.text and TOKEN not in replies[0]


@pytest.mark.parametrize("state", [RegistrationStates.waiting_phone, AdminStates.add_title])
async def test_link_router_precedes_existing_fsm_handlers_and_preserves_drafts(dispatcher, link_api, state):
    key = StorageKey(bot_id=123456, chat_id=111, user_id=111)
    await dispatcher.storage.set_state(key, state)
    await dispatcher.storage.set_data(key, {"draft": "keep_me"})
    try:
        replies = await _dispatch(dispatcher, f"/start link_{TOKEN}")
        assert "Telegram подтверждён" in replies[0]
        link_api.assert_awaited_once()
        assert await dispatcher.storage.get_state(key) == state.state
        assert await dispatcher.storage.get_data(key) == {"draft": "keep_me"}
    finally:
        await dispatcher.storage.set_state(key, None)
        await dispatcher.storage.set_data(key, {})


async def test_organic_start_still_reaches_registration(dispatcher, link_api):
    replies = await _dispatch(dispatcher, "/start")
    link_api.assert_not_awaited()
    registration.check_user.assert_awaited_once_with(111)
    assert len(replies) == 1 and "С возвращением" in replies[0]


async def test_existing_auth_deeplink_still_reaches_registration(dispatcher, link_api):
    replies = await _dispatch(dispatcher, "/start auth_existing_auth_token")
    link_api.assert_not_awaited()
    registration.bot_login.assert_awaited_once_with(111, "existing_auth_token")
    assert len(replies) == 1 and "Вход выполнен успешно" in replies[0]


def test_link_router_registered_before_registration(dispatcher):
    assert dispatcher.sub_routers.index(telegram_link.router) < dispatcher.sub_routers.index(registration.router)
