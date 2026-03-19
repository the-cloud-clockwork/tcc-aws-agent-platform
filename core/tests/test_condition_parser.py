"""Tests for condition_parser."""
from __future__ import annotations

import pytest

from agent_core.blueprints.condition_parser import _coerce_value, _resolve_attr, parse_condition


class TestCoerceValue:
    def test_bool_true(self):
        assert _coerce_value("true") is True

    def test_bool_false(self):
        assert _coerce_value("false") is False

    def test_none(self):
        assert _coerce_value("none") is None

    def test_int(self):
        assert _coerce_value("42") == 42

    def test_float(self):
        assert _coerce_value("0.7") == 0.7

    def test_quoted_string(self):
        assert _coerce_value('"hello"') == "hello"

    def test_bare_string(self):
        assert _coerce_value("success") == "success"


class TestResolveAttr:
    def test_dict_key(self):
        assert _resolve_attr({"status": "ok"}, "status") == "ok"

    def test_nested_dict(self):
        assert _resolve_attr({"a": {"b": "c"}}, "a.b") == "c"

    def test_object_attr(self):
        class Obj:
            x = 5
        assert _resolve_attr(Obj(), "x") == 5

    def test_missing(self):
        assert _resolve_attr({"a": 1}, "b") is None


class TestParseCondition:
    def test_eq_string(self):
        fn = parse_condition("status == success")
        assert fn({"status": "success"}) is True
        assert fn({"status": "fail"}) is False

    def test_gte_float(self):
        fn = parse_condition("score >= 0.7")
        assert fn({"score": 0.8}) is True
        assert fn({"score": 0.5}) is False

    def test_eq_bool(self):
        fn = parse_condition("result.matched == true")
        assert fn({"result": {"matched": True}}) is True

    def test_neq(self):
        fn = parse_condition("status != closed")
        assert fn({"status": "open"}) is True

    def test_lt(self):
        fn = parse_condition("risk < 5")
        assert fn({"risk": 3}) is True
        assert fn({"risk": 7}) is False

    def test_missing_field_returns_false(self):
        fn = parse_condition("missing == value")
        assert fn({"other": "data"}) is False

    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="Unknown operator"):
            parse_condition("x ~= 5")

    def test_malformed_expression_raises(self):
        with pytest.raises(ValueError, match="tokens"):
            parse_condition("just_one_word")

    def test_named_operators(self):
        fn = parse_condition("count gt 10")
        assert fn({"count": 15}) is True
        assert fn({"count": 5}) is False
