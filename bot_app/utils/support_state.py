from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _encode(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return {"__dt__": obj.isoformat()}
    if isinstance(obj, dict):
        return {str(k): _encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    return obj


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        if set(obj.keys()) == {"__dt__"}:
            try:
                return datetime.fromisoformat(obj["__dt__"])
            except (TypeError, ValueError):
                return None
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Failed to load support state from %s, starting empty", path)
        return {}
    return raw if isinstance(raw, dict) else {}


def _restore_int_keyed(raw: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        try:
            result[int(k)] = v
        except (TypeError, ValueError):
            continue
    return result


def load_state(
    path: Path,
    *,
    threads: dict[int, dict[str, Any]],
    admin_chats: dict[int, dict[str, Any]],
) -> None:
    """Populate the dicts in place from disk. No-op if file is missing."""
    raw = _load_raw(path)
    decoded_threads = _decode(raw.get("threads", {}))
    decoded_chats = _decode(raw.get("chats", {}))
    threads.clear()
    admin_chats.clear()
    if isinstance(decoded_threads, dict):
        threads.update(_restore_int_keyed(decoded_threads))
    if isinstance(decoded_chats, dict):
        admin_chats.update(_restore_int_keyed(decoded_chats))


async def save_state(
    path: Path,
    *,
    threads: Mapping[int, Mapping[str, Any]],
    admin_chats: Mapping[int, Mapping[str, Any]],
    save_lock: asyncio.Lock,
) -> None:
    """Atomic save via tempfile + os.replace. Serialised by save_lock."""
    async with save_lock:
        payload = {
            "threads": _encode(dict(threads)),
            "chats": _encode(dict(admin_chats)),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False)
        fd, tmp_str = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        tmp = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(encoded)
            os.replace(tmp, path)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
