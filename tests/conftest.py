"""Shared pytest configuration — adds src/ to sys.path for all test packages."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# Ensure ptk is importable from the src/ layout without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ptk  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_savings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep cumulative savings tests away from the user's real state file."""
    monkeypatch.delenv("PTK_SAVINGS_DISABLED", raising=False)
    monkeypatch.delenv("PTK_SAVINGS_PATH", raising=False)
    ptk.configure_savings(enabled=True, path=tmp_path / "savings.json")
    ptk.reset_savings()
    yield
    ptk.configure_savings(enabled=True, path=tmp_path / "savings.json")
