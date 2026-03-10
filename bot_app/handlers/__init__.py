from aiogram import Dispatcher

from bot_app.handlers import menu, registration, support


def register_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(registration.router)
    dispatcher.include_router(menu.router)
    dispatcher.include_router(support.router)
