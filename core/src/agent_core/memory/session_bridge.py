"""Session bridge: maps SFN execution IDs to AgentCore session IDs.

From CLAUDE.md:
  "Session IDs map to SFN execution IDs — AgentCore Memory uses the same
   session_id convention."

SFN execution IDs have the format:
  arn:aws:states:{region}:{account}:execution:{prefix}-{env}-workflow:exec-abc123

We extract the execution name (after the last colon) as the session ID.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Pattern for SFN execution ARN
SFN_EXECUTION_ARN_PATTERN = re.compile(
    r"^arn:aws:states:[a-z0-9-]+:\d{12}:execution:[^:]+:(.+)$"
)


def sfn_execution_id_to_session_id(execution_id: str) -> str:
    """Convert an SFN execution ID or ARN to a session ID.

    If the input is a full ARN, extracts the execution name.
    If the input is already a plain ID, returns it as-is.

    Args:
        execution_id: SFN execution ARN or plain execution name.

    Returns:
        Session ID string.

    Examples:
        >>> sfn_execution_id_to_session_id(
        ...     "arn:aws:states:eu-west-1:123456789012:execution:my-dev-workflow:exec-abc123"
        ... )
        'exec-abc123'
        >>> sfn_execution_id_to_session_id("exec-abc123")
        'exec-abc123'
    """
    match = SFN_EXECUTION_ARN_PATTERN.match(execution_id)
    if match:
        session_id = match.group(1)
        logger.debug("Extracted session ID '%s' from ARN", session_id)
        return session_id
    return execution_id


def session_id_to_sfn_execution_arn(
    session_id: str,
    state_machine_name: str,
    region: str = "",
    account_id: str = "",
) -> str:
    """Reconstruct an SFN execution ARN from a session ID.

    Args:
        session_id: Session ID (execution name).
        state_machine_name: SFN state machine name.
        region: AWS region.
        account_id: AWS account ID.

    Returns:
        Full SFN execution ARN.
    """
    region = region or os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or ""
    if not region:
        raise ValueError(
            "No AWS region configured.  Pass region= or export AWS_DEFAULT_REGION."
        )
    account_id = account_id or os.getenv("AWS_ACCOUNT_ID", "")
    return (
        f"arn:aws:states:{region}:{account_id}:"
        f"execution:{state_machine_name}:{session_id}"
    )


def extract_session_metadata(execution_input: dict[str, Any]) -> dict[str, str]:
    """Extract session metadata from SFN execution input.

    SFN passes execution context including the execution ID, state machine name,
    and execution start time. This function normalizes these into session metadata.

    Args:
        execution_input: SFN execution input or task input.

    Returns:
        Dict with session_id, state_machine, start_time.
    """
    # SFN injects these via Context Object in task input
    sfn_context = execution_input.get("_sfn_context", {})

    execution_arn = sfn_context.get("Execution", {}).get("Id", "")
    state_machine_arn = sfn_context.get("StateMachine", {}).get("Id", "")
    start_time = sfn_context.get("Execution", {}).get("StartTime", "")

    session_id = (
        sfn_execution_id_to_session_id(execution_arn)
        if execution_arn
        else execution_input.get("session_id", "unknown")
    )

    return {
        "session_id": session_id,
        "execution_arn": execution_arn,
        "state_machine_arn": state_machine_arn,
        "start_time": start_time,
    }
