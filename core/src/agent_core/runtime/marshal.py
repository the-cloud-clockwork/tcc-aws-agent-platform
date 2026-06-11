"""Output marshalling with mandatory S3 artifact storage + DynamoDB catalog."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Tool names whose toolUse.input wraps the typed payload under a "content" key.
# StructuredOutputEnforcer's synthetic toolUse uses the schema class name and
# its input IS the typed payload — those are handled in the else branch.
_KNOWN_TOOL_PASSTHROUGH = {"create_artifact"}

_FENCED_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

# Pattern for tool names that look like Pydantic schemas — used to filter out
# arbitrary tool calls (get_*, set_*, etc.) when scanning for the "structured
# output" toolUse synthesized by StructuredOutputEnforcer. Schemas are
# CamelCase, optionally with trailing "Output", "Report", "Recommendation",
# "Result", etc.
_SCHEMA_NAME_RE = re.compile(
    r"^[A-Z][a-zA-Z0-9]*"
    r"(?:Output|Report|Recommendation|Result|Response|Analysis|Prediction|Evaluation|Confirmation)?$"
)


def _looks_like_schema_name(name: Any) -> bool:
    """True when a toolUse name looks like a Pydantic schema (CamelCase)."""
    return isinstance(name, str) and bool(_SCHEMA_NAME_RE.match(name))


def _tool_name_matches(name: Any, known: set[str]) -> bool:
    """True when a toolUse name matches a known tool, tolerating the
    AgentCore Gateway's '<server>___<tool>' MCP namespacing — e.g.
    'artifacts-mcp___create_artifact' matches 'create_artifact'."""
    if not isinstance(name, str):
        return False
    return name in known or name.rsplit("___", 1)[-1] in known


def _parse_fenced_json(text: str) -> dict[str, Any] | None:
    """Return the first parseable JSON object from a ```json``` code fence."""
    for match in _FENCED_JSON_RE.finditer(text):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _extract_from_content_list(content: list[Any]) -> dict[str, Any] | None:
    """Scan a single Strands message content list for a typed payload.

    Priority within the list:
      1. Reversed scan for a toolUse — if name is a create_artifact-style
         passthrough, return ``input.content`` when it's a dict; otherwise
         the toolUse came from StructuredOutputEnforcer (or any other tool
         the agent invoked) and ``input`` itself is the typed payload.
      2. Forward scan for a fenced ```json``` code block in any text block.
      3. ``None`` if neither matches.
    """
    if not isinstance(content, list):
        return None

    for block in reversed(content):
        if not isinstance(block, dict):
            continue
        tool_use = block.get("toolUse")
        if not isinstance(tool_use, dict):
            continue
        input_ = tool_use.get("input")
        if not isinstance(input_, dict):
            continue
        name = tool_use.get("name")
        if _tool_name_matches(name, _KNOWN_TOOL_PASSTHROUGH):
            inner = input_.get("content")
            if isinstance(inner, dict):
                return inner
            if isinstance(inner, str):
                try:
                    parsed = json.loads(inner)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return parsed
            continue
        # Non-passthrough toolUse — only treat as typed payload when the name
        # matches a Pydantic schema pattern (CamelCase, optionally with a
        # known suffix). Skips arbitrary tool calls like get_ohlcv whose
        # input would otherwise leak into the artifact (see audit §J — the
        # sentiment-analyzer extracted {config: ...} because its final
        # toolUse was an upstream-data fetch with the config as input).
        if _looks_like_schema_name(name):
            return input_
        continue

    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        parsed = _parse_fenced_json(text)
        if parsed is not None:
            return parsed

    return None


def _extract_from_multiagent_envelope(
    envelope: dict[str, Any],
) -> dict[str, Any] | None:
    """Walk a multiagent_result envelope for typed sub-agent payloads.

    Each ``envelope.results[node_name].result`` is either an ``agent_result``
    envelope (with .message.content[]) or a nested ``multiagent_result``.
    For agent_result nodes, scan the last message via
    ``_extract_from_content_list``. For nested multiagent_result nodes,
    recurse.

    Returns an aggregate dict keyed by node name when at least one sub-agent
    produced a typed payload. Single-node graphs return the inner payload
    directly (no wrapping by node name). ``None`` when no sub-agent had an
    extractable payload — caller falls back to envelope.
    """
    results = envelope.get("results")
    if not isinstance(results, dict) or not results:
        return None

    extracted: dict[str, Any] = {}
    for node_name, node in results.items():
        if not isinstance(node, dict):
            continue
        node_result = node.get("result")
        if not isinstance(node_result, dict):
            continue
        node_type = node_result.get("type")
        if node_type == "multiagent_result":
            nested = _extract_from_multiagent_envelope(node_result)
            if isinstance(nested, dict) and nested:
                extracted[node_name] = nested
            continue
        # agent_result — walk its last message content
        message = node_result.get("message")
        if not isinstance(message, dict):
            continue
        payload = _extract_from_content_list(message.get("content", []))
        if payload is not None:
            extracted[node_name] = payload

    if not extracted:
        return None
    if len(extracted) == 1:
        only_value = next(iter(extracted.values()))
        if isinstance(only_value, dict):
            return only_value
    return extracted


def _extract_typed_payload(
    envelope: dict[str, Any],
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Best-effort extraction of a typed payload from a Strands envelope.

    Priority:
      1. ``conversation_history`` (when provided): walk in reverse for any
         assistant message containing a ``create_artifact`` toolUse whose
         ``input.content`` is a dict — that dict is the typed payload the
         agent already shipped to the platform tier. Catches the case where
         the final assistant message is a markdown summary with no toolUse
         (StructuredOutputEnforcer fell over silently).
      2. Multiagent envelope (type == "multiagent_result"): walk sub-agent
         last messages for typed payloads, aggregate by node name (v3 scope).
      3. Last assistant message's toolUse.input — either the StructuredOutput
         Enforcer's synthetic block (input == typed payload) or a
         create_artifact tool call (input.content == typed payload).
      4. Fenced ```json``` block in any text content of the last message.
      5. None — caller falls back to the envelope itself.
    """
    if conversation_history:
        # 1a. Walk all history for a create_artifact toolUse (agent explicitly
        #     shipped a typed artifact mid-conversation).
        for msg in reversed(conversation_history):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "assistant":
                continue
            msg_content = msg.get("content")
            if not isinstance(msg_content, list):
                continue
            for block in reversed(msg_content):
                if not isinstance(block, dict):
                    continue
                tool_use = block.get("toolUse")
                if not isinstance(tool_use, dict):
                    continue
                if not _tool_name_matches(
                    tool_use.get("name"), _KNOWN_TOOL_PASSTHROUGH
                ):
                    continue
                input_ = tool_use.get("input")
                if not isinstance(input_, dict):
                    continue
                inner = input_.get("content")
                if isinstance(inner, dict):
                    return inner
                if isinstance(inner, str):
                    try:
                        parsed = json.loads(inner)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        return parsed

        # 1b. The LAST assistant message in conversation_history is the
        #     post-hook truth — captured from session.messages AFTER
        #     AfterInvocationEvent fired. Strands builds AgentResult BEFORE
        #     that hook, so envelope["message"] can be a stale pre-hook copy
        #     that misses the StructuredOutputEnforcer's synthetic toolUse.
        #     Scan the live last message for a schema-named toolUse / fenced
        #     JSON before falling back to the (possibly stale) envelope.
        for msg in reversed(conversation_history):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "assistant":
                continue
            payload = _extract_from_content_list(msg.get("content", []))
            if payload is not None:
                return payload
            break

    if envelope.get("type") == "multiagent_result":
        return _extract_from_multiagent_envelope(envelope)

    message = envelope.get("message")
    if not isinstance(message, dict):
        return None
    return _extract_from_content_list(message.get("content", []))


