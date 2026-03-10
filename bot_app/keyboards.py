from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Оставить номер", request_contact=True)]],
        resize_keyboard=True,
    )


def consent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером и принять условия", request_contact=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        "Магазин на WB 💜",
        "Наш VK 🧡",
        "Наш Telegram 📢",
        "Наш Instagram ✅",
        "Подарок 🎁",
        "Техподдержка 🛠",
    ]

    keyboard = []
    row: list[KeyboardButton] = []
    for index, label in enumerate(buttons):
        row.append(KeyboardButton(text=label))
        if len(row) == 2 or index == len(buttons) - 1:
            keyboard.append(row[:])
            row.clear()

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def admin_support_keyboard(username: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Выйти из чата с @{username}"), KeyboardButton(text="Выйти в меню")],
        ],
        resize_keyboard=True,
    )


def user_support_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Выйти из чата поддержки"), KeyboardButton(text="Выйти в меню")],
        ],
        resize_keyboard=True,
    )


def welcome_consent_keyboard(pages_url: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Политика конфиденциальности", url=f"{pages_url}/privacy.html")],
        [InlineKeyboardButton(text="Пользовательское соглашение", url=f"{pages_url}/terms.html")],
        [InlineKeyboardButton(text="Согласиться", callback_data="consent_accept")],
        [InlineKeyboardButton(text="Отказаться", callback_data="consent_decline")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def register_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Зарегистрироваться", callback_data="start_registration")],
    ])
