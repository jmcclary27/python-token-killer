"""Persistent cumulative token savings counters."""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

_APP_NAME = "python-token-killer"
_STATE_VERSION = 1
_TOKENIZER_HEURISTIC = "chars_per_token:4"
_DISABLED_VALUES = {"1", "true", "yes", "on"}

_LOCK = threading.Lock()
_enabled_override: bool | None = None
_path_override: Path | None = None


def configure(*, enabled: bool | None = None, path: str | os.PathLike[str] | None = None) -> None:
    """Configure automatic savings tracking for this process."""
    global _enabled_override, _path_override
    with _LOCK:
        if enabled is not None:
            _enabled_override = enabled
        if path is not None:
            _path_override = Path(path)


def current() -> dict[str, Any]:
    """Return the current cumulative savings state."""
    with _LOCK:
        return dict(_read_state(_state_path()))


def reset() -> dict[str, Any]:
    """Reset cumulative savings counters and return the reset state."""
    with _LOCK:
        state = _empty_state()
        _write_state(_state_path(), state)
        return dict(state)


def record(
    original_tokens: int | None,
    minimized_tokens: int | None,
    *,
    estimated: bool,
    tokenizer: str,
) -> None:
    """Record one minimization pass, silently ignoring persistence failures."""
    if original_tokens is None or minimized_tokens is None or not _tracking_enabled():
        return

    original = max(original_tokens, 0)
    minimized = max(minimized_tokens, 0)
    saved = max(original - minimized, 0)

    with _LOCK:
        path = _state_path()
        state = _read_state(path)
        previous_calls = int(state["calls"])
        previous_estimated = bool(state["estimated"])

        state["calls"] = previous_calls + 1
        state["total_original_tokens"] = int(state["total_original_tokens"]) + original
        state["total_minimized_tokens"] = int(state["total_minimized_tokens"]) + minimized
        state["total_saved_tokens"] = int(state["total_saved_tokens"]) + saved
        state["estimated"] = estimated if previous_calls == 0 else previous_estimated or estimated
        state["tokenizer"] = _TOKENIZER_HEURISTIC if state["estimated"] else tokenizer
        state["updated_at"] = _now()
        _write_state(path, state)


def _tracking_enabled() -> bool:
    if os.environ.get("PTK_SAVINGS_DISABLED", "").lower() in _DISABLED_VALUES:
        return False
    if _enabled_override is not None:
        return _enabled_override
    return True


def _state_path() -> Path:
    if _path_override is not None:
        return _path_override

    env_path = os.environ.get("PTK_SAVINGS_PATH")
    if env_path:
        return Path(env_path)

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_STATE_HOME")
        root = Path(base) if base else Path.home() / ".local" / "state"
    return root / _APP_NAME / "savings.json"


def _empty_state() -> dict[str, Any]:
    return {
        "version": _STATE_VERSION,
        "calls": 0,
        "total_original_tokens": 0,
        "total_minimized_tokens": 0,
        "total_saved_tokens": 0,
        "estimated": True,
        "tokenizer": _TOKENIZER_HEURISTIC,
        "updated_at": _now(),
    }


def _read_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return _empty_state()
    if not _valid_state(data):
        return _empty_state()
    return cast(dict[str, Any], data)


def _write_state(path: Path, state: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return


def _valid_state(data: object) -> bool:
    if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
        return False
    int_keys = ("calls", "total_original_tokens", "total_minimized_tokens", "total_saved_tokens")
    if any(not isinstance(data.get(key), int) or data[key] < 0 for key in int_keys):
        return False
    return isinstance(data.get("estimated"), bool) and isinstance(data.get("tokenizer"), str)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
