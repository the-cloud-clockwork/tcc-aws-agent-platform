"""Tests for platform auth decorator wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestRequiresAccessToken:
    @patch("agent_core.identity.decorators._sdk_requires_access_token")
    def test_wraps_sdk_decorator(self, mock_sdk: MagicMock) -> None:
        mock_inner = MagicMock(side_effect=lambda fn: fn)
        mock_sdk.return_value = mock_inner

        from agent_core.identity.decorators import requires_access_token

        decorator = requires_access_token(
            provider_name="google-cal",
            scopes=["calendar"],
            auth_flow="USER_FEDERATION",
        )

        @decorator
        def my_func(*, access_token: str = "") -> str:
            return f"token={access_token}"

        mock_sdk.assert_called_once()
        call_kwargs = mock_sdk.call_args
        assert call_kwargs.kwargs["provider_name"] == "google-cal"
        assert call_kwargs.kwargs["auth_flow"] == "USER_FEDERATION"

    @patch("agent_core.identity.decorators._sdk_requires_access_token")
    def test_default_on_auth_url(self, mock_sdk: MagicMock) -> None:
        mock_sdk.return_value = lambda fn: fn

        from agent_core.identity.decorators import requires_access_token

        requires_access_token(provider_name="test")

        call_kwargs = mock_sdk.call_args.kwargs
        assert call_kwargs["on_auth_url"] is not None  # Uses default


class TestRequiresApiKey:
    @patch("agent_core.identity.decorators._sdk_requires_api_key")
    def test_wraps_sdk_decorator(self, mock_sdk: MagicMock) -> None:
        mock_sdk.return_value = lambda fn: fn

        from agent_core.identity.decorators import requires_api_key

        decorator = requires_api_key(provider_name="ext-api")

        @decorator
        def my_func(*, api_key: str = "") -> str:
            return f"key={api_key}"

        mock_sdk.assert_called_once_with(provider_name="ext-api", into="api_key")
