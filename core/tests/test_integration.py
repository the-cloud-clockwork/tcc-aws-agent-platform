"""Integration tests using moto for AWS service simulation.

Tests real DynamoDB/S3 interactions without hitting AWS.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import boto3

# Set AWS env vars BEFORE importing modules that use boto3
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")


from moto import mock_aws

from agent_core.runtime.idempotency import IdempotencyStore, generate_idempotency_key
from agent_core.runtime.session import SessionManager, SessionState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_idempotency_table(table_name: str = "test_idempotency") -> None:
    """Create the idempotency DynamoDB table for moto."""
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "idempotency_key", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "idempotency_key", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _create_session_table(table_name: str = "run_history") -> None:
    """Create the sessions DynamoDB table for moto."""
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _create_artifacts_bucket(bucket_name: str = "test-artifacts") -> None:
    """Create the S3 artifacts bucket for moto."""
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )


# ---------------------------------------------------------------------------
# Tests: IdempotencyStore
# ---------------------------------------------------------------------------

class TestIdempotencyStoreIntegration:
    """Tests IdempotencyStore against moto DynamoDB."""

    @mock_aws
    def test_store_and_retrieve_roundtrip(self):
        _create_idempotency_table()
        store = IdempotencyStore(table_name="test_idempotency")

        key = generate_idempotency_key("test-agent", "analyze", {"item": "item-A"})
        result = {"status": "ok", "count": 3}

        # First check — no existing entry
        assert store.check(key) is None

        # Store result
        store.store(key, result)

        # Second check — should return cached result
        cached = store.check(key)
        assert cached is not None
        assert cached["status"] == "ok"
        assert cached["count"] == 3

    @mock_aws
    def test_duplicate_store_returns_cached(self):
        _create_idempotency_table()
        store = IdempotencyStore(table_name="test_idempotency")

        key = generate_idempotency_key("test-agent", "detect", {"date": "2026-03-15"})

        store.store(key, {"first": True})
        store.store(key, {"second": True})

        cached = store.check(key)
        assert cached is not None
        # First write wins (conditional put)
        assert cached.get("first") is True

    @mock_aws
    def test_ttl_attribute_set(self):
        _create_idempotency_table()
        store = IdempotencyStore(table_name="test_idempotency")

        key = "test-key-ttl"
        store.store(key, {"data": "test"}, ttl_hours=24)

        # Verify TTL attribute exists in raw DynamoDB item
        table = boto3.resource("dynamodb", region_name="eu-west-1").Table("test_idempotency")
        item = table.get_item(Key={"idempotency_key": key}).get("Item", {})
        assert "ttl" in item


# ---------------------------------------------------------------------------
# Tests: SessionManager
# ---------------------------------------------------------------------------

class TestSessionManagerIntegration:
    """Tests SessionManager against moto DynamoDB."""

    @mock_aws
    def test_create_and_persist_session(self):
        _create_session_table()
        # SessionManager reads table name from SESSION_TABLE env var (default: run_history)
        with patch.dict(os.environ, {"SESSION_TABLE": "run_history"}):
            manager = SessionManager(runtime_mode="lambda")

            session = manager.create_session(
                session_id="sfn-exec-001",
                agent_id="test_agent",
                execution_mode="simulation",
            )

            assert isinstance(session, SessionState)
            assert session.session_id == "sfn-exec-001"

            # Store some data
            session.store("analysis_result", {"items": ["item-A", "item-B"]})

            # Persist
            manager.persist_session(session)

            # Verify data was written to DynamoDB
            table = boto3.resource("dynamodb", region_name="eu-west-1").Table("run_history")
            item = table.get_item(Key={"session_id": "sfn-exec-001"}).get("Item")
            assert item is not None

    @mock_aws
    def test_session_retrieve_stored_value(self):
        _create_session_table()
        with patch.dict(os.environ, {"SESSION_TABLE": "run_history"}):
            manager = SessionManager(runtime_mode="lambda")

            session = manager.create_session(
                session_id="sfn-exec-002",
                agent_id="test_analyzer",
                execution_mode="simulation",
            )

            session.store("scores", {"item-A": 0.8, "item-B": 0.3})
            assert session.retrieve("scores")["item-A"] == 0.8
            assert session.retrieve("missing_key") is None


# ---------------------------------------------------------------------------
# Tests: marshal_output with S3 claim-check
# ---------------------------------------------------------------------------

class TestMarshalOutputIntegration:
    """Tests marshal_output S3 claim-check against moto S3."""

    @mock_aws
    def test_small_output_returns_directly(self):
        from agent_core.runtime.marshal import marshal_output

        result = {"status": "ok", "gaps": 3}
        output = marshal_output(result, agent_id="test", execution_id="exec-001")
        assert output == result
        assert "claim_check" not in output

    @mock_aws
    def test_large_output_uploads_to_s3(self):
        from agent_core.runtime.marshal import marshal_output

        _create_artifacts_bucket("test-artifacts")

        # Create a payload larger than 256KB
        large_result = {"data": "x" * (300 * 1024)}

        with patch.dict(os.environ, {"ARTIFACTS_BUCKET": "test-artifacts"}):
            output = marshal_output(
                large_result,
                agent_id="test-agent",
                execution_id="exec-002",
            )

        assert output["claim_check"] is True
        assert output["artifact_id"] is not None
        assert output["bucket"] == "test-artifacts"

        # Verify the object actually exists in moto S3
        s3 = boto3.client("s3", region_name="eu-west-1")
        obj = s3.get_object(Bucket="test-artifacts", Key=output["artifact_id"])
        body = json.loads(obj["Body"].read().decode("utf-8"))
        assert body["data"] == large_result["data"]

    @mock_aws
    def test_large_output_without_bucket_truncates(self):
        from agent_core.runtime.marshal import marshal_output

        large_result = {"data": "x" * (300 * 1024)}

        with patch.dict(os.environ, {}, clear=False):
            # Remove ARTIFACTS_BUCKET if present
            os.environ.pop("ARTIFACTS_BUCKET", None)
            output = marshal_output(
                large_result,
                agent_id="test-agent",
                execution_id="exec-003",
            )

        assert output["claim_check"] is True
        assert output["artifact_id"] is None
        assert "_overflow_warning" in output


# ---------------------------------------------------------------------------
# Tests: StrategyEvaluator (pure logic, uses real Pydantic models)
# ---------------------------------------------------------------------------

class TestStrategyEvaluatorIntegration:
    """Tests StrategyEvaluator against realistic strategy data."""

    def test_evaluate_multi_condition_strategy(self):
        from agent_core.blueprints.strategy import Condition, ConditionGroup, StrategyBlueprint
        from agent_core.blueprints.strategy_evaluator import StrategyEvaluator

        bp = StrategyBlueprint(
            id="multi_signal_entry",
            version="1.0.0",
            name="Multi Signal Entry",
            description="Enter when multiple signals confirm threshold",
            asset_types=["default"],
            scopes=["global"],
            required_signals=["score_a", "score_b", "ratio_a"],
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[
                    Condition(field="score_a", op="gte", value=2.0),
                    Condition(field="score_b", op="gte", value=0.6),
                    Condition(field="ratio_a", op="gt", value=1.5),
                ],
            ),
            exit_conditions=ConditionGroup(
                logic="OR",
                conditions=[
                    Condition(type="threshold_breach"),
                    Condition(field="elapsed_time", op="gte", value=5),
                ],
            ),
            required_agents=["detector"],
            required_mcps=["data-mcp"],
        )

        evaluator = StrategyEvaluator()

        # Strong signals — entry should match
        signals = {
            "score_a": 3.2,
            "score_b": 0.75,
            "ratio_a": 2.1,
            "threshold_breach": True,
            "elapsed_time": 2,
        }
        result = evaluator.evaluate(bp, signals)
        assert result.entry_matched is True
        assert result.exit_matched is True  # threshold_breach present
        assert result.score > 0.5

        # Weak signals — entry should not match
        weak_signals = {
            "score_a": 0.5,
            "score_b": 0.4,
            "ratio_a": 0.8,
        }
        result = evaluator.evaluate(bp, weak_signals)
        assert result.entry_matched is False

    def test_evaluate_all_ranks_by_score(self):
        from agent_core.blueprints.strategy import Condition, ConditionGroup, StrategyBlueprint
        from agent_core.blueprints.strategy_evaluator import StrategyEvaluator

        bp1 = StrategyBlueprint(
            id="strict",
            version="1.0.0",
            name="Strict",
            description="Strict",
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[
                    Condition(field="score_a", op="gt", value=5.0),
                    Condition(field="volume", op="gt", value=10000),
                ],
            ),
            exit_conditions=ConditionGroup(logic="AND", conditions=[]),
            required_agents=[],
            required_mcps=[],
        )
        bp2 = StrategyBlueprint(
            id="lenient",
            version="1.0.0",
            name="Lenient",
            description="Lenient",
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[
                    Condition(field="score_a", op="gt", value=1.0),
                ],
            ),
            exit_conditions=ConditionGroup(logic="AND", conditions=[]),
            required_agents=[],
            required_mcps=[],
        )

        results = StrategyEvaluator().evaluate_all([bp1, bp2], {"score_a": 3.0, "volume": 500})
        assert results[0].strategy_id == "lenient"
        assert results[0].entry_matched is True
