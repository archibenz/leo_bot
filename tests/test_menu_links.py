"""Каждая кнопка меню должна вести куда-то, и вести туда, куда обещает.

Ссылки в боте живут в тексте ответов, поэтому единственный способ поймать
опечатку в домене или потерянную метку — прочитать их из самого исходника.
Отдельно проверяется префикс продавца в озоновской ссылке: без него переход
случится, но в отчёте Ozon он не появится, и понять, что бот приводит людей,
будет нечем.
"""

from __future__ import annotations

import re
from pathlib import Path

MENU = Path(__file__).resolve().parent.parent / "bot_app" / "handlers" / "menu.py"
KEYBOARDS = Path(__file__).resolve().parent.parent / "bot_app" / "keyboards.py"

SOURCE = MENU.read_text(encoding="utf-8")
KB_SOURCE = KEYBOARDS.read_text(encoding="utf-8")


def _buttons() -> list[str]:
    block = re.search(r"def main_menu_keyboard.*?\]", SOURCE + KB_SOURCE, re.S)
    assert block, "не нашёл список кнопок главного меню"
    return re.findall(r'"([^"]+)"', block.group(0))


def test_every_menu_button_has_a_handler() -> None:
    handled = set(re.findall(r'F\.text == "([^"]+)"', SOURCE))
    # админская кнопка живёт в другом модуле, поддержка тоже
    skip = {"🔐 Админ-панель", "Техподдержка 🛠"}
    missing = [b for b in _buttons() if b not in handled and b not in skip]
    assert missing == [], f"кнопки без обработчика: {missing}"


def test_ozon_button_exists() -> None:
    assert "Магазин на Ozon 🔵" in _buttons()
    assert 'F.text == "Магазин на Ozon 🔵"' in SOURCE


def test_ozon_link_carries_the_seller_prefix() -> None:
    # Читаем значение по умолчанию из самого конфига, а не через Settings:
    # конструктор требует полдюжины переменных окружения, и тест про ссылку не
    # должен падать из-за отсутствующего токена бота.
    config = (Path(__file__).resolve().parent.parent / "bot_app" / "config.py").read_text(encoding="utf-8")
    block = re.search(r'ozon_url = os\.getenv\((.*?)\)\n', config, re.S)
    assert block, "не нашёл значение OZON_URL по умолчанию"
    url = "".join(re.findall(r'"([^"]*)"', block.group(1))[1:])
    assert url.startswith("https://www.ozon.ru/"), url
    assert "utm_campaign=vendor_org_" in url, (
        "без префикса продавца Ozon не засчитает переход как наш"
    )


def test_links_are_https_and_not_placeholders() -> None:
    urls = re.findall(r"https?://[^\s\"'\\]+", SOURCE)
    assert urls, "в меню не нашлось ни одной ссылки"
    for u in urls:
        assert u.startswith("https://"), f"не https: {u}"
        assert "example.com" not in u and "localhost" not in u, f"заглушка: {u}"
