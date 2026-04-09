"""Data protection layer — Bedrock Guardrails PII anonymization + CloudWatch masking.

Two layers of defense:
  Layer 1: Bedrock Guardrails anonymize PII in model responses before
           they reach the trace or the user.
  Layer 2: CloudWatch Data Protection masks PII patterns (SSN, credit
           cards, etc.) in log streams at rest, so even if PII leaks
           into a trace it is masked in storage.
"""

from __future__ import annotations

import collections.abc
import json
import logging
import os

import boto3

from agent_core.schemas.observability_config import DataProtectionConfig

logger = logging.getLogger(__name__)


def build_guardrail_model_kwargs(config: DataProtectionConfig) -> dict[str, str]:
    """Build kwargs to pass to ``BedrockModel()`` for guardrail integration.

    Reads the guardrail ID and version from environment variables
    named in *config*. Returns an empty dict when the env vars are
    absent — non-Bedrock providers and unconfigured Bedrock agents
    both get a clean no-op instead of a crash.

    Returns a dict suitable for ``BedrockModel(**kwargs)``::

        {"guardrail_id": "...", "guardrail_version": "...", "guardrail_trace": "enabled"}
    """
    guardrail_id = os.environ.get(config.guardrail_id_env)
    if not guardrail_id:
        return {}
    guardrail_version = os.environ.get(config.guardrail_version_env, "")
    if not guardrail_version:
        return {}
    return {
        "guardrail_id": guardrail_id,
        "guardrail_version": guardrail_version,
        "guardrail_trace": "enabled",
    }


def build_data_protection_policy(
    config: DataProtectionConfig,
    log_group: str,
) -> dict:
    """Build a CloudWatch Data Protection policy document.

    The policy masks the PII identifiers declared in
    ``config.cloudwatch_masking_identifiers`` within the specified
    log group.

    See: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data.html

    Args:
        config: Data protection configuration from the blueprint.
        log_group: Target CloudWatch log group name.
    """
    if not config.cloudwatch_masking_identifiers:
        return {}

    data_identifiers = [
        f"arn:aws:dataprotection::aws:data-identifier/{ident}"
        for ident in config.cloudwatch_masking_identifiers
    ]

    return {
        "Name": "data-protection-policy",
        "Description": f"PII masking for {log_group}",
        "Version": "2021-06-01",
        "Statement": [
            {
                "Sid": "audit-policy",
                "DataIdentifier": data_identifiers,
                "Operation": {
                    "Audit": {
                        "FindingsDestination": {},
                    },
                },
            },
            {
                "Sid": "redact-policy",
                "DataIdentifier": data_identifiers,
                "Operation": {
                    "Deidentify": {
                        "MaskConfig": {},
                    },
                },
            },
        ],
    }


def apply_log_data_protection(
    config: DataProtectionConfig,
    log_group: str,
    *,
    region: str | None = None,
) -> None:
    """Apply a data protection policy to a CloudWatch log group.

    Creates the log group if it does not exist, then applies the
    data protection policy for the configured PII identifiers.

    Args:
        config: Data protection configuration from the blueprint.
        log_group: Target CloudWatch log group name.
        region: AWS region (resolved from env if not provided).
    """
    if not config.cloudwatch_masking_identifiers:
        logger.debug("No masking identifiers configured, skipping data protection.")
        return

    policy = build_data_protection_policy(config, log_group)
    if not policy:
        return

    client = boto3.client("logs", region_name=region)

    try:
        client.create_log_group(logGroupName=log_group)
        logger.info("Created log group %s", log_group)
    except client.exceptions.ResourceAlreadyExistsException:
        pass

    client.put_data_protection_policy(
        logGroupIdentifier=log_group,
        policyDocument=json.dumps(policy),
    )
    logger.info(
        "Applied data protection policy to %s (identifiers: %s)",
        log_group,
        config.cloudwatch_masking_identifiers,
    )


def sanitize_text(
    text: str,
    config: DataProtectionConfig,
    *,
    region: str | None = None,
    source: str = "INPUT",
) -> str:
    """Anonymize PII in text using Bedrock Guardrails.

    Applies the guardrail configured in *config* to strip or mask PII
    before the text is sent to external observability backends (e.g. Langfuse).

    Args:
        text: Raw text to sanitize.
        config: Data protection configuration with guardrail IDs.
        region: AWS region (resolved from env if not provided).
        source: Guardrail content source — ``"INPUT"`` or ``"OUTPUT"``.

    Returns:
        Sanitized text with PII anonymized.  Returns original text
        unchanged if the guardrail is not configured or the API fails.
    """
    guardrail_id = os.environ.get(config.guardrail_id_env)
    if not guardrail_id:
        return text

    guardrail_version = os.environ[config.guardrail_version_env]
    resolved_region = (
        region or os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
    )

    try:
        client = boto3.client("bedrock-runtime", region_name=resolved_region)
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,
            source=source,
            content=[{"text": {"text": text}}],
        )
        outputs = response.get("outputs", [])
        if outputs:
            return outputs[0].get("text", text)
        return text
    except Exception:
        logger.exception("Guardrail PII sanitization failed, returning original text")
        return text


def build_pii_filter(
    config: DataProtectionConfig,
    *,
    region: str | None = None,
) -> collections.abc.Callable[[str], str]:
    """Create a PII filter callable for use with ``LangfuseHook``.

    Returns a function that takes a string and returns the sanitized version.
    If the guardrail is not configured, returns a no-op passthrough.

    Args:
        config: Data protection configuration.
        region: AWS region override.
    """
    guardrail_id = os.environ.get(config.guardrail_id_env)
    if not guardrail_id:

        def _passthrough(text: str) -> str:
            return text

        return _passthrough

    def _filter(text: str) -> str:
        return sanitize_text(text, config, region=region)

    return _filter
