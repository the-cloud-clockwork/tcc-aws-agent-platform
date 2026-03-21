"""NL2Cedar — convenience wrapper for natural-language policy generation.

Thin layer over ``PolicyClient.generate_policy()`` that extracts the
Cedar statement from the API response into a clean dataclass.
The actual NL-to-Cedar generation is performed server-side by the
AgentCore Policy API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_core.policy.client import PolicyClient, PolicyError


@dataclass(frozen=True)
class NL2CedarResult:
    """Result of a natural-language-to-Cedar policy generation."""

    name: str
    cedar_statement: str
    raw_response: dict[str, Any]


def generate_from_natural_language(
    client: PolicyClient,
    engine_id: str,
    gateway_arn: str,
    name: str,
    description: str,
    fetch_assets: bool = True,
) -> NL2CedarResult:
    """Generate a Cedar policy from a natural language description.

    Args:
        client: Initialized PolicyClient.
        engine_id: Target policy engine ID.
        gateway_arn: Gateway ARN for resource context.
        name: Name for the generated policy.
        description: Plain English policy description.
        fetch_assets: Whether to fetch gateway target schemas for context.

    Returns:
        A ``NL2CedarResult`` containing the generated Cedar statement.

    Raises:
        PolicyError: If generation fails or the response is malformed.
    """
    result = client.generate_policy(
        engine_id=engine_id,
        name=name,
        gateway_arn=gateway_arn,
        natural_language=description,
        fetch_assets=fetch_assets,
    )

    generated = result.get("generatedPolicies", [])
    if not generated:
        raise PolicyError(
            message=f"NL2Cedar returned no policies for '{name}'.",
            code="NL2CEDAR_EMPTY",
        )

    cedar_statement = (
        generated[0].get("definition", {}).get("cedar", {}).get("statement", "")
    )
    if not cedar_statement:
        raise PolicyError(
            message=f"NL2Cedar returned empty Cedar for '{name}'.",
            code="NL2CEDAR_EMPTY_STATEMENT",
        )

    return NL2CedarResult(
        name=name,
        cedar_statement=cedar_statement,
        raw_response=result,
    )
