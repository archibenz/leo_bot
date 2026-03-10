from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot_app.config import get_settings

logger = logging.getLogger(__name__)


async def _get(path: str) -> Any:
    settings = get_settings()
    url = f"{settings.api_base_url}{path}"
    headers = {"X-Bot-Secret": settings.bot_api_secret}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _post(path: str, json: dict | None = None) -> Any:
    settings = get_settings()
    url = f"{settings.api_base_url}{path}"
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=json or {}, headers=headers) as resp:
            resp.raise_for_status()
            if resp.content_length and resp.content_length > 0:
                return await resp.json()
            return None


async def _patch(path: str, json: dict) -> Any:
    settings = get_settings()
    url = f"{settings.api_base_url}{path}"
    headers = {"X-Bot-Secret": settings.bot_api_secret, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=json, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _delete(path: str) -> None:
    settings = get_settings()
    url = f"{settings.api_base_url}{path}"
    headers = {"X-Bot-Secret": settings.bot_api_secret}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as resp:
            resp.raise_for_status()


async def get_dashboard() -> dict:
    return await _get("/api/bot/admin/dashboard")


async def get_products() -> list[dict]:
    return await _get("/api/bot/admin/products")


async def update_stock(product_id: str, quantity: int) -> dict:
    return await _patch(f"/api/bot/admin/products/{product_id}/stock", {"quantity": quantity})


async def get_alerts() -> list[dict]:
    return await _get("/api/bot/admin/alerts")


async def acknowledge_alert(alert_id: str) -> None:
    await _post(f"/api/bot/admin/alerts/{alert_id}/acknowledge")


async def get_collections() -> list[dict]:
    return await _get("/api/bot/admin/collections")


async def create_product(data: dict) -> dict:
    return await _post("/api/bot/admin/products", json=data)


async def delete_product(product_id: str) -> None:
    await _delete(f"/api/bot/admin/products/{product_id}?permanent=false")


async def create_collection(name: str, description: str | None = None) -> dict:
    return await _post("/api/bot/admin/collections", json={
        "name": name,
        "description": description,
        "sortOrder": 0,
    })


async def upload_image(file_bytes: bytes, filename: str, content_type: str) -> str:
    settings = get_settings()
    url = f"{settings.api_base_url}/api/bot/admin/upload"
    headers = {"X-Bot-Secret": settings.bot_api_secret}
    data = aiohttp.FormData()
    data.add_field("file", file_bytes, filename=filename, content_type=content_type)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers) as resp:
            resp.raise_for_status()
            result = await resp.json()
            return result["url"]
