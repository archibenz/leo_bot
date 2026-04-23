import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot_app.config import get_settings
from bot_app.keyboards import admin_support_keyboard, main_menu_keyboard, user_support_keyboard
from bot_app.states import SupportStates
from bot_app.utils.support_state import load_state, save_state

logger = logging.getLogger(__name__)

router = Router()

USER_ID_PATTERN = re.compile(r"ID:\s*(\d+)")
USERNAME_PATTERN = re.compile(r"Username:\s*@?([^\s]+)")

_CHAT_IDLE_TIMEOUT = timedelta(minutes=5)


def _end_chat_label(username: str) -> str:
    return f"Выйти из чата с @{username}"


def _user_end_chat_label() -> str:
    return "Выйти из чата поддержки"

# In-memory mapping of admin chat sessions to the user they are assisting
active_admin_chats: dict[int, dict[str, str | int]] = {}

# Per-user support threads to keep context between messages
support_threads: dict[int, dict[str, object]] = {}

# Track scheduled cleanup tasks per user
_cleanup_tasks: dict[int, asyncio.Task] = {}

# Per-user locks guard read-modify-write sequences spanning await points
_per_user_locks: dict[int, asyncio.Lock] = {}

# Persistence across bot restarts (A32b, 2026-04-23)
_STALE_THREAD_THRESHOLD = timedelta(minutes=30)
_state_path: Optional[Path] = None
_save_lock = asyncio.Lock()


def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _per_user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _per_user_locks[user_id] = lock
    return lock


def _admin_ids() -> tuple[int, ...]:
    settings = get_settings()
    return settings.admin_ids


def init_state_store(path: "str | os.PathLike[str]") -> None:
    """Load persisted support state from disk. Call once before polling."""
    global _state_path
    _state_path = Path(path)
    load_state(_state_path, threads=support_threads, admin_chats=active_admin_chats)


async def persist_state() -> None:
    """Atomic flush of support_threads + active_admin_chats to disk."""
    if _state_path is None:
        return
    try:
        await save_state(
            _state_path,
            threads=support_threads,
            admin_chats=active_admin_chats,
            save_lock=_save_lock,
        )
    except Exception:
        logger.exception("Failed to persist support state")


async def expire_stale_threads(bot, threshold: timedelta = _STALE_THREAD_THRESHOLD) -> int:
    """Close threads whose last user message is older than threshold.

    Called on startup after init_state_store. Best-effort apology message
    gets sent so the user knows to re-ping support.
    """
    now = datetime.now(timezone.utc)
    expired: list[int] = []
    for user_id, thread in list(support_threads.items()):
        last_msg = thread.get("last_user_message")
        if isinstance(last_msg, datetime) and (now - last_msg) > threshold:
            expired.append(user_id)

    for user_id in expired:
        support_threads.pop(user_id, None)
        _cancel_cleanup(user_id)
        try:
            await bot.send_message(
                user_id,
                "Мы перезапускали бота. Пожалуйста, напиши вопрос ещё раз — "
                "и мы продолжим поддержку.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            logger.exception("Failed to notify user %s about expired support thread", user_id)

    expired_set = set(expired)
    stale_admin_ids = [
        admin_id
        for admin_id, session in active_admin_chats.items()
        if session.get("user_id") in expired_set
    ]
    for admin_id in stale_admin_ids:
        active_admin_chats.pop(admin_id, None)

    if expired:
        await persist_state()
    return len(expired)


@router.message(F.text == "Техподдержка 🛠")
async def tech_support(message: Message, state: FSMContext):
    await state.set_state(SupportStates.waiting_for_feedback)
    await message.answer(
        "Опиши, пожалуйста, вопрос или проблему максимально подробно: номер заказа,"
        " артикул товара, фото/видео и контакт для связи. Мы быстро передадим запрос"
        " в поддержку и вернемся с ответом в этом чате."
    )


@router.message(SupportStates.waiting_for_feedback)
async def process_support_feedback(message: Message, state: FSMContext):
    await _handle_user_support_message(message, state)


@router.message(
    F.from_user.id.func(lambda user_id: user_id in support_threads)
    & ~F.text.in_({_user_end_chat_label(), "Выйти в меню"})
)
async def process_additional_support(message: Message):
    await _handle_user_support_message(message, None)


@router.message(SupportStates.in_chat, F.text.in_({_user_end_chat_label(), "Выйти в меню"}))
async def handle_user_exit(message: Message, state: FSMContext):
    user_id = message.from_user.id

    async with _get_user_lock(user_id):
        thread = support_threads.pop(user_id, None)
        _cancel_cleanup(user_id)

    username = str(thread.get("username", "пользователь")) if thread else "пользователь"

    if thread:
        await _notify_admins_user_left(user_id, username, message.bot)

    await state.clear()
    await message.answer(
        "Вы вышли из чата поддержки. Возвращаем вас в главное меню.",
        reply_markup=main_menu_keyboard(),
    )


def _support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить пользователю", callback_data=f"support_reply:{user_id}")]
        ]
    )


