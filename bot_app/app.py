from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot_app.config import get_settings
from bot_app.handlers import register_handlers
from bot_app.utils.json_storage import JSONFileStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    storage = JSONFileStorage(settings.state_file_path)
    dispatcher = Dispatcher(storage=storage)

    register_handlers(dispatcher)

    pages_url = settings.pages_url
    await bot.set_my_description(
        "Команда REINASLEO рада приветствовать тебя ❤️\n\n"
        "Спасибо за покупку — надеемся, что наши образы вдохновят тебя! 🫶🏻\n"
        "Смотри подарок с онлайн‑тренировкой прямо в боте и подписывайся на нас в соцсетях.\n\n"
        "Нажимая «Старт», вы соглашаетесь:\n"
        f"- Политика конфиденциальности: {pages_url}/privacy.html\n"
        f"- Пользовательское соглашение: {pages_url}/terms.html\n"
        f"- Рекламная оферта: {pages_url}/advertising.html"
    )

    logger.info("Starting bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
