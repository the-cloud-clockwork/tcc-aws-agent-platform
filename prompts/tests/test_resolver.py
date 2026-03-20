"""Tests for prompt reference resolution."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from prompt_registry.models import Mode, PromptStatus, PromptVersion
from prompt_registry.registry import PromptRegistry
from prompt_registry.resolver import PromptResolver, parse_prompt_ref
from prompt_registry.storage import PromptStorage

TABLE_NAME = "prompt_registry"
BUCKET_NAME = "prompt-registry"


class TestParsePromptRef:
    def test_plain_name(self):
        result = parse_prompt_ref("my_agent")
        assert result.prompt_id == "my_agent"
        assert result.version is None

    def test_underscore_v_format(self):
        result = parse_prompt_ref("my_agent_v1.2")
        assert result.prompt_id == "my_agent"
        assert result.version == "1.2"

    def test_underscore_v_format_full_semver(self):
        result = parse_prompt_ref("my_agent_v1.2.0")
        assert result.prompt_id == "my_agent"
        assert result.version == "1.2.0"

    def test_at_format(self):
        result = parse_prompt_ref("portfolio_recommender@2.0.0")
        assert result.prompt_id == "portfolio_recommender"
        assert result.version == "2.0.0"

    def test_complex_name_v_format(self):
        result = parse_prompt_ref("my_complex_prompt_v3.1")
        assert result.prompt_id == "my_complex_prompt"
        assert result.version == "3.1"


@pytest.fixture
def resolver_env():
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

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_NAME)

        registry = PromptRegistry(table_name=TABLE_NAME, dynamodb_resource=dynamodb)
        storage = PromptStorage(bucket=BUCKET_NAME, s3_client=s3)
        resolver = PromptResolver(registry, storage)

        # Seed data
        for ver, status, text in [
            ("1.0.0", "stable", "You are gap detector v1."),
            ("1.2.0", "stable", "You are gap detector v1.2."),
            ("2.0.0", "draft", "You are gap detector v2 (draft)."),
        ]:
            storage.put("my_agent", ver, text)
            registry.put_version(PromptVersion(
                prompt_id="my_agent",
                version=ver,
                status=PromptStatus(status),
                s3_key=f"my_agent/{ver}.txt",
            ))

        yield resolver


class TestResolverPinned:
    def test_resolve_at_format(self, resolver_env):
        result = resolver_env.resolve("my_agent@1.0.0", mode=Mode.PRODUCTION)
        assert result is not None
        assert result.version == "1.0.0"
        assert "v1." in result.content

    def test_resolve_v_format(self, resolver_env):
        result = resolver_env.resolve("my_agent_v1.2.0", mode=Mode.PRODUCTION)
        assert result is not None
        assert result.version == "1.2.0"

    def test_resolve_short_version_pads(self, resolver_env):
        """my_agent_v1.2 should resolve to 1.2.0."""
        result = resolver_env.resolve("my_agent_v1.2", mode=Mode.PRODUCTION)
        assert result is not None
        assert result.version == "1.2.0"

    def test_draft_blocked_in_production_mode(self, resolver_env):
        result = resolver_env.resolve("my_agent@2.0.0", mode=Mode.PRODUCTION)
        assert result is None

    def test_draft_allowed_in_simulation_mode(self, resolver_env):
        result = resolver_env.resolve("my_agent@2.0.0", mode=Mode.SIMULATION)
        assert result is not None
        assert result.status == PromptStatus.DRAFT

    def test_draft_allowed_in_dev_mode(self, resolver_env):
        result = resolver_env.resolve("my_agent@2.0.0", mode=Mode.DEV)
        assert result is not None


class TestResolverLatest:
    def test_resolve_latest_stable(self, resolver_env):
        result = resolver_env.resolve("my_agent", mode=Mode.PRODUCTION)
        assert result is not None
        assert result.version == "1.2.0"
        assert result.status == PromptStatus.STABLE

    def test_resolve_nonexistent(self, resolver_env):
        result = resolver_env.resolve("nonexistent", mode=Mode.PRODUCTION)
        assert result is None
