"""YAML-to-Cedar translation for AgentCore policy rules.

Converts simplified ``PolicyRuleConfig`` objects from blueprint YAML into
valid Cedar policy statements compatible with the AgentCore Policy Engine.

The generated Cedar uses AgentCore entity types:
- ``AgentCore::Action::"{target}___{tool}"`` for actions
- ``AgentCore::Gateway::"{arn}"`` for resources
- ``AgentCore::Principal::"{id}"`` for specific principals
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_core.schemas.policy_config import PolicyRuleConfig


class CedarTranslationError(Exception):
    """Raised when a policy rule cannot be translated to valid Cedar."""


def translate_rule(
    rule: PolicyRuleConfig,
    gateway_arn: str,
    target_prefix: str | None = None,
) -> str:
    """Translate a single ``PolicyRuleConfig`` into a Cedar statement.

    Args:
        rule: The simplified rule from blueprint YAML.
        gateway_arn: The Gateway ARN for the resource clause.
        target_prefix: Optional target prefix for action names.
            When set, the action becomes ``{prefix}___{tool_name}``.

    Returns:
        A complete Cedar policy statement string.

    Raises:
        CedarTranslationError: If the rule is malformed.
    """
    if rule.allow:
        effect = "permit"
        tool_name = rule.allow
    elif rule.deny:
        effect = "forbid"
        tool_name = rule.deny
    else:
        msg = f"Rule '{rule.name}': one of 'allow' or 'deny' is required."
        raise CedarTranslationError(msg)

    if target_prefix:
        action_str = f"{target_prefix}___{tool_name}"
    else:
        action_str = tool_name

    principal_clause = rule.principal if rule.principal else "principal"

    action_clause = f'action == AgentCore::Action::"{action_str}"'
    resource_clause = f'resource == AgentCore::Gateway::"{gateway_arn}"'

    statement = (
        f"{effect}({principal_clause},\n  {action_clause},\n  {resource_clause})"
    )

    if rule.when:
        statement += f"\nwhen {{ {rule.when} }}"

    if rule.unless:
        statement += f"\nunless {{ {rule.unless} }}"

    statement += ";"

    return statement


def translate_rules(
    rules: list[PolicyRuleConfig],
    gateway_arn: str,
    target_prefix: str | None = None,
) -> str:
    """Translate a list of policy rules into a Cedar policy set.

    Each rule is prefixed with a ``// {rule.name}`` comment line.

    Args:
        rules: List of simplified rules from blueprint YAML.
        gateway_arn: The Gateway ARN for resource clauses.
        target_prefix: Optional target prefix for action names.

    Returns:
        A string containing all Cedar statements joined by double newlines.
        Empty string if no rules are provided.
    """
    if not rules:
        return ""

    statements: list[str] = []
    for rule in rules:
        cedar = translate_rule(rule, gateway_arn, target_prefix)
        statements.append(f"// {rule.name}\n{cedar}")

    return "\n\n".join(statements)


def validate_cedar_expression(expr: str) -> list[str]:
    """Basic structural validation of a Cedar condition expression.

    Checks for balanced delimiters and obvious structural issues.
    This is NOT a full Cedar parser — it catches common mistakes only.

    Args:
        expr: A Cedar expression string to validate.

    Returns:
        A list of error messages. Empty list means no errors detected.
    """
    errors: list[str] = []

    brace_depth = 0
    paren_depth = 0
    for char in expr:
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1

        if brace_depth < 0:
            errors.append("Unbalanced braces: unexpected '}'.")
            break
        if paren_depth < 0:
            errors.append("Unbalanced parentheses: unexpected ')'.")
            break

    if brace_depth > 0:
        errors.append(f"Unbalanced braces: {brace_depth} unclosed '{{'.")
    if paren_depth > 0:
        errors.append(f"Unbalanced parentheses: {paren_depth} unclosed '('.")

    if not expr.strip():
        errors.append("Expression is empty.")

    return errors
