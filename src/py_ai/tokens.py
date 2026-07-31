"""
tokens.py module
================
Token and line statistics for the generated context pack.

Token counting uses 'tiktoken' (cl100k_base) when the optional dependency is
installed (pip install py-for-ai[tokens]) and falls back to the widely used
heuristic of ~4 characters per token otherwise.
"""

from __future__ import annotations

# Roughly how many characters form one token in code/prose for
# heuristic estimation when tiktoken is not available.
CHARS_PER_TOKEN_HEURISTIC = 4.0

_TIKTOKEN_ENCODING_NAME = "cl100k_base"
_cached_encoder = None
_tiktoken_unavailable = False


def _get_tiktoken_encoder():
    """
    Returns a cached tiktoken encoder, or None if tiktoken is not installed
    or cannot be initialized.
    """
    global _cached_encoder, _tiktoken_unavailable

    if _cached_encoder is not None:
        return _cached_encoder
    if _tiktoken_unavailable:
        return None

    try:
        import tiktoken
        _cached_encoder = tiktoken.get_encoding(_TIKTOKEN_ENCODING_NAME)
        return _cached_encoder
    except Exception:
        # ImportError, or runtime failure fetching the BPE ranks offline.
        _tiktoken_unavailable = True
        return None


def count_tokens(text: str) -> tuple[int, str]:
    """
    Counts (or estimates) the number of tokens in the text.

    :param text: Text to measure.
    :return: Tuple (token_count, method) where method is either
             'cl100k_base (tiktoken)' or 'heuristic (~4 chars/token)'.
    """
    encoder = _get_tiktoken_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text)), f"{_TIKTOKEN_ENCODING_NAME} (tiktoken)"
        except Exception:
            # Fall through to the heuristic on any unexpected encoder issue.
            pass

    estimated = int(len(text) / CHARS_PER_TOKEN_HEURISTIC + 0.5)
    return estimated, "heuristic (~4 chars/token)"


def count_lines(text: str) -> int:
    """
    Counts the number of lines in the text.
    A final line without a trailing newline counts as a line as well.
    """
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)
