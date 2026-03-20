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


def _create_artifacts_bucket(bucket_name: str = "qitp-artifacts") -> None:
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

        key = generate_idempotency_key("test-agent", "analyze", {"symbol": "AAPL"})
        result = {"status": "ok", "gaps": 3}

        # First check — no existing entry
        assert store.check(key) is None

        # Store result
        store.store(key, result)

        # Second check — should return cached result
        cached = store.check(key)
        assert cached is not None
        assert cached["status"] == "ok"
        assert cached["gaps"] == 3

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
                agent_id="gap_detector",
                execution_mode="simulation",
            )

            assert isinstance(session, SessionState)
            assert session.session_id == "sfn-exec-001"

            # Store some data
            session.store("analysis_result", {"gaps": ["AAPL", "TSLA"]})

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
                agent_id="sentiment_analyzer",
                execution_mode="simulation",
            )

            session.store("sentiment", {"AAPL": 0.8, "TSLA": 0.3})
            assert session.retrieve("sentiment")["AAPL"] == 0.8
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

    def test_evaluate_gap_momentum_strategy(self):
        from agent_core.blueprints.strategy import Condition, ConditionGroup, StrategyBlueprint
        from agent_core.blueprints.strategy_evaluator import StrategyEvaluator

        bp = StrategyBlueprint(
            id="gap_momentum_up",
            version="1.0.0",
            name="Gap Momentum Up",
            description="Long on upward gaps with volume confirmation",
            asset_types=["stock"],
            scopes=["US"],
            required_signals=["gap_pct", "sentiment_score", "volume_ratio"],
            entry_conditions=ConditionGroup(
                logic="AND",
                conditions=[
                    Condition(field="gap_pct", op="gte", value=2.0),
                    Condition(field="sentiment_score", op="gte", value=0.6),
                    Condition(field="volume_ratio", op="gt", value=1.5),
                ],
            ),
            exit_conditions=ConditionGroup(
                logic="OR",
                conditions=[
                    Condition(type="trailing_stop"),
                    Condition(field="holding_days", op="gte", value=5),
                ],
            ),
            required_agents=["gap_detector"],
            required_mcps=["market-data-mcp"],
        )

        evaluator = StrategyEvaluator()

        # Bullish signals — entry should match
        signals = {
            "gap_pct": 3.2,
            "sentiment_score": 0.75,
            "volume_ratio": 2.1,
            "trailing_stop": True,
            "holding_days": 2,
        }
        result = evaluator.evaluate(bp, signals)
        assert result.entry_matched is True
        assert result.exit_matched is True  # trailing_stop present
        assert result.score > 0.5

        # Weak signals — entry should not match
        weak_signals = {
            "gap_pct": 0.5,
            "sentiment_score": 0.4,
            "volume_ratio": 0.8,
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
                    Condition(field="gap_pct", op="gt", value=5.0),
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
                    Condition(field="gap_pct", op="gt", value=1.0),
                ],
            ),
            exit_conditions=ConditionGroup(logic="AND", conditions=[]),
            required_agents=[],
            required_mcps=[],
        )

        results = StrategyEvaluator().evaluate_all([bp1, bp2], {"gap_pct": 3.0, "volume": 500})
        assert results[0].strategy_id == "lenient"
        assert results[0].entry_matched is True
