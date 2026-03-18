"""Shared fixtures for artifact MCP tests."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.storage import ArtifactStorage

BUCKET_NAME = "mcp-artifacts"
TABLE_NAME = "mcp_artifacts"
REGION = "us-east-1"


@pytest.fixture()
def aws_env(monkeypatch):
    """Set dummy AWS env vars for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture()
def mock_s3(aws_env):
    """Provide a mocked S3 client with the artifacts bucket created."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME)
        storage = ArtifactStorage(s3_client=s3, bucket=BUCKET_NAME)
        yield storage


@pytest.fixture()
def mock_dynamodb(aws_env):
    """Provide a mocked DynamoDB resource with the artifacts table created."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        ArtifactCatalog.ensure_table(dynamodb_resource=ddb, table_name=TABLE_NAME)
        catalog = ArtifactCatalog(dynamodb_resource=ddb, table_name=TABLE_NAME)
        yield catalog


@pytest.fixture()
def mock_aws_all(aws_env):
    """Provide both mocked S3 and DynamoDB together (same mock context)."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME)
        storage = ArtifactStorage(s3_client=s3, bucket=BUCKET_NAME)

        ddb = boto3.resource("dynamodb", region_name=REGION)
        ArtifactCatalog.ensure_table(dynamodb_resource=ddb, table_name=TABLE_NAME)
        catalog = ArtifactCatalog(dynamodb_resource=ddb, table_name=TABLE_NAME)

        yield storage, catalog
