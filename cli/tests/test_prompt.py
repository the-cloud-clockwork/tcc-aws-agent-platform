"""Tests for agent_cli prompt sub-commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from agent_cli.main import app

runner = CliRunner()


def _mock_response(status_code: int, json_data: dict | list | None = None, text: str = "") -> httpx.Response:
    """Create a mock httpx.Response."""
    import json

    if json_data is not None:
        content = json.dumps(json_data).encode("utf-8")
        headers = {"content-type": "application/json"}
    else:
        content = text.encode("utf-8") if text else b""
        headers = {}

    resp = httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers,
        request=httpx.Request("GET", "http://test"),
    )
    return resp


class TestPromptPush:
    def test_push_success(self, tmp_path: Path):
        prompt_file = tmp_path / "test.txt"
        prompt_file.write_text("You are a helpful assistant.")

        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(201, {"status": "created"})

            result = runner.invoke(app, [
                "prompt", "push", str(prompt_file),
                "--id", "test-prompt",
                "--version", "1.0.0",
            ])

        assert result.exit_code == 0
        assert "Pushed" in result.output

    def test_push_file_not_found(self):
        result = runner.invoke(app, [
            "prompt", "push", "/nonexistent/file.txt",
            "--id", "test", "--version", "1.0.0",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestPromptGet:
    def test_get_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(200, {
                "prompt_id": "test-prompt",
                "version": "1.0.0",
                "status": "stable",
                "content": "You are a helpful assistant.",
            })

            result = runner.invoke(app, ["prompt", "get", "test-prompt"])

        assert result.exit_code == 0

    def test_get_not_found(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(404)

            result = runner.invoke(app, ["prompt", "get", "missing-prompt"])

        assert result.exit_code == 1


class TestPromptList:
    def test_list_versions(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.return_value = _mock_response(200, [
                {"version": "1.0.0", "status": "stable", "created_at": "2026-01-01", "content_hash": "abc123"},
                {"version": "0.9.0", "status": "draft", "created_at": "2025-12-01", "content_hash": "def456"},
            ])

            result = runner.invoke(app, ["prompt", "list", "test-prompt"])

        assert result.exit_code == 0


class TestPromptDiff:
    def test_diff_shows_changes(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.get.side_effect = [
                _mock_response(200, {"content": "Line 1\nLine 2\n"}),
                _mock_response(200, {"content": "Line 1\nLine 2 modified\n"}),
            ]

            result = runner.invoke(app, ["prompt", "diff", "test-prompt", "1.0.0", "2.0.0"])

        assert result.exit_code == 0


class TestPromptPromote:
    def test_promote_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(200)

            result = runner.invoke(app, ["prompt", "promote", "test-prompt", "1.0.0"])

        assert result.exit_code == 0
        assert "Promoted" in result.output


class TestPromptRollback:
    def test_rollback_success(self):
        with patch("agent_cli.prompt._client") as mock_client:
            mock_ctx = mock_client.return_value.__enter__.return_value
            mock_ctx.post.return_value = _mock_response(200)

            result = runner.invoke(app, ["prompt", "rollback", "test-prompt", "0.9.0"])

        assert result.exit_code == 0
        assert "Rolled back" in result.output