def _find_create_artifact_result(
    messages: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Locate the most recent successful create_artifact toolResult in history.

    Walks messages forward, tracking create_artifact toolUseIds emitted by
    the assistant; whenever a matching toolResult lands in a subsequent user
    message with ``status == "success"``, extract ``artifact_id`` + ``s3_key``
    and remember it. Returns the LAST such match (most recent call wins).

    Handles two toolResult content shapes:
      - ``[{"json": {...}}]`` — Strands' newer typed-result shape
      - ``[{"text": "<json-string>"}]`` — older / wrapped shape

    Returns ``{"artifact_id": str, "s3_key": str}`` or ``None`` when no
    successful create_artifact call is found.
    """
    if not messages:
        return None

    pending_ids: set[str] = set()
    latest: dict[str, Any] | None = None

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        if role == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                tool_use = block.get("toolUse")
                if not isinstance(tool_use, dict):
                    continue
                if not _tool_name_matches(
                    tool_use.get("name"), _KNOWN_TOOL_PASSTHROUGH
                ):
                    continue
                tool_use_id = tool_use.get("toolUseId")
                if isinstance(tool_use_id, str):
                    pending_ids.add(tool_use_id)
            continue

        if role != "user":
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            tool_result = block.get("toolResult")
            if not isinstance(tool_result, dict):
                continue
            tool_use_id = tool_result.get("toolUseId")
            if tool_use_id not in pending_ids:
                continue
            # Status field is optional in practice — some Strands transports
            # omit it on success. Treat anything other than explicit "error"
            # as success.
            status = tool_result.get("status")
            if status == "error":
                continue
            payload = _extract_tool_result_payload(tool_result.get("content"))
            if payload is None:
                continue
            artifact_id = payload.get("artifact_id")
            s3_key = payload.get("s3_key")
            if not isinstance(artifact_id, str) or not isinstance(s3_key, str):
                continue
            latest = {"artifact_id": artifact_id, "s3_key": s3_key}

    return latest


def _extract_tool_result_payload(
    content: Any,
) -> dict[str, Any] | None:
    """Extract a dict payload from a toolResult ``content`` field.

    Strands typically wraps toolResult bodies as a list of content blocks,
    each carrying either ``{"json": {...}}`` or ``{"text": "<json-string>"}``.
    Some MCP transports surface the payload as a bare dict instead. Accept
    all three shapes.
    """
    if isinstance(content, dict):
        return content
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("json"), dict):
            return block["json"]
        text = block.get("text")
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _serialize_result(
    result: Any,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert an agent result to a plain dict, preferring typed payloads.

    For Strands AgentResult objects (which expose to_dict()), the wire envelope
    AND the optional full conversation history are searched for a typed payload
    before falling back to the envelope itself. See _extract_typed_payload for
    priority. This closes the soft-failure where domain-tier S3 artifacts stored
    the conversation envelope rather than the schema the agent produced.
    """
    if hasattr(result, "to_dict"):
        output = result.to_dict()
        if hasattr(output, "to_dict"):
            output = output.to_dict()
        if isinstance(output, dict):
            extracted = _extract_typed_payload(output, conversation_history)
            return extracted if extracted is not None else output
        return {"raw_output": str(output)}
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        try:
            return dict(result)
        except TypeError:
            if hasattr(result, "__getitem__"):
                return {k: result[k] for k in result}
            return {"raw_output": str(result)}
    try:
        return json.loads(str(result))
    except (json.JSONDecodeError, TypeError):
        return {"raw_output": str(result)}


def _register_catalog(
    artifact_id: str,
    agent_id: str,
    execution_id: str,
    s3_key: str,
    bucket: str,
    tier: str,
    kms_key_alias: str | None,
    date: str,
) -> None:
    """Register artifact in DynamoDB catalog. Non-fatal on failure."""
    table_name = os.environ.get("ARTIFACTS_TABLE", "")
    if not table_name:
        return

    try:
        import boto3

        ddb = boto3.resource("dynamodb")
        table = ddb.Table(table_name)
        now = datetime.now(timezone.utc).isoformat()
        table.put_item(
            Item={
                "artifact_id": artifact_id,
                "agent_id": agent_id,
                "execution_id": execution_id,
                "artifact_type": "agent_output",
                "s3_key": s3_key,
                "s3_bucket": bucket,
                "tier": tier,
                "status": "ready",
                "content_type": "application/json",
                "created_at": now,
                "updated_at": now,
                "pipeline_date": date,
                "kms_key_alias": kms_key_alias or "",
                "claim_check": True,
            }
        )
        logger.info("Artifact %s registered in catalog (%s)", artifact_id, table_name)
    except Exception as err:
        logger.warning(
            "Failed to register artifact %s in catalog: %s", artifact_id, err
        )


def _alias_platform_artifact(
    platform_ref: dict[str, str],
    agent_id: str,
    execution_id: str,
    *,
    tier: str,
    kms_key_alias: str | None,
    date: str,
    s3_bucket: str | None = None,
) -> dict[str, Any] | None:
    """Register a domain-tier catalog row pointing at an existing platform artifact.

    Skips the duplicate S3 write that ``marshal_output`` would otherwise do.
    Loads the platform artifact body to populate ``output`` so SFN's ``$.output``
    still carries the typed payload inline (preserves claim-check semantics for
    downstream states).

    Returns the same shape as ``marshal_output``: artifact_id, s3_key, bucket,
    tier, agent_id, success, claim_check, output. Returns ``None`` when the
    platform artifact body cannot be fetched or is not parseable JSON — the
    caller then falls back to its own validated S3 write instead of handing
    downstream states an s3_key that points at a corrupt document.
    """
    platform_s3_key = platform_ref["s3_key"]
    bucket = s3_bucket or os.environ.get("ARTIFACTS_BUCKET")
    if not bucket:
        logger.warning(
            "No ARTIFACTS_BUCKET configured — cannot alias platform artifact"
        )
        return None

    domain_artifact_id = str(uuid.uuid4())

    try:
        import boto3

        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        s3 = boto3.client("s3")
        get_kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": platform_s3_key,
            "ExpectedBucketOwner": account_id,
        }
        try:
            obj = s3.get_object(**get_kwargs)
            body = obj["Body"].read()
            output = json.loads(body)
            if not isinstance(output, dict):
                output = {"raw_output": output}
        except Exception as load_err:
            # Aliasing a body we can't read or parse would canonicalize a
            # corrupt artifact (the truncated-recommendation soft failure).
            # Bail out — marshal_output writes its own validated copy.
            logger.warning(
                "Platform artifact %s unreadable/corrupt (%s) — falling back "
                "to validated marshal write instead of aliasing",
                platform_s3_key,
                load_err,
            )
            return None

        _register_catalog(
            artifact_id=domain_artifact_id,
            agent_id=agent_id,
            execution_id=execution_id,
            s3_key=platform_s3_key,
            bucket=bucket,
            tier=tier,
            kms_key_alias=kms_key_alias,
            date=date,
        )

        logger.info(
            "Aliased platform artifact %s -> domain catalog row %s (s3://%s/%s)",
            platform_ref["artifact_id"],
            domain_artifact_id,
            bucket,
            platform_s3_key,
        )

        return {
            "artifact_id": domain_artifact_id,
            "s3_key": platform_s3_key,
            "bucket": bucket,
            "tier": tier,
            "agent_id": agent_id,
            "success": True,
            "claim_check": True,
            "output": output,
        }
    except Exception:
        logger.exception(
            "Failed to alias platform artifact — falling back to marshal write"
        )
        return None


