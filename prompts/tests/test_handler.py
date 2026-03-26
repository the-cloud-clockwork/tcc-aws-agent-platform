"""Tests for prompt_registry.handler — Lambda routing and validation."""

from __future__ import annotations

from prompt_registry.handler import (
    _ERR_PROMPT_ID_REQUIRED,
    _parse_body,
    _response,
    handle_diff,
    handle_get_prompt,
    handle_list_versions,
    handle_promote,
    handle_rollback,
    handler,
)


class TestResponse:
    def test_structure(self) -> None:
        resp = _response(200, {"ok": True})
        assert resp["statusCode"] == 200
        assert "application/json" in resp["headers"]["Content-Type"]
        assert '"ok": true' in resp["body"]


class TestParseBody:
    def test_string_body(self) -> None:
        assert _parse_body({"body": '{"a": 1}'}) == {"a": 1}

    def test_empty_body(self) -> None:
        assert _parse_body({"body": ""}) == {}

    def test_dict_body(self) -> None:
        assert _parse_body({"body": {"x": 2}}) == {"x": 2}

    def test_none_body(self) -> None:
        assert _parse_body({}) == {}


class TestPromptIdRequired:
    """All handlers that take prompt_id from path must return the same constant error."""

    def _event_without_prompt_id(self) -> dict:
        return {"pathParameters": {}}

    def test_get_prompt_requires_id(self) -> None:
        resp = handle_get_prompt(self._event_without_prompt_id())
        assert resp["statusCode"] == 400
        assert _ERR_PROMPT_ID_REQUIRED in resp["body"]

    def test_list_versions_requires_id(self) -> None:
        resp = handle_list_versions(self._event_without_prompt_id())
        assert resp["statusCode"] == 400
        assert _ERR_PROMPT_ID_REQUIRED in resp["body"]

    def test_promote_requires_id(self) -> None:
        resp = handle_promote(self._event_without_prompt_id())
        assert resp["statusCode"] == 400
        assert _ERR_PROMPT_ID_REQUIRED in resp["body"]

    def test_rollback_requires_id(self) -> None:
        resp = handle_rollback(self._event_without_prompt_id())
        assert resp["statusCode"] == 400
        assert _ERR_PROMPT_ID_REQUIRED in resp["body"]

    def test_diff_requires_id(self) -> None:
        resp = handle_diff(self._event_without_prompt_id())
        assert resp["statusCode"] == 400
        assert _ERR_PROMPT_ID_REQUIRED in resp["body"]


class TestRouter:
    def test_unknown_route(self) -> None:
        resp = handler({"httpMethod": "GET", "path": "/unknown"})
        assert resp["statusCode"] == 404

    def test_routes_post_prompts(self) -> None:
        resp = handler({"httpMethod": "POST", "path": "/prompts", "body": "{}"})
        assert resp["statusCode"] == 400  # missing required fields, but routed correctly
