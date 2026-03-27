"""One-shot telemetry probe — tests Langfuse SDK connectivity on handler init."""

from __future__ import annotations

import os
import sys


_initialized = False


def _log(msg: str) -> None:
    print(f"[LANGFUSE-PROBE] {msg}", file=sys.stderr, flush=True)


def setup_langfuse_otel() -> None:
    """Probe Langfuse connectivity via SDK on first handler init."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    host = os.environ.get("LANGFUSE_HOST", "")
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
    agent_id = os.environ.get("AGENT_ID", "unknown")

    _log(f"agent={agent_id} host={host} pk={pk[:20] + '...' if pk else 'EMPTY'} sk={'set' if sk else 'EMPTY'}")

    if not host or not pk or not sk:
        _log("Missing env vars — probe skipped")
        return

    try:
        from langfuse import Langfuse
        _log("langfuse import OK")
    except ImportError as e:
        _log(f"langfuse IMPORT FAILED: {e}")
        return

    try:
        lf = Langfuse(public_key=pk, secret_key=sk, host=host)
        trace = lf.trace(name=f"probe:{agent_id}", tags=["probe", "init"])
        trace.generation(name="init-probe", model="probe", usage={"input": 0, "output": 0})
        lf.flush()
        _log("Probe trace sent + flushed OK")
    except Exception as e:
        _log(f"Probe FAILED: {e}")
