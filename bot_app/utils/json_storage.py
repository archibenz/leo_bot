from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

logger = logging.getLogger(__name__)


def _serialize_key(key: StorageKey) -> str:
    return "|".join(
        [
            str(key.bot_id),
            str(key.chat_id),
            str(key.thread_id) if key.thread_id is not None else "",
            str(key.user_id),
            key.business_connection_id or "",
            key.destiny,
        ]
    )


@dataclass
class _Record:
    state: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return self.state is None and not self.data


class JSONFileStorage(BaseStorage):
    """File-backed FSM storage with atomic writes.

    Every set_state/set_data persists the entire store via a temp-file
    swap so a crash mid-write cannot corrupt the file. Designed for a
    single-process bot — cross-process access is not coordinated.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._records: dict[str, _Record] = self._load_from_disk()
        self._closed = False

    def _load_from_disk(self) -> dict[str, _Record]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception(
                "Failed to load FSM state from %s, starting empty", self._path
            )
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, _Record] = {}
        for k, v in raw.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            state_val = v.get("state")
            data_val = v.get("data")
            if state_val is not None and not isinstance(state_val, str):
                continue
            if data_val is not None and not isinstance(data_val, dict):
                data_val = {}
            result[k] = _Record(state=state_val, data=data_val or {})
        return result

    async def _save_to_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            k: {"state": r.state, "data": r.data}
            for k, r in self._records.items()
            if not r.is_empty()
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=self._path.parent,
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(encoded)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

    def _get_or_create(self, key: StorageKey) -> _Record:
        serialized = _serialize_key(key)
        record = self._records.get(serialized)
        if record is None:
            record = _Record()
            self._records[serialized] = record
        return record

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        resolved = state.state if isinstance(state, State) else state
        async with self._lock:
            record = self._get_or_create(key)
            record.state = resolved
            if record.is_empty():
                self._records.pop(_serialize_key(key), None)
            await self._save_to_disk()

    async def get_state(self, key: StorageKey) -> str | None:
        record = self._records.get(_serialize_key(key))
        return record.state if record else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)
        async with self._lock:
            record = self._get_or_create(key)
            record.data = dict(data)
            if record.is_empty():
                self._records.pop(_serialize_key(key), None)
            await self._save_to_disk()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record = self._records.get(_serialize_key(key))
        return deepcopy(record.data) if record else {}

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            await self._save_to_disk()
