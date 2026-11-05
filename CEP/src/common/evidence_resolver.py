from __future__ import annotations

from collections.abc import Mapping
from typing import Any


VALID_SOURCE_FIELDS = ("title", "description")

RESOLVED = "resolved"
ZERO_MATCH = "zero_match"
MULTIPLE_MATCH = "multiple_match"


def _exact_occurrence_starts(
    source_text: str,
    exact_text: str,
) -> list[int]:
    """Return all exact substring start positions, including overlaps."""
    starts: list[int] = []
    search_from = 0

    while True:
        index = source_text.find(exact_text, search_from)

        if index == -1:
            return starts

        starts.append(index)

        # Advance by one character so overlapping exact matches
        # are also detected deterministically.
        search_from = index + 1


def resolve_evidence(
    evidence: Mapping[str, Any],
    *,
    title: str,
    description: str,
) -> dict[str, Any]:
    """Resolve one raw model evidence object against canonical inputs.

    Matching is exact, contiguous, case-sensitive, and restricted to
    the declared source field.

    No canonicalization, fuzzy matching, semantic repair, rewriting,
    inference, or cross-field fallback is performed.

    Offsets use Python string indexing with a half-open interval:
    [char_start, char_end)

    char_start is inclusive.
    char_end is exclusive.
    """
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")

    if not isinstance(title, str):
        raise TypeError("title must be a string")

    if not isinstance(description, str):
        raise TypeError("description must be a string")

    source_field = evidence.get("source_field")

    if source_field not in VALID_SOURCE_FIELDS:
        raise ValueError(
            "source_field must be exactly one of: title, description"
        )

    exact_text = evidence.get("exact_text")

    if not isinstance(exact_text, str):
        raise TypeError("exact_text must be a string")

    if exact_text == "":
        raise ValueError("exact_text must not be empty")

    source_text = (
        title
        if source_field == "title"
        else description
    )

    starts = _exact_occurrence_starts(
        source_text,
        exact_text,
    )

    occurrence_count = len(starts)

    if occurrence_count == 1:
        char_start = starts[0]
        char_end = char_start + len(exact_text)
        resolution_status = RESOLVED

    elif occurrence_count == 0:
        char_start = None
        char_end = None
        resolution_status = ZERO_MATCH

    else:
        char_start = None
        char_end = None
        resolution_status = MULTIPLE_MATCH

    return {
        "evidence_id": evidence.get("evidence_id"),
        "source_field": source_field,
        "exact_text": exact_text,
        "resolution_status": resolution_status,
        "occurrence_count": occurrence_count,
        "char_start": char_start,
        "char_end": char_end,
    }