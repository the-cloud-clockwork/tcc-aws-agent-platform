"""Tests for VersionedS3Store — latest pointer, caching, store + load."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from agent_core.mcp.versioned_store import VersionedS3Store, _override_s3_client


def _make_s3_response(body: bytes) -> dict:
    """Create a mock S3 get_object response."""
    stream = MagicMock()
    stream.read.return_value = body
    return {"Body": stream}


@pytest.fixture
def mock_s3():
    client = MagicMock()
    _override_s3_client(client)
    yield client
    _override_s3_client(None)


@pytest.fixture
def store(mock_s3):
    return VersionedS3Store("TEST_BUCKET", "test-bucket")


class TestGetLatestVersion:
    def test_reads_latest_pointer(self, store, mock_s3):
        mock_s3.get_object.return_value = _make_s3_response(b"v3")

        version = store.get_latest_version("gap_model")
        assert version == "v3"
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="gap_model/latest"
        )

    def test_falls_back_to_v1(self, store, mock_s3):
        mock_s3.get_object.side_effect = Exception("NotFound")

        version = store.get_latest_version("gap_model")
        assert version == "v1"


class TestLoadBytes:
    def test_load_with_explicit_version(self, store, mock_s3):
        mock_s3.get_object.return_value = _make_s3_response(b"\x00\x01\x02")

        data = store.load_bytes("gap_model", "model.joblib", version="v2")
        assert data == b"\x00\x01\x02"
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="gap_model/v2/model.joblib"
        )

    def test_load_resolves_latest(self, store, mock_s3):
        mock_s3.get_object.side_effect = [
            _make_s3_response(b"v5"),       # latest pointer
            _make_s3_response(b"payload"),   # actual file
        ]

        data = store.load_bytes("gap_model", "model.joblib")
        assert data == b"payload"
        assert mock_s3.get_object.call_count == 2

    def test_caching_avoids_repeated_s3_calls(self, store, mock_s3):
        mock_s3.get_object.return_value = _make_s3_response(b"cached")

        store.load_bytes("m", "f.bin", version="v1")
        store.load_bytes("m", "f.bin", version="v1")

        assert mock_s3.get_object.call_count == 1

    def test_clear_cache(self, store, mock_s3):
        mock_s3.get_object.return_value = _make_s3_response(b"data")

        store.load_bytes("m", "f.bin", version="v1")
        store.clear_cache()
        store.load_bytes("m", "f.bin", version="v1")

        assert mock_s3.get_object.call_count == 2


class TestLoadJson:
    def test_parses_json(self, store, mock_s3):
        payload = json.dumps({"accuracy": 0.95}).encode()
        mock_s3.get_object.return_value = _make_s3_response(payload)

        result = store.load_json("gap_model", version="v1")
        assert result == {"accuracy": 0.95}


class TestStore:
    def test_stores_files_and_latest(self, store, mock_s3):
        path = store.store(
            "gap_model",
            "v2",
            {"model.joblib": b"\x00", "metadata.json": b'{"v": 2}'},
        )

        assert path == "s3://test-bucket/gap_model/v2/"
        assert mock_s3.put_object.call_count == 3  # 2 files + latest pointer

        # Verify latest pointer
        calls = mock_s3.put_object.call_args_list
        latest_call = [c for c in calls if c.kwargs.get("Key", c[1].get("Key", "")) == "gap_model/latest"]
        # Use positional or keyword args
        found_latest = any(
            "gap_model/latest" in str(c) for c in calls
        )
        assert found_latest

    def test_store_without_latest(self, store, mock_s3):
        store.store("m", "v1", {"f.bin": b"data"}, set_latest=False)
        assert mock_s3.put_object.call_count == 1  # only the file

    def test_bucket_from_env(self, mock_s3, monkeypatch):
        monkeypatch.setenv("MY_BUCKET", "custom-bucket")
        s = VersionedS3Store("MY_BUCKET")
        assert s.bucket == "custom-bucket"
