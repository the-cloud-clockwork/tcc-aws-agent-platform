"""Tests for agent_core.blueprints.loader._expand_env_template."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestExpandEnvTemplate:
    """The model_id env-template expansion shared by the Strands model and
    the StructuredOutputEnforcer. A raw ${...} template reaching the
    enforcer 400s every instructor call (silent structured-output loss)."""

    def test_default_used_when_env_absent(self) -> None:
        from agent_core.blueprints.loader import _expand_env_template

        with patch.dict(os.environ, {}, clear=True):
            assert (
                _expand_env_template("${AGENT_MODEL_ID:-gemini-3.1-pro}")
                == "gemini-3.1-pro"
            )

    def test_env_value_overrides_default(self) -> None:
        from agent_core.blueprints.loader import _expand_env_template

        with patch.dict(os.environ, {"AGENT_MODEL_ID": "claude-max-opus"}):
            assert (
                _expand_env_template("${AGENT_MODEL_ID:-gemini-3.1-pro}")
                == "claude-max-opus"
            )

    def test_plain_string_unchanged(self) -> None:
        from agent_core.blueprints.loader import _expand_env_template

        assert _expand_env_template("claude-max-opus") == "claude-max-opus"

    def test_bare_var_without_default_expands(self) -> None:
        from agent_core.blueprints.loader import _expand_env_template

        with patch.dict(os.environ, {"MODEL_X": "sonnet-4-6"}):
            assert _expand_env_template("${MODEL_X}") == "sonnet-4-6"

    def test_bare_var_missing_keeps_literal(self) -> None:
        """A ${VAR} with no default and no env value is left as-is rather than
        collapsing to empty — surfaces the misconfiguration instead of hiding it."""
        from agent_core.blueprints.loader import _expand_env_template

        with patch.dict(os.environ, {}, clear=True):
            assert _expand_env_template("${UNSET_VAR}") == "${UNSET_VAR}"
