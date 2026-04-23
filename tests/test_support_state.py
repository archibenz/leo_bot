import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot_app.utils.support_state import _decode, _encode, load_state, save_state


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "support_state.json"


@pytest.fixture()
def save_lock() -> asyncio.Lock:
    return asyncio.Lock()


def test_encode_datetime_roundtrip() -> None:
    now = datetime(2026, 4, 23, 22, 30, 15, tzinfo=timezone.utc)
    encoded = _encode({"ts": now})
    assert encoded == {"ts": {"__dt__": now.isoformat()}}
    decoded = _decode(encoded)
    assert decoded == {"ts": now}


def test_encode_nested_structures() -> None:
    moment = datetime(2026, 4, 23, tzinfo=timezone.utc)
    payload: dict[str, Any] = {
        "threads": {
            42: {
                "last_user_message": moment,
                "prompt_messages": {100: 5, 200: 7},
            },
        },
    }
    roundtrip = _decode(_encode(payload))
    # int keys survive (decode doesn't re-cast; that's load_state's job)
    # but dict values preserve datetime
    inner = roundtrip["threads"]["42"]
    assert inner["last_user_message"] == moment


def test_decode_handles_invalid_dt() -> None:
    encoded = {"ts": {"__dt__": "not-a-datetime"}}
    assert _decode(encoded) == {"ts": None}


def test_decode_normalises_naive_datetime_to_utc() -> None:
    encoded = {"ts": {"__dt__": "2026-04-23T10:00:00"}}
    decoded = _decode(encoded)
    assert decoded["ts"] == datetime(2026, 4, 23, 10, 0, 0, tzinfo=timezone.utc)
    assert decoded["ts"].tzinfo is timezone.utc


async def test_save_and_load_roundtrip(state_file: Path, save_lock: asyncio.Lock) -> None:
    last_msg = datetime(2026, 4, 23, 10, 0, 0, tzinfo=timezone.utc)
    threads = {
        42: {
            "user_id": 42,
            "username": "alex",
            "last_user_message": last_msg,
            "last_admin_reply": None,
            "prompt_sent": True,
            "user_ack_sent": True,
            "prompt_messages": {100: 7, 200: 9},
        },
    }
    chats = {100: {"user_id": 42, "username": "alex"}}

    await save_state(state_file, threads=threads, admin_chats=chats, save_lock=save_lock)

    loaded_threads: dict[int, dict[str, Any]] = {}
    loaded_chats: dict[int, dict[str, Any]] = {}
    load_state(state_file, threads=loaded_threads, admin_chats=loaded_chats)

    assert set(loaded_threads.keys()) == {42}
    assert loaded_threads[42]["username"] == "alex"
    assert loaded_threads[42]["last_user_message"] == last_msg
    assert loaded_threads[42]["last_admin_reply"] is None
    assert loaded_chats == {100: {"user_id": 42, "username": "alex"}}


async def test_load_missing_file_is_noop(state_file: Path) -> None:
    threads: dict[int, dict[str, Any]] = {999: {"stays": True}}
    chats: dict[int, dict[str, Any]] = {}
    load_state(state_file, threads=threads, admin_chats=chats)
    # Existing entries cleared even when file missing (fresh boot semantics)
    assert threads == {}
    assert chats == {}


async def test_load_corrupted_file_starts_empty(state_file: Path) -> None:
    state_file.write_text("{ not valid", encoding="utf-8")
    threads: dict[int, dict[str, Any]] = {}
    chats: dict[int, dict[str, Any]] = {}
    load_state(state_file, threads=threads, admin_chats=chats)
    assert threads == {}
    assert chats == {}


async def test_save_overwrites_previous_snapshot(
    state_file: Path, save_lock: asyncio.Lock,
) -> None:
    await save_state(state_file, threads={1: {"v": 1}}, admin_chats={}, save_lock=save_lock)
    await save_state(state_file, threads={2: {"v": 2}}, admin_chats={}, save_lock=save_lock)

    threads: dict[int, dict[str, Any]] = {}
    chats: dict[int, dict[str, Any]] = {}
    load_state(state_file, threads=threads, admin_chats=chats)
    assert threads == {2: {"v": 2}}


async def test_expire_stale_threads_closes_old_and_keeps_recent(
    state_file: Path,
) -> None:
    from bot_app.handlers import support

    support.support_threads.clear()
    support.active_admin_chats.clear()
    support.init_state_store(state_file)

    now = datetime.now(timezone.utc)
    old_user_id = 42
    recent_user_id = 43
    admin_id = 100

    support.support_threads[old_user_id] = {
        "user_id": old_user_id,
        "username": "old",
        "last_user_message": now - timedelta(hours=2),
        "last_admin_reply": None,
        "prompt_sent": True,
        "user_ack_sent": True,
    }
    support.support_threads[recent_user_id] = {
        "user_id": recent_user_id,
        "username": "recent",
        "last_user_message": now - timedelta(minutes=2),
        "last_admin_reply": None,
        "prompt_sent": True,
        "user_ack_sent": True,
    }
    support.active_admin_chats[admin_id] = {"user_id": old_user_id, "username": "old"}

    bot = MagicMock()
    bot.send_message = AsyncMock()

    closed = await support.expire_stale_threads(bot)

    assert closed == 1
    assert old_user_id not in support.support_threads
    assert recent_user_id in support.support_threads
    assert admin_id not in support.active_admin_chats
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == old_user_id
