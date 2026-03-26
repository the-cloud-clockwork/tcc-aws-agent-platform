"""Tests for PolicyClient — mocked SDK calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.policy.client import (
    PolicyClient,
    PolicyConfigError,
    PolicyError,
    PolicyMode,
)


class TestPolicyClientInit:
    def test_missing_region_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(PolicyConfigError, match="Region required"):
                PolicyClient()

    def test_init_from_env(self):
        """Verify PolicyClient can be instantiated when region is set."""
        import sys

        mock_boto3 = MagicMock()
        conflict_exc = type("ConflictException", (Exception,), {})
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = conflict_exc
        mock_boto3.client.return_value = mock_client

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            with patch.dict("os.environ", {"AWS_REGION": "eu-west-1"}):
                client = PolicyClient()
                assert client._region == "eu-west-1"


class TestPolicyMode:
    def test_enforce(self):
        assert PolicyMode.ENFORCE.value == "ENFORCE"

    def test_log_only(self):
        assert PolicyMode.LOG_ONLY.value == "LOG_ONLY"


class TestPolicyClientOperations:
    """Tests with fully mocked SDK clients."""

    @pytest.fixture()
    def client(self):
        mock_boto_client = MagicMock()
        mock_sdk_instance = MagicMock()

        # Create proper exception classes so `except client.exceptions.X` works
        conflict_exc = type("ConflictException", (Exception,), {})
        mock_boto_client.exceptions.ConflictException = conflict_exc

        c = PolicyClient.__new__(PolicyClient)
        c._region = "eu-west-1"
        c._boto_client = mock_boto_client
        c._sdk_client = mock_sdk_instance
        yield c

    def test_create_engine(self, client):
        client._boto_client.create_policy_engine.return_value = {
            "policyEngineArn": "arn:aws:policy:123",
            "policyEngineId": "pe-123",
        }
        result = client.create_engine("TestEngine", "desc")
        assert result["policyEngineArn"] == "arn:aws:policy:123"
        client._boto_client.create_policy_engine.assert_called_once_with(
            name="TestEngine", description="desc"
        )

    def test_create_engine_failure(self, client):
        client._boto_client.create_policy_engine.side_effect = Exception("boom")
        with pytest.raises(PolicyError, match="CREATE_ENGINE_FAILED"):
            client.create_engine("TestEngine")

    def test_create_policy(self, client):
        client._boto_client.create_policy.return_value = {"policyId": "p1"}
        result = client.create_policy("pe-123", "my-policy", "permit(...);")
        assert result["policyId"] == "p1"
        client._boto_client.create_policy.assert_called_once_with(
            policyEngineId="pe-123",
            name="my-policy",
            definition={"cedar": {"statement": "permit(...);"}},
            validationMode="IGNORE_ALL_FINDINGS",
        )

    def test_list_policies(self, client):
        client._sdk_client.list_policies.return_value = [{"policyId": "p1"}]
        result = client.list_policies("pe-123")
        assert len(result) == 1

    def test_delete_policy(self, client):
        client.delete_policy("pe-123", "p1")
        client._sdk_client.delete_policy.assert_called_once_with(
            policy_engine_id="pe-123", policy_id="p1"
        )

    def test_get_engine(self, client):
        client._boto_client.get_policy_engine.return_value = {"name": "E"}
        result = client.get_engine("pe-123")
        assert result["name"] == "E"

    def test_delete_engine(self, client):
        client.delete_engine("pe-123")
        client._boto_client.delete_policy_engine.assert_called_once_with(
            policyEngineId="pe-123"
        )

    def test_generate_policy_nl2cedar(self, client):
        client._sdk_client.generate_policy.return_value = {
            "generatedPolicies": [
                {"definition": {"cedar": {"statement": "permit(...);"}}}
            ]
        }
        result = client.generate_policy(
            engine_id="pe-123",
            name="nl-test",
            gateway_arn="arn:aws:gw:123",
            natural_language="Allow all users to query data",
        )
        assert "generatedPolicies" in result
        client._sdk_client.generate_policy.assert_called_once()
