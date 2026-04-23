from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot_app.config import get_settings
from bot_app.keyboards import (
    consent_keyboard,
    main_menu_keyboard,
    welcome_consent_keyboard,
)
from bot_app.services.api_client import (
    AuthTokenExpired,
    UserNotFound,
    bot_login,
    bot_organic_register,
    bot_register,
    check_user,
    log_visit,
)
from bot_app.states import RegistrationStates
from bot_app.utils.validators import is_valid_phone

MAX_NAME_LENGTH = 64

router = Router()

logger = logging.getLogger(__name__)


def _sanitize_name(raw: str | None, fallback: str = "User") -> str:
    if not raw:
        return fallback
    cleaned = raw.strip()[:MAX_NAME_LENGTH]
    return cleaned or fallback

def _user_menu(user_id: int):
    settings = get_settings()
    return main_menu_keyboard(is_admin=user_id in settings.admin_ids)


def _is_local_url(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url


async def _send_site_link(message: Message, text_button: str, text_plain: str, url: str, button_text: str = "Перейти на сайт REINASLEO") -> None:
    """Send a site link — inline button for HTTPS, plain text with URL for localhost."""
    if _is_local_url(url):
        await message.answer(f"{text_plain}\n\n{url}")
    else:
        await message.answer(
            text_button,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=button_text, url=url)]
            ]),
        )


# ── /start command ──────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    payload = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    source = "deep_link" if payload.startswith("auth_") else "organic"

    await log_visit(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code,
        source=source,
    )

    if payload.startswith("auth_"):
        await _handle_auth_deeplink(message, state, payload[5:])
    else:
        await _handle_organic(message, state)


# ── Organic flow ────────────────────────────────────────────────────

async def _handle_organic(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    telegram_id = message.from_user.id
    name = message.from_user.first_name or ""

    try:
        user_info = await check_user(telegram_id)
    except Exception:
        logger.exception("check_user failed for telegram_id=%s", telegram_id)
        user_info = {"registered": False}

    if user_info.get("registered"):
        db_name = user_info.get("name") or name
        await message.answer(
            f"С возвращением, {db_name}!\n\n"
            "Мы рады снова видеть вас в REINASLEO.\n"
            "Выбирайте интересующий раздел — впереди много нового.",
            reply_markup=_user_menu(message.from_user.id),
        )
    else:
        await state.set_state(RegistrationStates.waiting_consent)
        await message.answer(
            f"Добро пожаловать в REINASLEO, {name}!\n\n"
            "Мы создаём редакционную женскую одежду с точной посадкой "
            "и кутюрной отделкой.\n\n"
            "Для регистрации нам потребуется ваш номер телефона. "
            "Перед этим, пожалуйста, ознакомьтесь с нашими условиями:",
            reply_markup=welcome_consent_keyboard(settings.pages_url),
        )
        await message.answer(
            "А пока вы можете пользоваться меню:",
            reply_markup=_user_menu(message.from_user.id),
        )


# ── Deep link flow ──────────────────────────────────────────────────

async def _handle_auth_deeplink(message: Message, state: FSMContext, auth_token: str) -> None:
    settings = get_settings()
    telegram_id = message.from_user.id
    name = message.from_user.first_name or ""

    try:
        login_token = await bot_login(telegram_id, auth_token)
        site_url = f"{settings.site_url}/ru/auth/tg?token={login_token}"
        if _is_local_url(site_url):
            await message.answer(
                f"Рады видеть вас снова, {name}!\n\n"
                "Вход выполнен успешно. Перейдите по ссылке, "
                f"чтобы продолжить на сайте:\n\n{site_url}",
            )
        else:
            await message.answer(
                f"Рады видеть вас снова, {name}!\n\n"
                "Вход выполнен успешно. Нажмите на кнопку, "
                "чтобы продолжить на сайте:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Перейти на сайт REINASLEO", url=site_url)]
                ]),
            )
    except UserNotFound:
        await state.set_state(RegistrationStates.waiting_consent)
        await state.update_data(auth_token=auth_token)
        await message.answer(
            f"Добро пожаловать в REINASLEO, {name}!\n\n"
            "Для завершения входа на сайт необходима быстрая регистрация. "
            "Нам потребуется ваш номер телефона.\n\n"
            "Пожалуйста, ознакомьтесь с условиями:",
            reply_markup=welcome_consent_keyboard(settings.pages_url),
        )
    except AuthTokenExpired:
        await message.answer(
            "К сожалению, ссылка для входа устарела.\n"
            "Вернитесь на сайт и запросите новую.",
        )
    except Exception:
        logger.exception("Error during auth deeplink handling for telegram_id=%s", telegram_id)
        await message.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже "
            "или обратитесь в поддержку.",
        )


# ── Consent callbacks ──────────────────────────────────────────────