def _get_or_create_thread(user_id: int, username: str) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    thread = support_threads.get(user_id)
    if thread is None:
        thread = {
            "user_id": user_id,
            "username": username,
            "last_user_message": now,
            "last_admin_reply": None,
            "prompt_sent": False,
            "user_ack_sent": False,
        }
        # setdefault ensures atomicity if another coroutine just created it
        thread = support_threads.setdefault(user_id, thread)
    thread["username"] = username
    thread["last_user_message"] = now
    return thread


async def _handle_user_support_message(message: Message, state: Optional[FSMContext]):
    username = message.from_user.username or message.from_user.first_name or "Без ника"
    user_id = message.from_user.id
    feedback = message.text or "<нет текста>"

    async with _get_user_lock(user_id):
        thread = _get_or_create_thread(user_id, username)

        should_send_prompt = not thread.get("prompt_sent")
        should_send_ack = not thread.get("user_ack_sent")
        # Claim both flags before awaiting so a concurrent burst cannot duplicate work
        if should_send_prompt:
            thread["prompt_sent"] = True
        if should_send_ack:
            thread["user_ack_sent"] = True

        if should_send_prompt:
            admin_prompt = (
                "Новое сообщение в техподдержке.\n\n"
                f"ID: {user_id}\n"
                f"Username: @{username}\n"
                f"Текст: {feedback}\n\n"
                "Нажми «Ответить пользователю», чтобы войти в чат."
            )

            prompt_messages: dict[int, int] = {}
            any_sent = False
            for admin_id in _admin_ids():
                try:
                    if message.content_type == "text":
                        sent = await message.bot.send_message(
                            chat_id=admin_id,
                            text=admin_prompt,
                            reply_markup=_support_reply_keyboard(user_id),
                        )
                    else:
                        sent = await message.copy_to(
                            admin_id,
                            caption=admin_prompt,
                            reply_markup=_support_reply_keyboard(user_id),
                        )
                    prompt_messages[admin_id] = sent.message_id
                    any_sent = True
                except Exception:  # noqa: BLE001
                    logger.exception("Error sending support message to admin %s", admin_id)

            if any_sent:
                thread.setdefault("prompt_messages", {}).update(prompt_messages)
            else:
                # Rollback so a retry can ping admins again
                thread["prompt_sent"] = False
        else:
            await _forward_user_message_to_admins(message, thread)

        if should_send_ack:
            try:
                await message.answer(
                    "Мы получили ваш запрос. Команда на связи и ответит здесь в чате.",
                    reply_markup=user_support_keyboard(),
                )
            except Exception:
                thread["user_ack_sent"] = False
                raise

        if state:
            await state.set_state(SupportStates.in_chat)

        _schedule_cleanup(user_id)


def _parse_username(text: str) -> Optional[str]:
    username_match = USERNAME_PATTERN.search(text)
    if username_match:
        return username_match.group(1)
    return None


def _parse_user_from_message(message: Message) -> tuple[Optional[int], Optional[str]]:
    if not message.text:
        return None, None

    user_id = None
    username = _parse_username(message.text)

    match = USER_ID_PATTERN.search(message.text)
    if match:
        user_id = int(match.group(1))

    return user_id, username


async def _forward_user_message_to_admins(message: Message, thread: dict[str, object]):
    user_id = int(thread["user_id"])
    username = str(thread.get("username", "пользователь"))

    active_targets = [
        admin_id for admin_id, session in active_admin_chats.items() if session.get("user_id") == user_id
    ]
    target_admins = active_targets or list(_admin_ids())

    for admin_id in target_admins:
        try:
            if message.content_type == "text":
                await message.bot.send_message(admin_id, message.text)
            else:
                await message.copy_to(admin_id)
        except Exception:  # noqa: BLE001
            logger.exception("Error forwarding user message from %s to admin %s", username, admin_id)


