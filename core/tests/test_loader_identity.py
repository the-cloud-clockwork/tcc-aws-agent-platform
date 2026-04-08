"""Tests for identity wiring in BlueprintLoader.build_agent_session()."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from agent_core.identity.wiring import IdentityWiring


def _write_blueprint(tmp: Path, agent_id: str = "test-agent", identity: dict | None = None) -> Path:
    agents_dir = tmp / "agents"
    agents_dir.mkdir(parents=True)
    bp = {
        "id": agent_id,
        "version": "1",
        "name": "Test Agent",
        "model": {"provider": "bedrock", "model_id": "eu.anthropic.claude-sonnet-4-6", "temperature": 0.5, "max_tokens": 1024},
        "prompt_ref": "test_prompt",
    }
    if identity:
        bp["identity"] = identity
    bp_file = agents_dir / f"{agent_id}.yaml"
    bp_file.write_text(yaml.dump(bp))
    return tmp


class TestLoaderIdentityWiring:
    @patch("agent_core.blueprints.loader.Agent")
    def test_no_identity_produces_none(self, mock_agent_cls: MagicMock) -> None:
        mock_agent_cls.return_value = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp))
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            # Write a dummy prompt file
            (Path(tmp) / "test_prompt.txt").write_text("You are a test agent.")
            with patch.object(loader, "_resolve_prompt", return_value="You are a test agent."):
                with patch.object(loader, "_create_mcp_clients", return_value=[]):
                    session = loader.build_agent_session("test-agent")
                    assert session.identity is None

    @patch("agent_core.blueprints.loader.Agent")
    def test_identity_wiring_created(self, mock_agent_cls: MagicMock) -> None:
        mock_agent_cls.return_value = MagicMock()
        identity = {
            "credentials": [
                {"name": "ext-api", "type": "api_key", "provider": "ext-provider"},
                {
                    "name": "oauth-svc",
                    "type": "oauth2",
                    "provider": "oauth-provider",
                    "auth_flow": "M2M",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            bp_dir = _write_blueprint(Path(tmp), identity=identity)
            from agent_core.blueprints.loader import BlueprintLoader

            loader = BlueprintLoader(bp_dir, prompt_dir=bp_dir)
            with patch.object(loader, "_resolve_prompt", return_value="You are a test agent."):
                with patch.object(loader, "_create_mcp_clients", return_value=[]):
                    session = loader.build_agent_session("test-agent")
                    assert session.identity is not None
                    assert isinstance(session.identity, IdentityWiring)
                    cred_map = session.identity.get_credential_map()
                    assert "ext-api" in cred_map
                    assert "oauth-svc" in cred_map
