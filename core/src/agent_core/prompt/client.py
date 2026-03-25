"""PromptRegistryClient -- resolves versioned prompts from the Prompt Registry Lambda."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import boto3
import httpx

logger = logging.getLogger("agent_core.prompt")

_DEFAULT_REGISTRY_URL = "http://localhost:8080"


class PromptResolutionError(Exception):
    """Raised when a prompt cannot be resolved."""


class PromptRegistryClient:
    """Fetches prompt text from the Prompt Registry.

    Resolution sequence:
    1. If ``PROMPT_REGISTRY_FUNCTION`` env var is set, invoke the Lambda
       directly via ``boto3.client('lambda').invoke()``.  This is the
       production path inside AgentCore Runtime containers — boto3 handles
       SigV4 signing through the native credential chain.
    2. Otherwise, call ``GET /prompts/{prompt_ref}`` on the registry HTTP
       URL (for local dev or non-Lambda registries).
    3. If both fail, fall back to a local file at
       ``{local_dir}/{prompt_ref}.txt``.

    Parameters
    ----------
    registry_url:
        Base URL for the registry HTTP API.  Defaults to
        ``PROMPT_REGISTRY_URL`` env var, then ``http://localhost:8080``.
    lambda_function_name:
        Lambda function name or ARN for direct invocation.  Defaults to
        ``PROMPT_REGISTRY_FUNCTION`` env var.
    local_dir:
        Path to a local directory of prompt text files (dev fallback).
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        registry_url: str | None = None,
        lambda_function_name: str | None = None,
        local_dir: str | Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.registry_url = (
            registry_url
            or os.environ.get("PROMPT_REGISTRY_URL")
            or _DEFAULT_REGISTRY_URL
        )
        self.lambda_function_name = (
            lambda_function_name
            or os.environ.get("PROMPT_REGISTRY_FUNCTION", "")
        )
        self.local_dir = Path(local_dir) if local_dir else None
        self.timeout = timeout

    def get(self, prompt_ref: str) -> str:
        """Resolve *prompt_ref* to prompt text.

        Supports pinned versions (``my_agent_v1.2``) and latest-stable
        references (``my_agent``).

        Returns
        -------
        The resolved prompt text as a string.

        Raises
        ------
        PromptResolutionError
            If the prompt cannot be resolved from any source.
        """
        # Try remote registry first.
        try:
            return self._fetch_remote(prompt_ref)
        except Exception as exc:
            logger.warning(
                "Registry fetch failed for '%s': %s -- trying local fallback",
                prompt_ref,
                exc,
            )

        # Fallback to local file.
        return self._fetch_local(prompt_ref)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_remote(self, prompt_ref: str) -> str:
        if self.lambda_function_name:
            return self._invoke_lambda(prompt_ref)
        return self._fetch_http(prompt_ref)

    def _invoke_lambda(self, prompt_ref: str) -> str:
        """Invoke the Prompt Registry Lambda directly via boto3.

        This uses the native AWS credential chain (task role in AgentCore
        Runtime, instance profile on EC2, env vars locally) — the same
        chain that successfully calls Bedrock and Gateway.
        """
        client = boto3.client(
            "lambda",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )

        # Construct the event in Lambda Function URL v2.0 format
        event = {
            "rawPath": f"/prompts/{prompt_ref}",
            "requestContext": {
                "http": {"method": "GET", "path": f"/prompts/{prompt_ref}"},
            },
        }

        resp = client.invoke(
            FunctionName=self.lambda_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode(),
        )

        payload = json.loads(resp["Payload"].read())

        # The Lambda returns an API Gateway-style response with statusCode + body
        status_code = payload.get("statusCode", 500)
        body_raw = payload.get("body", "{}")
        data: dict[str, Any] = json.loads(body_raw) if isinstance(body_raw, str) else body_raw

        if status_code != 200:
            raise PromptResolutionError(
                f"Prompt Registry Lambda returned {status_code}: {data.get('error', body_raw)}"
            )

        return self._extract_text(data, prompt_ref)

    def _fetch_http(self, prompt_ref: str) -> str:
        """Fetch prompt via HTTP GET (local dev or non-Lambda registries)."""
        url = f"{self.registry_url.rstrip('/')}/prompts/{prompt_ref}"
        resp = httpx.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return self._extract_text(data, prompt_ref)

    def _extract_text(self, data: dict[str, Any], prompt_ref: str) -> str:
        """Extract prompt text from registry response."""
        text = (
            data.get("text")
            or data.get("content")
            or data.get("prompt_text")
            or data.get("body")
        )
        if not text:
            raise PromptResolutionError(
                f"Registry returned empty prompt for '{prompt_ref}'"
            )
        return str(text)

    def _fetch_local(self, prompt_ref: str) -> str:
        if self.local_dir is None:
            raise PromptResolutionError(
                f"No local_dir configured and registry unavailable for '{prompt_ref}'"
            )
        path = self.local_dir / f"{prompt_ref}.txt"
        if not path.exists():
            raise PromptResolutionError(
                f"Local prompt file not found: {path}"
            )
        return path.read_text(encoding="utf-8").strip()
