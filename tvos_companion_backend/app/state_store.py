from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any, Callable


DEFAULT_STATE: dict[str, Any] = {
    "accounts": [],
    "selectedAccountId": None,
    "pendingAuth": None,
    "localHistory": [],
    "recommendationPreferences": {},
}


class StateStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write_unlocked(copy.deepcopy(DEFAULT_STATE))

    def read(self) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            return copy.deepcopy(data)

    def update(self, updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            updater(data)
            self._write_unlocked(data)
            return copy.deepcopy(data)

    def reset(self) -> None:
        with self._lock:
            self._write_unlocked(copy.deepcopy(DEFAULT_STATE))

    def _read_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return copy.deepcopy(DEFAULT_STATE)
        with self._path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = copy.deepcopy(DEFAULT_STATE)
        if not isinstance(data, dict):
            data = copy.deepcopy(DEFAULT_STATE)
        for key, value in DEFAULT_STATE.items():
            data.setdefault(key, copy.deepcopy(value))
        return data

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
