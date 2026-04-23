import json
from pathlib import Path

import pytest
from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey

from bot_app.utils.json_storage import JSONFileStorage, _serialize_key


class DummyStates(StatesGroup):
    first = State()
    second = State()


def _key(user_id: int = 42) -> StorageKey:
    return StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


async def test_set_and_get_state_persists(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()

    await storage.set_state(key, DummyStates.first)

    assert await storage.get_state(key) == DummyStates.first.state
    assert state_file.exists()

    reloaded = JSONFileStorage(state_file)
    assert await reloaded.get_state(key) == DummyStates.first.state


async def test_clearing_state_drops_record(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()
    await storage.set_state(key, DummyStates.first)
    await storage.set_state(key, None)

    on_disk = json.loads(state_file.read_text(encoding="utf-8"))
    assert _serialize_key(key) not in on_disk


async def test_set_data_replaces_prior_value(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()

    await storage.set_data(key, {"phone": "+7"})
    await storage.set_data(key, {"first_name": "Alex"})

    assert await storage.get_data(key) == {"first_name": "Alex"}


async def test_update_data_merges(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()

    await storage.update_data(key, {"phone": "+7"})
    merged = await storage.update_data(key, {"first_name": "Alex"})

    assert merged == {"phone": "+7", "first_name": "Alex"}
    assert await storage.get_data(key) == {"phone": "+7", "first_name": "Alex"}


async def test_data_and_state_survive_reload(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()
    await storage.set_state(key, DummyStates.second)
    await storage.set_data(key, {"step": 2})

    reloaded = JSONFileStorage(state_file)
    assert await reloaded.get_state(key) == DummyStates.second.state
    assert await reloaded.get_data(key) == {"step": 2}


async def test_set_data_rejects_non_dict(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    with pytest.raises(DataNotDictLikeError):
        await storage.set_data(_key(), [("phone", "+7")])  # type: ignore[arg-type]


async def test_get_data_returns_copy(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key()
    await storage.set_data(key, {"items": [1, 2]})

    snapshot = await storage.get_data(key)
    snapshot["items"].append(999)

    fresh = await storage.get_data(key)
    assert fresh == {"items": [1, 2]}


async def test_missing_key_returns_empty_defaults(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    key = _key(user_id=999)

    assert await storage.get_state(key) is None
    assert await storage.get_data(key) == {}


async def test_corrupted_file_starts_empty(state_file: Path) -> None:
    state_file.write_text("{not valid json", encoding="utf-8")

    storage = JSONFileStorage(state_file)
    assert await storage.get_state(_key()) is None


async def test_different_users_do_not_collide(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    await storage.set_state(_key(user_id=1), DummyStates.first)
    await storage.set_state(_key(user_id=2), DummyStates.second)

    assert await storage.get_state(_key(user_id=1)) == DummyStates.first.state
    assert await storage.get_state(_key(user_id=2)) == DummyStates.second.state


async def test_close_is_idempotent(state_file: Path) -> None:
    storage = JSONFileStorage(state_file)
    await storage.set_state(_key(), DummyStates.first)
    await storage.close()
    await storage.close()
