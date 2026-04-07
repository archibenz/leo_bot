import logging
import random

from aiogram import F, Router
from aiogram.types import Message

from bot_app.config import get_settings
from bot_app.keyboards import register_prompt_keyboard
from bot_app.services.api_client import check_user

router = Router()

logger = logging.getLogger(__name__)

GIFT_VIDEO_FALLBACK_URL = ""


async def _maybe_remind_registration(message: Message) -> None:
    if random.random() > 0.2:
        return
    try:
        user_info = await check_user(message.from_user.id)
        if not user_info.get("registered"):
            await message.answer(
                "💡 Кстати, вы ещё не зарегистрированы. "
                "Регистрация займёт меньше минуты!",
                reply_markup=register_prompt_keyboard(),
            )
    except Exception:
        logger.debug("remind check_user failed", exc_info=True)


@router.message(F.text == "Магазин на WB 💜")
async def send_wb_link(message: Message):
    wb_seller_id = get_settings().wb_seller_id
    await message.answer(
        "Обнови свой гардероб в нашем магазине! 💜\n\n"
        "Ознакомиться с нашими товарами на Wildberries вы можете по ссылке:\n"
        f"https://www.wildberries.ru/seller/{wb_seller_id}"
    )
    await _maybe_remind_registration(message)


@router.message(F.text == "Подарок 🎁")
async def send_gift_link(message: Message):
    await message.answer(
        "Ваш подарок 🎁 скоро будет доступен!\n\n"
        "Следите за обновлениями в нашем Telegram-канале: https://t.me/reinasleo_store"
    )
    await _maybe_remind_registration(message)


@router.message(F.text == "Наш Instagram ✅")
async def send_instagram_link(message: Message):
    await message.answer(
        "Подписывайся на нашу страничку в Instagram, чтобы всегда быть в курсе новинок! 👉🏻\n"
        "https://www.instagram.com/reinasleo"
    )
    await _maybe_remind_registration(message)


@router.message(F.text == "Наш Telegram 📢")
async def send_telegram_channel(message: Message):
    await message.answer(
        "Присоединяйся к нашему Telegram‑каналу REINASLEO 👉🏻\n"
        "https://t.me/reinasleo_store"
    )
    await _maybe_remind_registration(message)


@router.message(F.text == "Наш VK 🧡")
async def send_vk_link(message: Message):
    await message.answer(
        "Мы теперь и во ВКонтакте! Подписывайся, чтобы не пропустить новинки и акции 👉🏻\n"
        "https://vk.com/reinasleo"
    )
    await _maybe_remind_registration(message)
