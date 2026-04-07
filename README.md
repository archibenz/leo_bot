# Telegram бот ReinasLeo

Telegram‑бот для брэнда REINASLEO на aiogram 3. Обрабатывает регистрацию пользователей, авторизацию через deep links, и логирует визиты в основную PostgreSQL базу через REST API.

## Быстрый старт

1. Выполните `./setup.sh` — создаст виртуальное окружение и установит зависимости.
2. Заполните файл `.env` — см. раздел "Переменные окружения" ниже.
3. Запустите бота:
   ```bash
   source venv/bin/activate && python main.py
   ```

## Структура проекта

- `main.py` — точка входа для запуска бота.
- `bot_app/` — приложение бота.
  - `config.py` — загрузка настроек и переменных окружения.
  - `app.py` — создание `Bot`, `Dispatcher` и запуск поллинга.
  - `states.py` — FSM‑состояния (регистрация, поддержка).
  - `keyboards.py` — генерация клавиатур.
  - `handlers/` — обработчики команд и кнопок.
    - `registration.py` — регистрация пользователей, deep link auth, логирование визитов.
    - `menu.py` — ответы на кнопки основного меню.
    - `support.py` — приём обращений в поддержку и ответы админов.
  - `services/api_client.py` — HTTP‑клиент для Spring Boot API (вся бизнес‑логика и хранение в API).
  - `utils/validators.py` — вспомогательные проверки (например, телефон).
- `requirements.txt` — список зависимостей.
- `setup.sh` — автоматическая настройка окружения.

## Архитектура

Бот — тонкий клиент над Spring Boot API. Все данные (пользователи, регистрации, визиты бота) хранятся в PostgreSQL и доступны через `/api/bot/*` endpoints, защищённые `X-Bot-Secret` заголовком.

## Переменные окружения

Обязательные:
- `BOT_TOKEN` — токен Telegram‑бота от @BotFather.
- `API_BASE_URL` — URL Spring Boot API (обычно `http://localhost:8080` на сервере).
- `BOT_API_SECRET` — общий секрет с API, должен совпадать с `BOT_API_SECRET` на бэкенде.
- `ADMIN_IDS` — список Telegram user ID администраторов через запятую.

Опциональные:
- `BOT_USERNAME` — username бота (по умолчанию `reinasleo_bot`).
- `SITE_URL` — URL сайта (по умолчанию `https://reinasleo.com`).
- `PAGES_URL` — URL pages (по умолчанию `https://reinasleo.com/pages`).
- `GIFT_VIDEO_URL` — URL приветственного видео.
- `WB_SELLER_ID` — ID продавца на Wildberries (по умолчанию `609562`).

## Тесты

Для запуска тестов установите dev-зависимости:

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
