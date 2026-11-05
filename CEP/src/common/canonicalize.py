from __future__ import annotations

import unicodedata


def canonicalize_text(value: object) -> str:
    """Phase-7A v0.2 non-semantic canonicalization only.

    - require a string
    - normalize line endings to LF
    - Unicode NFC
    - trim outer whitespace
    Internal whitespace, punctuation, casing, and wording are preserved.
    """
    if not isinstance(value, str):
        raise TypeError(f"Expected string, got {type(value).__name__}")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", value).strip()
