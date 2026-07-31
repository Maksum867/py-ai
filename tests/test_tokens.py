"""Tests for py_ai.tokens (line and token statistics)."""

import pytest

from py_ai.tokens import count_lines, count_tokens

KNOWN_METHODS = {"cl100k_base (tiktoken)", "heuristic (~4 chars/token)"}


def test_count_lines_basic():
    assert count_lines("") == 0
    assert count_lines("a") == 1
    assert count_lines("a\n") == 1
    assert count_lines("a\nb") == 2
    assert count_lines("a\nb\nc\n") == 3


def test_count_tokens_returns_known_method():
    count, method = count_tokens("def foo(): pass\n" * 50)
    assert isinstance(count, int)
    assert count > 0
    assert method in KNOWN_METHODS


def test_count_tokens_scales_with_size():
    small, _ = count_tokens("x" * 100)
    large, _ = count_tokens("x" * 10000)
    assert large > small


def test_count_tokens_heuristic_fallback(monkeypatch):
    import py_ai.tokens as tokens_module

    monkeypatch.setattr(tokens_module, "_get_tiktoken_encoder", lambda: None)
    count, method = count_tokens("a" * 400)
    assert method == "heuristic (~4 chars/token)"
    assert count == 100


def test_count_tokens_with_tiktoken_if_available():
    pytest.importorskip("tiktoken")
    count, method = count_tokens("hello world")
    assert method == "cl100k_base (tiktoken)"
    assert count == 2  # cl100k_base encodes 'hello world' into 2 tokens
