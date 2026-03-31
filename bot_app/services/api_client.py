from __future__ import annotations

import logging

import aiohttp

from bot_app.config import get_settings

logger = logging.getLogger(__name__)


class UserNotFound(Exception):
    pass


class AuthTokenExpired(Exception):
    pass


async def bot_login(telegram_id: int, auth_token: str) -> str:
    """Call POST /api/bot/login and return loginToken. Raises UserNotFound if user doesn't exist."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/login"
    payload = {"telegramId": telegram_id, "authToken": auth_token}
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 400:
                raise AuthTokenExpired("auth_token_not_found or invalid")
            if resp.status == 404:
                raise UserNotFound(f"No user for telegram_id={telegram_id}")
            if resp.status == 410:
                raise AuthTokenExpired("auth_token expired")
            resp.raise_for_status()
            data = await resp.json()
            return data["loginToken"]


async def check_user(telegram_id: int) -> dict:
    """Call POST /api/bot/check-user. Returns {"registered": bool, "name": str|None}."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/check-user"
    payload = {"telegramId": telegram_id}
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()


async def bot_organic_register(telegram_id: int, phone: str, first_name: str,
                               surname: str | None = None) -> None:
    """Call POST /api/bot/organic-register. No token returned."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/organic-register"
    payload = {
        "telegramId": telegram_id,
        "phone": phone,
        "firstName": first_name,
        "surname": surname,
    }
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()


async def bot_register(telegram_id: int, phone: str, first_name: str, auth_token: str,
                        surname: str | None = None) -> str:
    """Call POST /api/bot/register and return loginToken."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/register"
    payload = {
        "telegramId": telegram_id,
        "phone": phone,
        "firstName": first_name,
        "surname": surname,
        "authToken": auth_token,
    }
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 400:
                raise AuthTokenExpired("auth_token_not_found or invalid")
            if resp.status == 410:
                raise AuthTokenExpired("auth_token expired")
            resp.raise_for_status()
            data = await resp.json()
            return data["loginToken"]
