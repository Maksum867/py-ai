"""
stripping.py module
===================
Optional source slimming for the py-ai utility (--strip-docs).

Removes comments and docstrings from Python source so the packed context
becomes smaller. The transformation is AST-based and fails safe: any file
that cannot be parsed (syntax error, exotic syntax) is returned unchanged —
packing must never break because of stripping.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize

_DOCSTRING_NODES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _collect_and_remove_docstrings(tree) -> list:
    """
    Removes module/class/function docstrings from the AST in place.

    :param tree: Parsed AST.
    :return: List of (lineno, end_lineno) spans of the removed docstrings
             (used by the Python 3.8 fallback, which cannot ast.unparse).
    """
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, _DOCSTRING_NODES):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                end = getattr(body[0], "end_lineno", None) or body[0].lineno
                spans.append((body[0].lineno, end))
                # An empty def/class/module still needs a statement.
                node.body = body[1:] if len(body) > 1 else [ast.Pass()]
    return spans


def _fallback_strip(source: str, docstring_spans) -> str:
    """Python 3.8 path (no ast.unparse): blank out docstring lines and
    comments via tokenize, then collapse runs of blank lines."""
    out_lines = source.splitlines()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok_ in tokens:
            if tok_.type == tokenize.COMMENT:
                line_no = tok_.start[0]
                line = out_lines[line_no - 1]
                out_lines[line_no - 1] = line[:tok_.start[1]].rstrip()
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source

    for start, end in docstring_spans:
        for line_no in range(start, min(end, len(out_lines)) + 1):
            out_lines[line_no - 1] = ""

    cleaned = []
    blank = False
    for line in out_lines:
        if not line.strip():
            if blank:
                continue
            blank = True
            cleaned.append("")
        else:
            blank = False
            cleaned.append(line)
    return "\n".join(cleaned).rstrip("\n") + "\n"


def strip_python_docs(source: str) -> str:
    """
    Returns Python source without comments and docstrings.

    - Comments are removed (AST round-trip on Python >= 3.9, tokenize-based
      blanking on 3.8).
    - Module/class/function docstrings are removed; a def/class left empty
      gets a ``pass`` so the code stays syntactically valid.
    - Regular string literals (including ones containing '#') are preserved.
    - Files that fail to parse are returned unchanged.
    """
    if not source.strip():
        return source
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return source

    docstring_spans = _collect_and_remove_docstrings(tree)

    if sys.version_info >= (3, 9):
        try:
            return ast.unparse(tree) + "\n"
        except Exception:
            pass

    return _fallback_strip(source, docstring_spans)
