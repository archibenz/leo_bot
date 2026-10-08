from __future__ import annotations

import asyncio
import re

import aiohttp
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from bot_app.services import api_client

router = Router()

INVALID_LINK = "Ссылка недействительна. Создайте новую в аккаунте на сайте."
UNAVAILABLE = "Сейчас не удалось подтвердить привязку. Попробуйте позже."


@router.message(CommandStart(deep_link=True), F.text.regexp(r"^/start(?:@\w+)?\s+link_"))
async def telegram_link(message: Message, command: CommandObject) -> None:
    if message.chat.type != "private" or message.from_user is None:
        await message.answer("Для привязки Telegram откройте ссылку в личном чате с ботом.")
        return
    token = (command.args or "")[5:]
    if (
        re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None
        or type(message.from_user.id) is not int
        or not 0 < message.from_user.id < 2**63
        or message.from_user.is_bot
    ):
        await message.answer(INVALID_LINK)
        return
    try:
        await api_client.confirm_telegram_link(
            token, message.from_user.id, message.from_user.username,
        )
    except api_client.TelegramLinkConflict:
        await message.answer("Telegram уже связан с другой учётной записью. Привязка не изменена.")
    except api_client.AuthTokenExpired:
        await message.answer("Срок ссылки истёк или она уже использована. Создайте новую на сайте.")
    except api_client.TelegramLinkInvalid:
        await message.answer(INVALID_LINK)
    except (api_client.TelegramLinkUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
        await message.answer(UNAVAILABLE)
    else:
        await message.answer("Telegram подтверждён для вашей учётной записи на сайте. Вернитесь на сайт.")
