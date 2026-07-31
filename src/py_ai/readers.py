"""
readers.py module
=================
Robust reading of project files for the py-ai utility:

- BOM-aware decoding (UTF-32 / UTF-16 / UTF-8-SIG).
- Binary detection via NUL-byte heuristics.
- Encoding fallback chain: UTF-8 -> cp1251 -> latin-1.
"""

from __future__ import annotations

import codecs
from pathlib import Path

# How many leading bytes are inspected for NUL bytes when deciding whether
# a file is binary (a similar heuristic to the one git uses).
BINARY_CHECK_BYTES = 8192

# Encodings tried, in order, when a file is not UTF-8.
ENCODING_FALLBACK_CHAIN = ("utf-8", "utf-8-sig", "cp1251", "latin-1")

# BOM -> encoding mapping. NB: UTF-32 BOMs share their prefix with UTF-16
# BOMs, so UTF-32 must be checked first.
_BOM_ENCODINGS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
    (codecs.BOM_UTF8, "utf-8-sig"),
)


def looks_binary(raw: bytes, check_bytes: int = BINARY_CHECK_BYTES) -> bool:
    """
    Binary heuristic: text files never contain NUL bytes.
    Only the beginning of the file is inspected for speed.

    :param raw: Raw file bytes.
    :param check_bytes: How many leading bytes to inspect.
    :return: True if the content looks binary.
    """
    return b"\x00" in raw[:check_bytes]


def read_text_content(file_path: Path) -> tuple[str | None, str | None]:
    """
    Reads a file and returns its text content, handling encodings gracefully.

    Detection strategy:
    1. BOM-aware decoding for UTF-32 / UTF-16 / UTF-8-SIG files.
    2. Files containing NUL bytes (in the first chunk) are treated as binary.
    3. Otherwise the encoding fallback chain is tried:
       UTF-8 -> UTF-8-SIG -> cp1251 -> latin-1 (the latter never fails).

    :param file_path: Path to the file to read.
    :return: Tuple (content, None) on success or (None, reason) on failure.
    """
    try:
        raw = Path(file_path).read_bytes()
    except PermissionError:
        return None, "permission denied"
    except OSError as e:
        return None, f"read error: {e}"

    for bom, encoding in _BOM_ENCODINGS:
        if raw.startswith(bom):
            try:
                return raw.decode(encoding), None
            except UnicodeDecodeError:
                return None, "encoding error (invalid BOM-marked content)"

    if looks_binary(raw):
        return None, "binary file"

    for encoding in ENCODING_FALLBACK_CHAIN:
        try:
            return raw.decode(encoding), None
        except UnicodeDecodeError:
            continue

    return None, "encoding error"
