from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot_app.config import get_settings
from bot_app.handlers import register_handlers
from bot_app.handlers.support import expire_stale_threads, init_state_store, persist_state
from bot_app.utils.json_storage import JSONFileStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SUPPORT_STATE_FLUSH_INTERVAL = 5.0


async def _periodic_support_state_flush() -> None:
    while True:
        try:
            await asyncio.sleep(_SUPPORT_STATE_FLUSH_INTERVAL)
            await persist_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic support state flush failed")


async def run() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    storage = JSONFileStorage(settings.state_file_path)
    dispatcher = Dispatcher(storage=storage)

    register_handlers(dispatcher)
    init_state_store(settings.support_state_path)

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

    try:
        expired = await expire_stale_threads(bot)
        if expired:
            logger.info("Expired %d stale support thread(s) on startup", expired)
    except Exception:
        logger.exception("Startup support state cleanup failed")

    flush_task = asyncio.create_task(_periodic_support_state_flush())
    try:
        await dispatcher.start_polling(bot)
    finally:
        flush_task.cancel()
        try:
            await flush_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Periodic flush task raised while shutting down")
        try:
            await persist_state()
        except Exception:
            logger.exception("Final support state flush failed")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
