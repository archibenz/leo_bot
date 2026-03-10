# CLAUDE.md — Telegram Bot Agent (Python/aiogram)

You are working on the **Telegram bot** for REINASLEO — a premium women's fashion e-commerce platform.

## Scope

Your domain is `leo_bot/` only. You MUST NOT edit files in `leo_web/`.

## Tech Stack

- **Python 3.9+**
- **aiogram 3.20+** — Telegram bot framework (async, FSM, filters)
- **aiohttp 3.9+** — async HTTP client (for API calls)
- **python-dotenv** — env vars
- **gspread** + **oauth2client** — Google Sheets integration (optional)

## Commands

```bash
# From leo_bot/:
source venv/bin/activate    # Activate virtualenv
python main.py              # Start bot (polling mode)

# Install deps:
pip install -r requirements.txt
```

## Architecture

### Directory Structure
```
leo_bot/
├── main.py                    # Entry point
├── reinasleo_bot.py           # Alternative entry
├── requirements.txt           # Dependencies
├── bot_app/
│   ├── app.py                 # Bot & Dispatcher initialization
│   ├── config.py              # Settings (env vars)
│   ├── states.py              # FSM states
│   ├── keyboards.py           # Inline & reply keyboards
│   ├── handlers/
│   │   ├── __init__.py        # register_handlers()
│   │   ├── registration.py    # /start, deep link auth, phone collection
│   │   ├── menu.py            # Main menu navigation
│   │   └── support.py         # Support & feedback
│   ├── services/
│   │   ├── api_client.py      # HTTP calls to Spring Boot API
│   │   └── google_sheets.py   # Google Sheets (optional)
│   └── utils/
│       └── validators.py      # Input validation
```

### FSM States (`states.py`)
```python
RegistrationStates:
  - waiting_phone       # After deep link, waiting for phone number

SupportStates:
  - waiting_for_feedback
  - in_chat
```

### Auth Flow (core feature)
The bot participates in Telegram authentication between the website and API:

1. **User clicks "Login via Telegram" on website** → site calls `POST /api/auth/telegram/init` → gets deep link `t.me/BOT?start=auth_TOKEN`
2. **User opens deep link in Telegram** → bot receives `/start auth_TOKEN`
3. **Bot handler** (`handlers/registration.py`):
   - Calls `bot_login(telegram_id, auth_token)` — if user exists → get login token → send site URL
   - If `UserNotFound` → ask for phone number (FSM → `waiting_phone`)
   - If `AuthTokenExpired` → error message
4. **Phone received** → calls `bot_register(telegram_id, phone, name, surname, auth_token)` → get login token → send site URL with token
5. **User clicks link** → site exchanges login token for JWT

### API Client (`services/api_client.py`)
All calls go to Spring Boot backend with `X-Bot-Secret` header:

```python
bot_login(telegram_id, auth_token) -> loginToken
# POST /api/bot/login
# Raises: UserNotFound, AuthTokenExpired

bot_register(telegram_id, phone, first_name, surname, auth_token) -> loginToken
# POST /api/bot/register
```

### Keyboards (`keyboards.py`)
- Reply keyboards for main menu
- Inline keyboards for auth flow (share phone, cancel)
- Language selection keyboards

## Key Files

| Purpose | File |
|---------|------|
| Entry point | `main.py` |
| Bot setup | `bot_app/app.py` |
| Config | `bot_app/config.py` |
| FSM states | `bot_app/states.py` |
| Keyboards | `bot_app/keyboards.py` |
| Auth handler | `bot_app/handlers/registration.py` |
| Menu handler | `bot_app/handlers/menu.py` |
| Support handler | `bot_app/handlers/support.py` |
| API client | `bot_app/services/api_client.py` |
| Google Sheets | `bot_app/services/google_sheets.py` |

## API Contract (consumed, not owned)

Backend API base URL: env `API_BASE_URL` (default: `http://localhost:8080`)

### Bot endpoints (X-Bot-Secret auth)
- `POST /api/bot/login` — body: `{ telegramId, authToken }` → `{ loginToken }`
- `POST /api/bot/register` — body: `{ telegramId, phone, firstName, surname, authToken }` → `{ loginToken }`
- `POST /api/bot/check-user` — body: `{ telegramId }` → `{ registered, name }`
- `POST /api/bot/organic-register` — body: `{ telegramId, phone, firstName, surname }` → `200 OK`

### Error responses from API
- `404` — UserNotFound (user not registered yet)
- `400` — AuthTokenExpired or invalid token
- `403` — invalid bot secret

## Environment Variables

```
BOT_TOKEN=<telegram bot token from @BotFather>
API_BASE_URL=http://localhost:8080
BOT_API_SECRET=<shared secret with API, must match API's BOT_API_SECRET>
SITE_URL=http://localhost:3000
SHEET_ID=<google sheet id, optional>
CREDENTIALS_FILE=<path to google oauth json, optional>
```

## Completed: Organic + Deep Link Registration Flow

All implemented: FSM states (`waiting_consent`, `waiting_phone_organic`); API client (`check_user()`, `bot_organic_register()`); keyboards (`welcome_consent_keyboard()`, `register_prompt_keyboard()`); full registration.py rewrite with consent flow; soft reminders in menu.py (~20%).

---

## Rules

1. All HTTP calls to API go through `services/api_client.py` — never call API directly from handlers
2. Use aiogram FSM for multi-step flows — define states in `states.py`
3. Register new handlers in `handlers/__init__.py` → `register_handlers()`
4. Bot messages should support Russian (primary audience)
5. Always handle API errors gracefully — show user-friendly messages, don't expose technical details
6. Use `config.py` Settings class for all configuration — never read env vars directly in handlers