def marshal_output(
    result: Any,
    agent_id: str,
    execution_id: str,
    s3_bucket: str | None = None,
    tier: str = "platform",
    kms_key_alias: str | None = None,
    date: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert agent result to dict, upload to S3, register in DynamoDB catalog.

    Every agent execution produces a JSON artifact in S3 + a DynamoDB catalog
    entry — unconditionally. Artifacts are the source of truth.

    When ``conversation_history`` contains a successful ``create_artifact``
    toolResult, the duplicate S3 write is skipped and a catalog row is written
    pointing at the existing platform artifact (Option B alias path). The
    inline ``output`` is still populated from that artifact for SFN passthrough.

    Args:
        result: Agent output (Pydantic model, dict, or str).
        agent_id: Agent identifier for S3 key prefix.
        execution_id: Execution/session ID for S3 key.
        s3_bucket: S3 bucket for storage. Falls back to ARTIFACTS_BUCKET env var.
        tier: Storage tier — "platform" or "domain".
        kms_key_alias: KMS key alias for server-side encryption (optional).
        date: Analysis date (YYYY-MM-DD). Defaults to today.
        conversation_history: Optional full Strands agent message history,
            captured by the handler before MCP client teardown. Used to find
            create_artifact toolResults for aliasing and to walk earlier
            toolUse blocks for typed payload extraction.

    Returns:
        JSON-serializable dict with artifact_id, s3_key, bucket, tier, and output.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not execution_id:
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"

    platform_ref = _find_create_artifact_result(conversation_history)
    if platform_ref is not None:
        aliased = _alias_platform_artifact(
            platform_ref,
            agent_id,
            execution_id,
            tier=tier,
            kms_key_alias=kms_key_alias,
            date=date,
            s3_bucket=s3_bucket,
        )
        if aliased is not None:
            return aliased

    output = _serialize_result(result, conversation_history=conversation_history)
    serialized = json.dumps(output, default=str)

    bucket = s3_bucket or os.environ.get("ARTIFACTS_BUCKET")
    if not bucket:
        logger.warning("No ARTIFACTS_BUCKET configured — artifact not stored")
        return {
            "artifact_id": "",
            "s3_key": "",
            "bucket": "",
            "tier": tier,
            "agent_id": agent_id,
            "success": False,
            "error": "no_bucket",
            "output": output,
        }

    artifact_id = str(uuid.uuid4())
    s3_key = f"{tier}/{date}/{execution_id}/{agent_id}.json"

    try:
        import boto3

        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        put_kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": s3_key,
            "Body": serialized.encode("utf-8"),
            "ContentType": "application/json",
            "ExpectedBucketOwner": account_id,
        }
        if kms_key_alias:
            put_kwargs["ServerSideEncryption"] = "aws:kms"
            put_kwargs["SSEKMSKeyId"] = kms_key_alias

        s3 = boto3.client("s3")
        s3.put_object(**put_kwargs)
        logger.info(
            "Artifact stored: s3://%s/%s (%d bytes, tier=%s)",
            bucket,
            s3_key,
            len(serialized),
            tier,
        )

        # Mandatory: register in DynamoDB catalog
        _register_catalog(
            artifact_id=artifact_id,
            agent_id=agent_id,
            execution_id=execution_id,
            s3_key=s3_key,
            bucket=bucket,
            tier=tier,
            kms_key_alias=kms_key_alias,
            date=date,
        )

        return {
            "artifact_id": artifact_id,
            "s3_key": s3_key,
            "bucket": bucket,
            "tier": tier,
            "agent_id": agent_id,
            "success": True,
            "claim_check": True,
            "output": output,
        }
    except Exception as exc:
        logger.exception("Failed to upload artifact to S3")
        return {
            "artifact_id": "",
            "s3_key": "",
            "bucket": bucket,
            "tier": tier,
            "agent_id": agent_id,
            "success": False,
            "error": str(exc),
            "output": output,
        }
