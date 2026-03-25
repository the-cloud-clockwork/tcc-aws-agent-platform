"""PromptRegistryClient -- resolves versioned prompts from the Lambda API."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import httpx
from aws_requests_auth.boto_utils import BotoAWSRequestsAuth

logger = logging.getLogger("agent_core.prompt")

_DEFAULT_REGISTRY_URL = "http://localhost:8080"


class PromptResolutionError(Exception):
    """Raised when a prompt cannot be resolved."""


class PromptRegistryClient:
    """Fetches prompt text from the Prompt Registry API.

    Resolution sequence:
    1. Call ``GET /prompts/{prompt_ref}`` on the registry API.
    2. If the registry is unavailable, fall back to a local file at
       ``{local_dir}/{prompt_ref}.txt``.

    Parameters
    ----------
    registry_url:
        Base URL for the registry API.  Defaults to ``PROMPT_REGISTRY_URL``
        env var, then ``http://localhost:8080``.
    local_dir:
        Path to a local directory of prompt text files (dev fallback).
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        registry_url: str | None = None,
        local_dir: str | Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.registry_url = (
            registry_url
            or os.environ.get("PROMPT_REGISTRY_URL")
            or _DEFAULT_REGISTRY_URL
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
            If the prompt cannot be resolved from either the registry or local
            fallback.
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
        url = f"{self.registry_url.rstrip('/')}/prompts/{prompt_ref}"
        parsed = urlparse(url)
        headers: dict[str, str] = {}

        # Lambda Function URLs with IAM auth require SigV4 signing
        if "lambda-url" in parsed.hostname or "amazonaws.com" in parsed.hostname:
            region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
            session = boto3.Session()
            credentials = session.get_credentials().get_frozen_credentials()
            auth = BotoAWSRequestsAuth(
                aws_host=parsed.hostname,
                aws_region=region,
                aws_service="lambda",
            )
            # BotoAWSRequestsAuth works with requests, not httpx.
            # Use requests for signed calls.
            import requests as req_lib

            resp = req_lib.get(url, auth=auth, timeout=self.timeout)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        else:
            resp = httpx.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

        text = data.get("text") or data.get("prompt_text") or data.get("body")
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
