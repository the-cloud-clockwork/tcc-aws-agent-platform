"""Lambda wrapper for AgentCore Runtime invocation.

Replaces the SFN aws-sdk:bedrockagentcore:invokeAgentRuntime integration
which has a hardcoded 60s HTTP read timeout. This Lambda controls the
timeout (up to 15 minutes) and returns the same response shape.

Event format (matches SFN Parameters):
  {
    "AgentRuntimeArn": "arn:aws:bedrock-agentcore:...:runtime/...",
    "Qualifier": "DEFAULT",
    "Payload": {"prompt": "...", ...}  # or string
  }

Response format (matches SFN ResultSelector expectations):
  {
    "StatusCode": 200,
    "RuntimeSessionId": "...",
    "Response": "..."  # JSON string of agent output
  }
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import ssl

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
TIMEOUT = int(os.environ.get("AGENT_INVOKE_TIMEOUT", "600"))


def _get_credentials():
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()
    return creds


def handler(event: dict, context) -> dict:
    arn = event["AgentRuntimeArn"]
    qualifier = event.get("Qualifier", "DEFAULT")

    # Build the agent payload. SFN passes Prompt.$ (resolved from state)
    # and optional memory branching fields.
    prompt = event.get("Prompt", event.get("Payload", {}))
    memory_branch = event.get("MemoryBranch", "")
    memory_merge = event.get("MemoryMergeStrategy", "")

    if memory_branch:
        payload = {
            "prompt": prompt if isinstance(prompt, str) else json.dumps(prompt),
            "memory_branch": memory_branch,
            "memory_merge_strategy": memory_merge,
        }
    elif isinstance(prompt, dict):
        payload = prompt
    else:
        payload = {"prompt": str(prompt)}

    payload_bytes = json.dumps(payload).encode()

    encoded_arn = urllib.parse.quote(arn, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier={qualifier}"

    logger.info("Invoking %s (timeout=%ds)", arn, TIMEOUT)

    creds = _get_credentials()
    aws_req = AWSRequest(
        method="POST",
        url=url,
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(creds, "bedrock-agentcore", REGION).add_auth(aws_req)

    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers=dict(aws_req.headers),
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode()
            status = resp.status
    except Exception as exc:
        logger.error("Agent invocation failed: %s", exc)
        raise

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = body

    session_id = ""
    if isinstance(data, dict):
        session_id = data.get("session_id", data.get("runtimeSessionId", ""))

    return {
        "StatusCode": status,
        "RuntimeSessionId": session_id,
        "Response": body if isinstance(body, str) else json.dumps(data),
    }