async def _notify_admins_user_left(user_id: int, username: str, bot):
    notified_admins: set[int] = set()
    for admin_id, session in list(active_admin_chats.items()):
        if session.get("user_id") == user_id:
            # Pop before awaiting so a concurrent admin handler cannot reuse the stale session
            active_admin_chats.pop(admin_id, None)
            notified_admins.add(admin_id)
            try:
                await bot.send_message(
                    admin_id,
                    f"Пользователь @{username} вышел из чата поддержки. Диалог закрыт.",
                    reply_markup=main_menu_keyboard(),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Error notifying admin %s about user exit", admin_id)

    for admin_id in _admin_ids():
        if admin_id in notified_admins:
            continue
        try:
            await bot.send_message(
                admin_id,
                f"Пользователь @{username} вышел из чата поддержки. Диалог закрыт.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Error notifying admin %s about user exit", admin_id)


def _schedule_cleanup(user_id: int):
    prev = _cleanup_tasks.pop(user_id, None)
    if prev is not None and not prev.done():
        prev.cancel()
    _cleanup_tasks[user_id] = asyncio.create_task(_cleanup_thread_after(user_id))


def _cancel_cleanup(user_id: int):
    existing = _cleanup_tasks.pop(user_id, None)
    if existing and not existing.done():
        existing.cancel()


async def _cleanup_thread_after(user_id: int):
    try:
        await asyncio.sleep(_CHAT_IDLE_TIMEOUT.total_seconds())
    except asyncio.CancelledError:
        return

    async with _get_user_lock(user_id):
        thread = support_threads.get(user_id)
        if not thread:
            _cleanup_tasks.pop(user_id, None)
            _per_user_locks.pop(user_id, None)
            return

        if not thread.get("last_admin_reply"):
            _cleanup_tasks.pop(user_id, None)
            return

        if any(session.get("user_id") == user_id for session in active_admin_chats.values()):
            _cleanup_tasks.pop(user_id, None)
            _schedule_cleanup(user_id)
            return

        epoch = datetime.min.replace(tzinfo=timezone.utc)
        last_activity = max(
            thread.get("last_user_message") or epoch,
            thread.get("last_admin_reply") or epoch,
        )
        if datetime.now(timezone.utc) - last_activity >= _CHAT_IDLE_TIMEOUT:
            support_threads.pop(user_id, None)
            _per_user_locks.pop(user_id, None)

        _cleanup_tasks.pop(user_id, None)


def _close_thread(user_id: int):
    support_threads.pop(user_id, None)
    _cancel_cleanup(user_id)
    _per_user_locks.pop(user_id, None)


@router.callback_query(F.data.startswith("support_reply:"))
async def handle_support_reply(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if admin_id not in _admin_ids():
        await callback.answer()
        return

    try:
        user_id = int(callback.data.split(":", maxsplit=1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    async with _get_user_lock(user_id):
        thread = support_threads.get(user_id)
        if not thread:
            await callback.answer("Чат уже закрыт")
            return

        username = str(thread.get("username", "пользователем"))
        # Claim the admin slot before awaiting so a parallel callback cannot hijack it
        active_admin_chats[admin_id] = {"user_id": user_id, "username": username}

    try:
        await callback.message.answer(
            f"Вы в чате с @{username}. Можете писать сообщения пользователю.",
            reply_markup=admin_support_keyboard(username),
        )
    except Exception:
        active_admin_chats.pop(admin_id, None)
        raise
    await callback.answer()


@router.message(F.from_user.id.in_(_admin_ids()))
async def handle_admin_support_chat(message: Message):
    admin_id = message.from_user.id
    session = active_admin_chats.get(admin_id)

    if session and message.text:
        if message.text == _end_chat_label(str(session.get("username", ""))):
            active_admin_chats.pop(admin_id, None)
            await message.answer(
                "Вы вышли из диалога поддержки. Нажмите «Ответить пользователю», чтобы вернуться.",
                reply_markup=main_menu_keyboard(),
            )
            return

        if message.text == "Выйти в меню":
            active_admin_chats.pop(admin_id, None)
            await message.answer("Возвращаемся в меню.", reply_markup=main_menu_keyboard())
            return

    if not session and message.reply_to_message:
        user_id_from_reply, username_from_reply = _parse_user_from_message(message.reply_to_message)
        if user_id_from_reply:
            # setdefault avoids clobbering if another handler already claimed the slot
            session = active_admin_chats.setdefault(
                admin_id,
                {"user_id": user_id_from_reply, "username": username_from_reply or "пользователь"},
            )

    if not session:
        return

    user_id = int(session.get("user_id", 0))
    username = session.get("username", "пользователю") or "пользователю"

    async with _get_user_lock(user_id):
        thread = support_threads.get(user_id)
        if not thread:
            active_admin_chats.pop(admin_id, None)
            await message.answer(
                "Чат закрыт. Откройте новый диалог через кнопку «Ответить пользователю».",
                reply_markup=main_menu_keyboard(),
            )
            return

        thread["last_admin_reply"] = datetime.now(timezone.utc)
        _schedule_cleanup(user_id)

    try:
        if message.content_type == "text":
            await message.bot.send_message(user_id, message.text)
        else:
            await message.copy_to(user_id)
    except Exception:  # noqa: BLE001
        await message.answer(
            "Не удалось отправить сообщение пользователю. Попробуйте ещё раз позднее.",
            reply_markup=admin_support_keyboard(str(username)),
        )
        return

    return
