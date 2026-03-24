"""PromptRegistryClient -- resolves versioned prompts from multiple backends."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("agent_core.prompt")

_DEFAULT_REGISTRY_URL = "http://localhost:8080"

_REF_VERSION_RE = re.compile(r"^(.+?)(?:_v|@)(\d+(?:\.\d+)*)$")


class PromptResolutionError(Exception):
    """Raised when a prompt cannot be resolved."""


class PromptRegistryClient:
    """Fetches prompt text from the Prompt Registry.

    Resolution sequence (first success wins):

    1. **Direct S3 + DynamoDB** -- when ``PROMPT_REGISTRY_TABLE`` and
       ``PROMPT_REGISTRY_BUCKET`` env vars are set, read metadata from
       DynamoDB and content from S3.  No HTTP API required.
    2. **HTTP API** -- call ``GET /prompts/{prompt_ref}`` on the registry
       Lambda (requires a deployed API endpoint).
    3. **Local file** -- fall back to ``{local_dir}/{prompt_ref}.txt``.

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
            If the prompt cannot be resolved from any backend.
        """
        # 1. Try direct S3 + DynamoDB (no HTTP API needed).
        if os.environ.get("PROMPT_REGISTRY_TABLE"):
            try:
                return self._fetch_direct(prompt_ref)
            except Exception as exc:
                logger.warning(
                    "Direct S3+DDB fetch failed for '%s': %s",
                    prompt_ref,
                    exc,
                )

        # 2. Try remote HTTP registry.
        try:
            return self._fetch_remote(prompt_ref)
        except Exception as exc:
            logger.warning(
                "Registry fetch failed for '%s': %s -- trying local fallback",
                prompt_ref,
                exc,
            )

        # 3. Fallback to local file.
        return self._fetch_local(prompt_ref)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ref(prompt_ref: str) -> tuple[str, str | None]:
        """Parse a prompt reference into ``(prompt_id, version | None)``.

        Supported formats::

            "qitp/gap-detector"           -> ("qitp/gap-detector", None)
            "qitp/gap-detector_v1.0.0"    -> ("qitp/gap-detector", "1.0.0")
            "gap-detector@2.1"            -> ("gap-detector", "2.1")
        """
        m = _REF_VERSION_RE.match(prompt_ref)
        if m:
            return m.group(1), m.group(2)
        return prompt_ref, None

    def _fetch_direct(self, prompt_ref: str) -> str:
        """Resolve prompt directly from S3 + DynamoDB (no HTTP API)."""
        import boto3
        from boto3.dynamodb.conditions import Attr, Key

        table_name = os.environ.get("PROMPT_REGISTRY_TABLE")
        bucket_name = os.environ.get("PROMPT_REGISTRY_BUCKET")
        if not (table_name and bucket_name):
            raise PromptResolutionError(
                "Direct access requires PROMPT_REGISTRY_TABLE and "
                "PROMPT_REGISTRY_BUCKET env vars"
            )

        prompt_id, version = self._parse_ref(prompt_ref)

        ddb = boto3.resource(
            "dynamodb",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )
        table = ddb.Table(table_name)

        if version:
            resp = table.get_item(
                Key={"prompt_key": prompt_id, "version": version}
            )
            item = resp.get("Item")
        else:
            resp = table.query(
                KeyConditionExpression=Key("prompt_key").eq(prompt_id),
                FilterExpression=Attr("status").eq("stable"),
                ScanIndexForward=False,
                Limit=1,
            )
            items = resp.get("Items", [])
            item = items[0] if items else None

        if not item:
            raise PromptResolutionError(
                f"Prompt not found in registry: {prompt_ref}"
            )

        s3_key = item.get("s3_key")
        if not s3_key:
            raise PromptResolutionError(
                f"Prompt metadata missing s3_key: {prompt_ref}"
            )

        s3 = boto3.client(
            "s3",
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"),
        )
        obj = s3.get_object(Bucket=bucket_name, Key=s3_key)
        text = obj["Body"].read().decode("utf-8").strip()
        if not text:
            raise PromptResolutionError(
                f"S3 prompt content is empty: {s3_key}"
            )

        logger.info(
            "Resolved prompt '%s' from S3+DDB (version=%s)",
            prompt_id,
            item.get("version", "?"),
        )
        return text

    def _fetch_remote(self, prompt_ref: str) -> str:
        url = f"{self.registry_url.rstrip('/')}/prompts/{prompt_ref}"
        resp = httpx.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
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
