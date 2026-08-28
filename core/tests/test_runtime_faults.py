"""Pins the LLM failure classifier: it must read the whole __cause__ chain.

Strands wraps a retriable litellm error in an EventLoopException, so classifying
the OUTER exception reported every upstream outage as a permanent `agent_error`
with `retriable: False` — and callers dutifully did not retry. Both QITP lanes
died that way on 2026-08-27.

`litellm` is an optional extra and is absent from the local venv, so the ladder
is exercised against a fake module mirroring the real class hierarchy. The
classifier takes `litellm` as a parameter precisely so this test gates
everywhere, installed or not.
"""

from __future__ import annotations

import types

from agent_core.runtime.handler import _MAX_CAUSE_DEPTH, _cause_chain, _classify_llm_failure


def _fake_litellm() -> types.SimpleNamespace:
    """Mirrors the real MRO: MidStreamFallbackError -> ServiceUnavailableError
    -> APIStatusError -> APIError, verified in a running agent pod."""

    class APIError(Exception):
        def __init__(self, message="", llm_provider=None, status_code=None):
            super().__init__(message)
            self.llm_provider = llm_provider
            self.status_code = status_code

    class APIStatusError(APIError):
        pass

    class ServiceUnavailableError(APIStatusError):
        pass

    class MidStreamFallbackError(ServiceUnavailableError):
        pass

    class BadGatewayError(APIStatusError):
        pass

    class APIConnectionError(APIError):
        pass

    class Timeout(APIError):
        pass

    class RateLimitError(APIError):
        pass

    return types.SimpleNamespace(
        APIError=APIError,
        APIStatusError=APIStatusError,
        ServiceUnavailableError=ServiceUnavailableError,
        MidStreamFallbackError=MidStreamFallbackError,
        BadGatewayError=BadGatewayError,
        APIConnectionError=APIConnectionError,
        Timeout=Timeout,
        RateLimitError=RateLimitError,
    )


def _raise_from(outer: BaseException, inner: BaseException) -> BaseException:
    """Chain `outer` to `inner` the way `raise X from Y` does."""
    outer.__cause__ = inner
    return outer


class TestCauseChain:
    def test_bare_exception(self):
        exc = ValueError("boom")
        assert _cause_chain(exc) == [exc]

    def test_explicit_cause_nest_is_outermost_first(self):
        leaf = OSError("leaf")
        mid = RuntimeError("mid")
        outer = ValueError("outer")
        _raise_from(mid, leaf)
        _raise_from(outer, mid)
        assert _cause_chain(outer) == [outer, mid, leaf]

    def test_context_is_not_followed(self):
        # The whole point of the __cause__-only choice: an unrelated error
        # raised while handling an LLM failure must not inherit its verdict.
        inner = OSError("in flight")
        outer = ValueError("a real bug")
        outer.__context__ = inner
        assert _cause_chain(outer) == [outer]

    def test_depth_cap(self):
        exc = ValueError("0")
        head = exc
        for i in range(_MAX_CAUSE_DEPTH + 10):
            nxt = ValueError(str(i + 1))
            head.__cause__ = nxt
            head = nxt
        assert len(_cause_chain(exc)) == _MAX_CAUSE_DEPTH

    def test_cycle_is_survived(self):
        a = ValueError("a")
        b = ValueError("b")
        a.__cause__ = b
        b.__cause__ = a
        assert _cause_chain(a) == [a, b]

    def test_exception_group_members_included(self):
        member = OSError("inside the group")
        group = BaseExceptionGroup("task group", [member])
        chain = _cause_chain(group)
        assert group in chain
        assert member in chain


class TestClassifyLlmFailure:
    def test_the_2026_08_27_chain(self):
        # EventLoopException -> MidStreamFallbackError -> APIConnectionError
        # -> TransferEncodingError. The regression pin: the outer type is not a
        # litellm class and the LEAF is not either, so only a full walk finds it.
        lite = _fake_litellm()
        leaf = Exception("TransferEncodingError: 400, Not enough data")
        conn = lite.APIConnectionError("payload not completed", llm_provider="openai")
        mid = lite.MidStreamFallbackError("mid stream", llm_provider="openai")
        outer = RuntimeError("EventLoopException")
        _raise_from(conn, leaf)
        _raise_from(mid, conn)
        _raise_from(outer, mid)

        hit = _classify_llm_failure(_cause_chain(outer), lite)
        assert hit == ("upstream_llm_unavailable", 503, "openai", True)

    def test_outer_only_would_have_missed(self):
        lite = _fake_litellm()
        mid = lite.MidStreamFallbackError("mid", llm_provider="openai")
        outer = RuntimeError("EventLoopException")
        _raise_from(outer, mid)
        assert _classify_llm_failure([outer], lite) is None

    def test_leaf_only_would_have_missed(self):
        lite = _fake_litellm()
        leaf = Exception("TransferEncodingError: 400")
        mid = lite.MidStreamFallbackError("mid")
        _raise_from(mid, leaf)
        assert _classify_llm_failure([leaf], lite) is None

    def test_outermost_match_wins(self):
        lite = _fake_litellm()
        inner = lite.APIConnectionError("conn")
        outer = lite.BadGatewayError("gateway", llm_provider="openai")
        _raise_from(outer, inner)
        cls, status, _provider, _retriable = _classify_llm_failure(_cause_chain(outer), lite)
        assert (cls, status) == ("upstream_llm_unavailable", 502)

    def test_attributes_come_from_the_matched_node(self):
        lite = _fake_litellm()
        matched = lite.ServiceUnavailableError("down", llm_provider="anthropic")
        wrapper = RuntimeError("wrapper carries no llm_provider")
        _raise_from(wrapper, matched)
        _cls, _status, provider, _retriable = _classify_llm_failure(_cause_chain(wrapper), lite)
        assert provider == "anthropic"

    def test_timeout(self):
        lite = _fake_litellm()
        assert _classify_llm_failure([lite.Timeout("slow")], lite) == (
            "upstream_llm_timeout", None, None, True,
        )

    def test_rate_limit(self):
        lite = _fake_litellm()
        assert _classify_llm_failure([lite.RateLimitError("429")], lite) == (
            "upstream_llm_rate_limit", 429, None, True,
        )

    def test_connection_error(self):
        lite = _fake_litellm()
        assert _classify_llm_failure([lite.APIConnectionError("refused")], lite) == (
            "upstream_llm_connection_error", None, None, True,
        )

    def test_api_error_retriable_only_on_transient_status(self):
        lite = _fake_litellm()
        for status, expected in ((502, True), (503, True), (429, True), (500, True),
                                 (504, True), (400, False), (404, False), (None, False)):
            hit = _classify_llm_failure(
                [lite.APIError("api", llm_provider="openai", status_code=status)], lite
            )
            assert hit == ("upstream_llm_api_error", status, "openai", expected), status

    def test_non_llm_chain_returns_none(self):
        lite = _fake_litellm()
        leaf = KeyError("symbol")
        outer = ValueError("validation failed")
        _raise_from(outer, leaf)
        assert _classify_llm_failure(_cause_chain(outer), lite) is None
