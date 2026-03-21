"""Code Interpreter provider — wraps AgentCore Code Interpreter as Strands tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


class CodeInterpreterProvider:
    """Managed provider for the AgentCore Code Interpreter sandbox.

    Wraps ``bedrock_agentcore.tools.code_interpreter_client.CodeInterpreter``
    and exposes its five sandbox operations as Strands ``@tool`` callables.

    Parameters
    ----------
    region:
        AWS region where the Code Interpreter is provisioned.
    network_mode:
        ``"PUBLIC"`` or ``"PRIVATE"`` sandbox networking.
    """

    def __init__(self, *, region: str, network_mode: str = "PUBLIC") -> None:
        from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

        self._region = region
        self._network_mode = network_mode
        self._client = CodeInterpreter(region)
        self._started = False

    def start(self) -> None:
        """Provision the sandbox session."""
        if not self._started:
            self._client.start()
            self._started = True
            logger.info("Code Interpreter started (region=%s)", self._region)

    def stop(self) -> None:
        """Tear down the sandbox session."""
        if self._started:
            try:
                self._client.stop()
            except Exception:
                logger.exception("Error stopping Code Interpreter")
            finally:
                self._started = False

    @property
    def tools(self) -> list[Any]:
        """Return Strands-compatible tool callables for the sandbox."""
        client = self._client

        @tool
        def execute_code(code: str, language: str = "python") -> str:
            """Execute code in the sandboxed Code Interpreter.

            Args:
                code: Source code to execute.
                language: Programming language (default: python).

            Returns:
                JSON string with stdout, stderr, and exit code.
            """
            response = client.invoke(
                "executeCode",
                {"code": code, "language": language, "clearContext": False},
            )
            for event in response.get("stream", [response]):
                if "result" in event:
                    return json.dumps(event["result"])
            return json.dumps({"error": "no result returned"})

        @tool
        def execute_command(command: str) -> str:
            """Execute a shell command in the sandboxed Code Interpreter.

            Args:
                command: Shell command to run.

            Returns:
                JSON string with stdout, stderr, and exit code.
            """
            response = client.invoke("executeCommand", {"command": command})
            for event in response.get("stream", [response]):
                if "result" in event:
                    return json.dumps(event["result"])
            return json.dumps({"error": "no result returned"})

        @tool
        def write_files(files: list[dict]) -> str:
            """Write files into the Code Interpreter sandbox.

            Args:
                files: List of dicts with 'path' and 'text' keys.

            Returns:
                JSON confirmation of written files.
            """
            response = client.invoke("writeFiles", {"content": files})
            return json.dumps(response)

        @tool
        def list_files() -> str:
            """List files available in the Code Interpreter sandbox.

            Returns:
                JSON list of file paths.
            """
            response = client.invoke("listFiles", {})
            return json.dumps(response)

        @tool
        def read_file(path: str) -> str:
            """Read a file from the Code Interpreter sandbox.

            Args:
                path: File path within the sandbox.

            Returns:
                File contents as a string.
            """
            response = client.invoke("readFile", {"path": path})
            return json.dumps(response)

        return [execute_code, execute_command, write_files, list_files, read_file]
