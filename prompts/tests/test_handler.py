"""Tests for Lambda handler / API Gateway integration."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from prompt_registry.handler import handler

TABLE_NAME = "prompt_registry"
BUCKET_NAME = "prompt-registry"


def _api_event(
    method: str,
    path: str,
    body: dict | None = None,
    query: dict | None = None,
    path_params: dict | None = None,
) -> dict:
    """Build a minimal API Gateway proxy event."""
    event = {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": query,
        "pathParameters": path_params,
        "body": json.dumps(body) if body else None,
    }
    return event


@pytest.fixture
def api_env(monkeypatch):
    """Set up mocked AWS services for handler tests."""
    with mock_aws():
        monkeypatch.setenv("DYNAMODB_TABLE", TABLE_NAME)
        monkeypatch.setenv("S3_BUCKET", BUCKET_NAME)

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

        # Reload handler module to pick up env vars
        import prompt_registry.handler as h
        h.TABLE_NAME = TABLE_NAME
        h.BUCKET_NAME = BUCKET_NAME

        yield


class TestCreatePrompt:
    def test_create_success(self, api_env):
        event = _api_event("POST", "/prompts", body={
            "prompt_id": "my_agent",
            "version": "1.0.0",
            "content": "You are a gap detector.",
            "description": "Initial version",
            "tags": ["gap"],
        })
        resp = handler(event)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["prompt_id"] == "my_agent"
        assert body["status"] == "draft"

    def test_create_duplicate_fails(self, api_env):
        event = _api_event("POST", "/prompts", body={
            "prompt_id": "my_agent",
            "version": "1.0.0",
            "content": "text",
        })
        handler(event)
        resp = handler(event)
        assert resp["statusCode"] == 409

    def test_create_invalid_body(self, api_env):
        event = _api_event("POST", "/prompts", body={"bad": "data"})
        resp = handler(event)
        assert resp["statusCode"] == 400


class TestGetPrompt:
    def test_get_latest_stable(self, api_env):
        # Create and promote
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.0.0",
            "content": "Version one.",
        }))
        handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))

        resp = handler(_api_event(
            "GET", "/prompts/my_agent",
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "1.0.0"
        assert body["content"] == "Version one."

    def test_get_specific_version(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.0.0",
            "content": "V1.",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "2.0.0",
            "content": "V2.",
        }))
        # Promote 1.0.0
        handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))

        # Get specific draft in simulation mode
        resp = handler(_api_event(
            "GET", "/prompts/my_agent",
            query={"version": "2.0.0", "mode": "simulation"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "2.0.0"
        assert body["content"] == "V2."

    def test_get_not_found(self, api_env):
        resp = handler(_api_event(
            "GET", "/prompts/nonexistent",
            path_params={"prompt_id": "nonexistent"},
        ))
        assert resp["statusCode"] == 404


class TestListVersions:
    def test_list_versions(self, api_env):
        for ver in ["1.0.0", "1.2.0", "2.0.0"]:
            handler(_api_event("POST", "/prompts", body={
                "prompt_id": "my_agent", "version": ver,
                "content": f"Version {ver}.",
            }))

        resp = handler(_api_event(
            "GET", "/prompts/my_agent/versions",
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["versions"]) == 3


class TestPromote:
    def test_promote_success(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.0.0", "content": "V1.",
        }))

        resp = handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "stable"

    def test_promote_nonexistent(self, api_env):
        resp = handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "99.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 404


class TestRollback:
    def test_rollback_success(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.0.0", "content": "V1.",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "2.0.0", "content": "V2.",
        }))
        # Promote 1.0.0 then 2.0.0
        handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        handler(_api_event(
            "POST", "/prompts/my_agent/promote",
            body={"version": "2.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))

        # Rollback to 1.0.0
        resp = handler(_api_event(
            "POST", "/prompts/my_agent/rollback",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "1.0.0"
        assert body["status"] == "stable"


class TestDiff:
    def test_diff_two_versions(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.0.0",
            "content": "Line 1\nLine 2\nLine 3\n",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "my_agent", "version": "1.2.0",
            "content": "Line 1\nLine 2 modified\nLine 3\nLine 4\n",
        }))

        resp = handler(_api_event(
            "GET", "/prompts/my_agent/diff",
            query={"v1": "1.0.0", "v2": "1.2.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "Line 2 modified" in body["diff"]
        assert body["v1"] == "1.0.0"
        assert body["v2"] == "1.2.0"

    def test_diff_missing_params(self, api_env):
        resp = handler(_api_event(
            "GET", "/prompts/my_agent/diff",
            query={"v1": "1.0.0"},
            path_params={"prompt_id": "my_agent"},
        ))
        assert resp["statusCode"] == 400


class TestRouting:
    def test_unknown_route(self, api_env):
        resp = handler(_api_event("DELETE", "/prompts/whatever"))
        assert resp["statusCode"] == 404
