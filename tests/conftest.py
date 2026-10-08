from __future__ import annotations

import builtins
import io
import os
import socket
from pathlib import Path
from unittest.mock import patch

import dotenv
import pytest


def _no_dotenv(*args: object, **kwargs: object) -> bool:
    return False


dotenv.load_dotenv = _no_dotenv

SYNTHETIC_ENV = {
    "BOT_TOKEN": "123456:synthetic_bot_token_only_123456789",
    "ADMIN_IDS": "111",
    "BOT_API_SECRET": "synthetic_bot_api_secret_only",
    "API_BASE_URL": "http://localhost:8080",
    "BOT_USERNAME": "synthetic_test_bot",
    "SITE_URL": "https://synthetic.example",
    "PAGES_URL": "https://synthetic.example/pages",
}


def no_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("Real network access is disabled in bot tests")


original_open = builtins.open


def no_env_file(file: object, *args: object, **kwargs: object):
    if isinstance(file, (str, os.PathLike)):
        name = Path(file).name
        if name == ".env" or name.startswith(".env."):
            raise AssertionError("Environment files are disabled in bot tests")
    return original_open(file, *args, **kwargs)


socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network
builtins.open = no_env_file
io.open = no_env_file
os.environ.clear()
os.environ.update(SYNTHETIC_ENV)


@pytest.fixture(autouse=True)
def synthetic_settings_and_no_network(monkeypatch: pytest.MonkeyPatch):
    from bot_app.config import get_settings

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(builtins, "open", no_env_file)
    monkeypatch.setattr(io, "open", no_env_file)
    monkeypatch.setattr("bot_app.config.load_dotenv", _no_dotenv)
    get_settings.cache_clear()
    with patch.dict(os.environ, SYNTHETIC_ENV, clear=True):
        yield
    get_settings.cache_clear()
