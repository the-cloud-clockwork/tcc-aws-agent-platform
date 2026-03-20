"""Tests for DynamoDB registry operations."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from prompt_registry.models import PromptStatus, PromptVersion
from prompt_registry.registry import PromptRegistry

TABLE_NAME = "prompt_registry"


@pytest.fixture
def registry():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield PromptRegistry(table_name=TABLE_NAME, dynamodb_resource=dynamodb)


def _make_prompt(prompt_id: str, version: str, status: str = "draft") -> PromptVersion:
    return PromptVersion(
        prompt_id=prompt_id,
        version=version,
        description=f"Test {version}",
        status=PromptStatus(status),
        s3_key=f"{prompt_id}/{version}.txt",
        tags=["test"],
    )


class TestRegistryPutGet:
    def test_put_and_get_version(self, registry):
        prompt = _make_prompt("my_agent", "1.0.0")
        registry.put_version(prompt)

        result = registry.get_version("my_agent", "1.0.0")
        assert result is not None
        assert result.prompt_id == "my_agent"
        assert result.version == "1.0.0"
        assert result.status == PromptStatus.DRAFT

    def test_get_nonexistent_version(self, registry):
        result = registry.get_version("my_agent", "99.0.0")
        assert result is None


class TestRegistryListVersions:
    def test_list_versions_sorted(self, registry):
        for ver in ["2.0.0", "1.0.0", "1.2.0"]:
            registry.put_version(_make_prompt("my_agent", ver))

        versions = registry.list_versions("my_agent")
        assert len(versions) == 3
        assert [v.version for v in versions] == ["1.0.0", "1.2.0", "2.0.0"]

    def test_list_versions_empty(self, registry):
        versions = registry.list_versions("nonexistent")
        assert versions == []


class TestRegistryLatestStable:
    def test_get_latest_stable(self, registry):
        v1 = _make_prompt("my_agent", "1.0.0", "stable")
        v2 = _make_prompt("my_agent", "1.2.0", "stable")
        v3 = _make_prompt("my_agent", "2.0.0", "draft")
        for v in [v1, v2, v3]:
            registry.put_version(v)

        latest = registry.get_latest_stable("my_agent")
        assert latest is not None
        assert latest.version == "1.2.0"

    def test_no_stable_returns_none(self, registry):
        registry.put_version(_make_prompt("my_agent", "1.0.0", "draft"))
        assert registry.get_latest_stable("my_agent") is None


class TestRegistryPromote:
    def test_promote_version(self, registry):
        registry.put_version(_make_prompt("my_agent", "1.0.0", "stable"))
        registry.put_version(_make_prompt("my_agent", "2.0.0", "draft"))

        result = registry.promote("my_agent", "2.0.0")
        assert result is not None
        assert result.status == PromptStatus.STABLE

        # Old stable should be deprecated
        old = registry.get_version("my_agent", "1.0.0")
        assert old.status == PromptStatus.DEPRECATED


class TestRegistryRollback:
    def test_rollback_to_previous(self, registry):
        registry.put_version(_make_prompt("my_agent", "1.0.0", "deprecated"))
        registry.put_version(_make_prompt("my_agent", "2.0.0", "stable"))

        result = registry.rollback("my_agent", "1.0.0")
        assert result is not None
        assert result.status == PromptStatus.STABLE

        # Current stable should be deprecated
        old = registry.get_version("my_agent", "2.0.0")
        assert old.status == PromptStatus.DEPRECATED

    def test_rollback_nonexistent(self, registry):
        result = registry.rollback("my_agent", "99.0.0")
        assert result is None