@router.callback_query(F.data == "consent_accept")
async def on_consent_accept(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    auth_token = data.get("auth_token")

    if auth_token:
        await state.set_state(RegistrationStates.waiting_phone)
    else:
        await state.set_state(RegistrationStates.waiting_phone_organic)

    await callback.message.answer(
        "Спасибо за доверие!\n\n"
        "Теперь, пожалуйста, поделитесь номером телефона — "
        "нажмите кнопку ниже, и номер будет отправлен автоматически:",
        reply_markup=consent_keyboard(),
    )


@router.callback_query(F.data == "consent_decline")
async def on_consent_decline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "Ничего страшного! Вы всегда можете вернуться к регистрации позже.\n"
        "А пока — пользуйтесь меню:",
        reply_markup=_user_menu(callback.from_user.id),
    )


@router.callback_query(F.data == "start_registration")
async def on_start_registration(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    settings = get_settings()
    await state.set_state(RegistrationStates.waiting_consent)
    await callback.message.answer(
        "Для регистрации нам потребуется ваш номер телефона.\n"
        "Пожалуйста, ознакомьтесь с условиями:",
        reply_markup=welcome_consent_keyboard(settings.pages_url),
    )


# ── Phone handler: deep link flow ──────────────────────────────────

@router.message(RegistrationStates.waiting_phone, F.contact)
async def handle_phone_deeplink(message: Message, state: FSMContext):
    settings = get_settings()
    telegram_id = message.from_user.id
    phone = message.contact.phone_number
    first_name = _sanitize_name(message.from_user.first_name)
    last_name = _sanitize_name(message.from_user.last_name, fallback="")

    if not is_valid_phone(phone):
        await message.answer(
            "Не удалось распознать номер телефона. "
            "Пожалуйста, используйте кнопку «Поделиться контактом» ещё раз.",
        )
        return

    data = await state.get_data()
    auth_token = data.get("auth_token")

    if not auth_token:
        await state.clear()
        await message.answer(
            "Сессия регистрации истекла. Вернитесь на сайт и попробуйте снова.",
            reply_markup=_user_menu(message.from_user.id),
        )
        return

    try:
        login_token = await bot_register(
            telegram_id=telegram_id,
            phone=phone,
            first_name=first_name,
            auth_token=auth_token,
            surname=last_name,
        )
        site_url = f"{settings.site_url}/ru/auth/tg?token={login_token}"
        await state.clear()
        await message.answer(
            "Регистрация завершена!\n\n"
            "Спасибо, что выбрали REINASLEO. "
            "Мы подготовили для вас особенный опыт на нашем сайте.",
            reply_markup=_user_menu(message.from_user.id),
        )
        await _send_site_link(
            message,
            "Нажмите, чтобы продолжить на сайте:",
            "Перейдите по ссылке, чтобы продолжить на сайте:",
            site_url,
        )
    except AuthTokenExpired:
        await state.clear()
        await message.answer(
            "К сожалению, ссылка для входа устарела.\n"
            "Вернитесь на сайт и запросите новую.",
            reply_markup=_user_menu(message.from_user.id),
        )
    except Exception:
        logger.exception("Error during phone registration for telegram_id=%s", telegram_id)
        await state.clear()
        await message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.",
            reply_markup=_user_menu(message.from_user.id),
        )


# ── Phone handler: organic flow ────────────────────────────────────

@router.message(RegistrationStates.waiting_phone_organic, F.contact)
async def handle_phone_organic(message: Message, state: FSMContext):
    settings = get_settings()
    telegram_id = message.from_user.id
    phone = message.contact.phone_number
    first_name = _sanitize_name(message.from_user.first_name)
    last_name = _sanitize_name(message.from_user.last_name, fallback="")

    if not is_valid_phone(phone):
        await message.answer(
            "Не удалось распознать номер телефона. "
            "Пожалуйста, используйте кнопку «Поделиться контактом» ещё раз.",
        )
        return

    try:
        await bot_organic_register(
            telegram_id=telegram_id,
            phone=phone,
            first_name=first_name,
            surname=last_name,
        )
        await state.clear()
        await message.answer(
            f"Добро пожаловать в REINASLEO, {first_name}!\n\n"
            "Спасибо за регистрацию. Мы ценим ваше доверие "
            "и рады приветствовать вас в нашем сообществе.",
            reply_markup=_user_menu(message.from_user.id),
        )
    except Exception:
        logger.exception("Error during organic registration for telegram_id=%s", telegram_id)
        await state.clear()
        await message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.",
            reply_markup=_user_menu(message.from_user.id),
        )


# ── Cancel handler (both phone states) ─────────────────────────────

@router.message(RegistrationStates.waiting_phone, F.text == "Отмена")
@router.message(RegistrationStates.waiting_phone_organic, F.text == "Отмена")
async def handle_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Регистрация отменена. Вы всегда можете вернуться к ней позже.",
        reply_markup=_user_menu(message.from_user.id),
    )
