from __future__ import annotations

from typing import Any

import pytest

from conductor.tokens import Tokens, no_tokens, total


class TestTokens:
    def test_plus_both_none(self) -> None:
        a = Tokens(input=None, output=None)
        b = Tokens(input=None, output=None)
        result = a.plus(b)
        assert result.input is None
        assert result.output is None

    def test_plus_one_none(self) -> None:
        a = Tokens(input=10, output=None)
        b = Tokens(input=None, output=20)
        result = a.plus(b)
        assert result.input == 10
        assert result.output == 20

    def test_plus_both_values(self) -> None:
        a = Tokens(input=10, output=5, reasoning=3, cache_read=2, cache_write=1)
        b = Tokens(input=20, output=10, reasoning=6, cache_read=4, cache_write=2)
        result = a.plus(b)
        assert result.input == 30
        assert result.output == 15
        assert result.reasoning == 9
        assert result.cache_read == 6
        assert result.cache_write == 3

    def test_to_dict(self) -> None:
        t = Tokens(input=100, output=50, reasoning=10, cache_read=200, cache_write=5)
        d = t.to_dict()
        assert d == {
            "input": 100,
            "output": 50,
            "reasoning": 10,
            "cache_read": 200,
            "cache_write": 5,
        }

    def test_to_dict_with_none(self) -> None:
        t = Tokens(input=100, output=None)
        d = t.to_dict()
        assert d == {
            "input": 100,
            "output": None,
            "reasoning": None,
            "cache_read": None,
            "cache_write": None,
        }

    def test_from_dict_valid(self) -> None:
        data = {"input": 100, "output": 50, "reasoning": 10, "cache_read": 200, "cache_write": 5}
        t = Tokens.from_dict(data)
        assert t.input == 100
        assert t.output == 50
        assert t.reasoning == 10
        assert t.cache_read == 200
        assert t.cache_write == 5

    def test_from_dict_partial(self) -> None:
        data = {"input": 100, "output": "not an int", "cache_read": 200}
        t = Tokens.from_dict(data)
        assert t.input == 100
        assert t.output is None
        assert t.reasoning is None
        assert t.cache_read == 200
        assert t.cache_write is None

    def test_from_dict_non_dict(self) -> None:
        t = Tokens.from_dict("not a dict")
        assert t == Tokens()

    def test_from_dict_bool_is_not_int(self) -> None:
        data = {"input": True, "output": False}
        t = Tokens.from_dict(data)
        assert t.input is None
        assert t.output is None

    def test_cache_share_both_known_positive(self) -> None:
        t = Tokens(input=800, cache_read=200)
        assert t.cache_share == pytest.approx(0.2)

    def test_cache_share_input_none(self) -> None:
        t = Tokens(input=None, cache_read=200)
        assert t.cache_share is None

    def test_cache_share_cache_read_none(self) -> None:
        t = Tokens(input=800, cache_read=None)
        assert t.cache_share is None

    def test_cache_share_zero_sum(self) -> None:
        t = Tokens(input=0, cache_read=0)
        assert t.cache_share is None


class TestTotal:
    def test_total_empty(self) -> None:
        result = total([])
        assert result == Tokens()

    def test_total_single(self) -> None:
        t = Tokens(input=10, output=5)
        result = total([t])
        assert result == t

    def test_total_multiple(self) -> None:
        items = [
            Tokens(input=10, output=5),
            Tokens(input=20, output=10),
            Tokens(input=5, output=2),
        ]
        result = total(items)
        assert result.input == 35
        assert result.output == 17

    def test_total_with_none(self) -> None:
        items = [
            Tokens(input=10, output=None),
            Tokens(input=None, output=20),
            Tokens(input=5, output=5),
        ]
        result = total(items)
        assert result.input == 15
        assert result.output == 25


class TestNoTokens:
    def test_no_tokens_returns_empty(self) -> None:
        events: list[dict[str, Any]] = [{"type": "step_finish", "part": {"tokens": {"input": 10}}}]
        assert no_tokens(events) == Tokens()
