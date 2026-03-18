"""Shared test fixtures for prompt registry tests."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from prompt_registry.registry import PromptRegistry
from prompt_registry.storage import PromptStorage

TEST_TABLE = "prompt_registry"
TEST_BUCKET = "prompt-registry"

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_prompts"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_TABLE", TEST_TABLE)
    monkeypatch.setenv("S3_BUCKET", TEST_BUCKET)


@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=TEST_TABLE,
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
        table.meta.client.get_waiter("table_exists").wait(
            TableName=TEST_TABLE
        )
        yield dynamodb


@pytest.fixture
def s3_bucket():
    """Create a mocked S3 bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=TEST_BUCKET)
        yield s3


@pytest.fixture
def mock_aws_all():
    """Mock all AWS services together (for integration tests)."""
    with mock_aws():
        # DynamoDB
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TEST_TABLE,
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

        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=TEST_BUCKET)

        yield {
            "dynamodb": dynamodb,
            "s3": s3,
            "registry": PromptRegistry(
                table_name=TEST_TABLE, dynamodb_resource=dynamodb
            ),
            "storage": PromptStorage(
                bucket=TEST_BUCKET, s3_client=s3
            ),
        }


@pytest.fixture
def sample_prompt_text() -> dict[str, str]:
    """Load sample prompt texts from fixtures."""
    texts = {}
    for path in FIXTURES_DIR.rglob("*.txt"):
        key = f"{path.parent.name}/{path.stem}"
        texts[key] = path.read_text()
    return texts
