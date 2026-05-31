"""Cumulative token savings tracking tests."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import ptk


class TestSavingsAPI:
    def test_savings_initial_state(self):
        state = ptk.savings()
        assert state["version"] == 1
        assert state["calls"] == 0
        assert state["total_saved_tokens"] == 0
        assert state["estimated"] is True

    def test_minimize_records_savings(self):
        ptk.minimize({"name": "Alice", "bio": None, "notes": ""})
        state = ptk.savings()
        assert state["calls"] == 1
        assert state["total_original_tokens"] >= state["total_minimized_tokens"]
        assert state["total_saved_tokens"] >= 0

    def test_callable_module_records_savings(self):
        ptk({"name": "Alice", "bio": None})
        assert ptk.savings()["calls"] == 1

    def test_stats_records_savings(self):
        result = ptk.stats({"name": "Alice", "bio": None, "notes": ""})
        state = ptk.savings()
        assert state["calls"] == 1
        assert state["total_original_tokens"] == result["original_tokens"]
        assert state["total_minimized_tokens"] == result["minimized_tokens"]

    def test_reset_savings(self):
        ptk.minimize({"name": "Alice", "bio": None})
        state = ptk.reset_savings()
        assert state["calls"] == 0
        assert ptk.savings()["total_saved_tokens"] == 0

    def test_disabled_tracking_via_api(self):
        ptk.configure_savings(enabled=False)
        ptk.minimize({"name": "Alice", "bio": None})
        assert ptk.savings()["calls"] == 0

    def test_disabled_tracking_via_env(self, monkeypatch):
        monkeypatch.setenv("PTK_SAVINGS_DISABLED", "1")
        ptk.minimize({"name": "Alice", "bio": None})
        assert ptk.savings()["calls"] == 0

    def test_env_path_override(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "env" / "savings.json"
        ptk.configure_savings(enabled=True, path=tmp_path / "configured.json")
        monkeypatch.setenv("PTK_SAVINGS_PATH", str(path))

        # Process configuration takes precedence over the environment once set.
        ptk.minimize({"name": "Alice", "bio": None})
        assert not path.exists()

        ptk.configure_savings(enabled=True, path=path)
        ptk.minimize({"name": "Alice", "bio": None})
        assert path.exists()

    def test_no_raw_content_written(self, tmp_path: Path):
        path = tmp_path / "private.json"
        secret = "do-not-store-this-prompt"
        ptk.configure_savings(enabled=True, path=path)
        ptk.minimize({"secret": secret, "empty": None})

        written = path.read_text(encoding="utf-8")
        assert secret not in written
        assert "secret" not in written
        assert "output" not in written

    def test_corrupt_file_recovers(self, tmp_path: Path):
        path = tmp_path / "savings.json"
        ptk.configure_savings(enabled=True, path=path)
        path.write_text("not json", encoding="utf-8")

        assert ptk.savings()["calls"] == 0
        ptk.minimize({"name": "Alice", "bio": None})
        assert ptk.savings()["calls"] == 1

    def test_negative_savings_clamped_to_zero(self):
        ptk.minimize("x", content_type="text")
        state = ptk.savings()
        assert state["total_saved_tokens"] == 0
        assert state["calls"] == 1

    def test_state_file_contains_only_metadata_keys(self, tmp_path: Path):
        path = tmp_path / "savings.json"
        ptk.configure_savings(enabled=True, path=path)
        ptk.minimize({"name": "Alice", "bio": None})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) == {
            "version",
            "calls",
            "total_original_tokens",
            "total_minimized_tokens",
            "total_saved_tokens",
            "estimated",
            "tokenizer",
            "updated_at",
        }


class TestSavingsConcurrency:
    def test_concurrent_tracking_keeps_valid_json(self, tmp_path: Path):
        path = tmp_path / "savings.json"
        ptk.configure_savings(enabled=True, path=path)
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(20):
                    ptk.minimize({"name": "Alice", "bio": None, "notes": ""})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["calls"] == 100
