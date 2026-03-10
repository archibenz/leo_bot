# Telegram бот ReinasLeo

Упрощённая структура проекта для запуска и поддержки Telegram‑бота на aiogram 3.

## Быстрый старт
1. Выполните `./setup.sh` для создания виртуального окружения и установки зависимостей.
2. Заполните файл `.env` значениями `BOT_TOKEN`, `SHEET_ID`, при необходимости `ADMIN_IDS` и `GOOGLE_APPLICATION_CREDENTIALS`.
3. Поместите JSON‑файл сервисного аккаунта Google по пути, указанному в `GOOGLE_APPLICATION_CREDENTIALS` (по умолчанию `credentials.json`).
4. Запустите бота: `source venv/bin/activate && python main.py`.

## Структура проекта
- `main.py` / `reinasleo_bot.py` — точки входа для запуска бота.
- `bot_app/` — приложение бота.
  - `config.py` — загрузка настроек и переменных окружения.
  - `app.py` — создание `Bot`, `Dispatcher` и запуск поллинга.
  - `handlers/` — обработчики команд и кнопок.
    - `registration.py` — регистрация пользователя и запись в Google Sheets.
    - `menu.py` — ответы на кнопки основного меню.
    - `support.py` — приём обращений в поддержку и ответы админов.
  - `services/google_sheets.py` — работа с Google Sheets через сервисный аккаунт.
  - `keyboards.py` — генерация клавиатур.
  - `states.py` — FSM‑состояния.
  - `utils/validators.py` — вспомогательные проверки (например, номера телефона).
- `requirements.txt` — список зависимостей.
- `setup.sh` — автоматическая настройка окружения.

## Переменные окружения
- `BOT_TOKEN` — токен Telegram‑бота (обязательно).
- `SHEET_ID` — идентификатор таблицы Google Sheets (обязательно).
- `ADMIN_IDS` — необязательный список ID администраторов через запятую для ответов из поддержки.
- `GOOGLE_APPLICATION_CREDENTIALS` — путь к JSON‑файлу сервисного аккаунта Google (по умолчанию `credentials.json`).
