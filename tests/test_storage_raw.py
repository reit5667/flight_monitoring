"""Integration tests for storage/raw.py — requires running PostgreSQL (docker compose up -d)."""
import time
from pathlib import Path

import pytest

from storage.raw import save_raw, load_raw, RAW_STORAGE_DIR


@pytest.fixture(autouse=True)
def cleanup_files(tmp_path, monkeypatch):
    """Redirect raw_storage writes to a temp dir so tests don't pollute the repo."""
    import storage.raw as raw_module
    monkeypatch.setattr(raw_module, "RAW_STORAGE_DIR", tmp_path / "raw_storage")
    yield


def test_save_raw_creates_file(tmp_path, monkeypatch):
    import storage.raw as raw_module
    base = tmp_path / "raw_storage"
    monkeypatch.setattr(raw_module, "RAW_STORAGE_DIR", base)

    snapshot = save_raw({"price": 100}, "aviasales", 1)

    file_path = Path(snapshot.file_path)
    assert file_path.exists(), "JSON file must be created on disk"
    assert "aviasales/1" in snapshot.file_path


def test_save_raw_returns_snapshot_with_id():
    snapshot = save_raw({"test": 1}, "aviasales", 1)
    assert snapshot.id is not None and snapshot.id > 0
    assert snapshot.source == "aviasales"
    assert snapshot.route_id == 1


def test_load_raw_returns_same_data():
    data = {"flights": [{"price": 200, "airline": "AirAsia"}]}
    snapshot = save_raw(data, "aviasales", 1)
    loaded = load_raw(snapshot.id)
    assert loaded == data


def test_save_raw_twice_creates_two_files():
    s1 = save_raw({"n": 1}, "aviasales", 1)
    time.sleep(0.01)  # ensure distinct microsecond timestamps
    s2 = save_raw({"n": 2}, "aviasales", 1)

    assert s1.file_path != s2.file_path
    assert s1.id != s2.id


def test_save_raw_creates_directories_automatically(tmp_path, monkeypatch):
    import storage.raw as raw_module
    nested = tmp_path / "deep" / "raw_storage"
    monkeypatch.setattr(raw_module, "RAW_STORAGE_DIR", nested)

    snapshot = save_raw({"x": 1}, "trip", 1)  # route_id=1 exists from seed migration
    assert Path(snapshot.file_path).exists()


def test_load_raw_raises_for_missing_snapshot():
    with pytest.raises(ValueError, match="not found"):
        load_raw(999_999_999)


def test_save_raw_records_count_stored():
    snapshot = save_raw({"data": []}, "aviasales", 1, records_count=42)
    assert snapshot.records_count == 42
