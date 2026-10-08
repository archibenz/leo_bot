from __future__ import annotations

import logging
import re

import aiohttp

from bot_app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)


class UserNotFound(Exception):
    pass


class AuthTokenExpired(Exception):
    pass


class TelegramLinkConflict(Exception):
    pass


class TelegramLinkInvalid(Exception):
    pass


class TelegramLinkUnavailable(Exception):
    pass


async def confirm_telegram_link(
    challenge_token: str,
    telegram_id: int,
    telegram_username: str | None = None,
) -> None:
    if (
        not isinstance(challenge_token, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge_token) is None
        or type(telegram_id) is not int
        or not 0 < telegram_id < 2**63
        or telegram_username is not None and (
            not isinstance(telegram_username, str)
            or re.fullmatch(r"[A-Za-z0-9_]{1,32}", telegram_username) is None
        )
    ):
        raise TelegramLinkInvalid()
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/api/bot/telegram-link/confirm"
    payload = {
        "challengeToken": challenge_token,
        "telegramId": telegram_id,
        "telegramUsername": telegram_username,
    }
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}
    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session, session.post(
        url, json=payload, headers=headers, allow_redirects=False
    ) as response:
        if response.status == 204:
            return
        if response.status == 401:
            raise TelegramLinkInvalid()
        if response.status == 409:
            raise TelegramLinkConflict()
        if response.status == 410:
            raise AuthTokenExpired()
        response.raise_for_status()
        raise TelegramLinkUnavailable()


async def bot_login(telegram_id: int, auth_token: str) -> str:
    """Call POST /api/bot/login and return loginToken. Raises UserNotFound if user doesn't exist."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/login"
    payload = {"telegramId": telegram_id, "authToken": auth_token}
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
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

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
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

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()


async def log_visit(telegram_id: int, username: str | None = None,
                    first_name: str | None = None, last_name: str | None = None,
                    language_code: str | None = None, source: str = "organic") -> None:
    """Call POST /api/bot/visit to log a bot visit. Errors are logged but never raised."""
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/visit"
    payload = {
        "telegramId": telegram_id,
        "username": username,
        "firstName": first_name,
        "lastName": last_name,
        "languageCode": language_code,
        "source": source,
    }
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status >= 400:
                    logger.warning("log_visit failed: status=%s telegram_id=%s", resp.status, telegram_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_visit error for telegram_id=%s: %s", telegram_id, exc)


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

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 400:
                raise AuthTokenExpired("auth_token_not_found or invalid")
            if resp.status == 410:
                raise AuthTokenExpired("auth_token expired")
            resp.raise_for_status()
            data = await resp.json()
            return data["loginToken"]
