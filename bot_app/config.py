from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from aiogram.utils.token import TokenValidationError, validate_token


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    gift_video_url: str | None
    api_base_url: str
    bot_api_secret: str
    bot_username: str
    site_url: str
    pages_url: str
    wb_seller_id: str


def _parse_admin_ids(raw_value: str | None) -> tuple[int, ...]:
    if not raw_value:
        return tuple()
    ids: list[int] = []
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return tuple(ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    admin_ids_raw = os.getenv("ADMIN_IDS")
    gift_video_url = os.getenv("GIFT_VIDEO_URL")
    api_base_url = os.getenv("API_BASE_URL")
    bot_api_secret = os.getenv("BOT_API_SECRET")
    bot_username = os.getenv("BOT_USERNAME", "reinasleo_bot")
    site_url = os.getenv("SITE_URL", "https://reinasleo.com")
    pages_url = os.getenv("PAGES_URL", "https://reinasleo.com/pages")
    wb_seller_id = os.getenv("WB_SELLER_ID", "609562")

    if not bot_token:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    if not api_base_url:
        raise RuntimeError("API_BASE_URL environment variable is required")
    if not bot_api_secret:
        raise RuntimeError("BOT_API_SECRET environment variable is required")

    admin_ids = _parse_admin_ids(admin_ids_raw)
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS environment variable is required (comma-separated Telegram user IDs)")

    try:
        validate_token(bot_token)
    except TokenValidationError as exc:
        raise RuntimeError(
            "BOT_TOKEN is set but invalid. Copy the token exactly as provided by BotFather"
        ) from exc

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        gift_video_url=gift_video_url,
        api_base_url=api_base_url,
        bot_api_secret=bot_api_secret,
        bot_username=bot_username,
        site_url=site_url,
        pages_url=pages_url,
        wb_seller_id=wb_seller_id,
    )
