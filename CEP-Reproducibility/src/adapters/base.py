from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping

from src.common.hashing import sha256_json, sha256_text


@dataclass(frozen=True)
class CanonicalTE:
    generation_input: Mapping[str, str]
    hidden_provenance: Mapping[str, Any]
    input_hashes: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_te(*, title: str, description: str, provenance: Mapping[str, Any]) -> CanonicalTE:
    generation_input = {"title": title, "description": description}
    hashes = {
        "title_sha256": sha256_text(title),
        "description_sha256": sha256_text(description),
        "generation_input_sha256": sha256_json(generation_input),
    }
    return CanonicalTE(generation_input=generation_input, hidden_provenance=dict(provenance), input_hashes=hashes)


class SourceResolutionError(RuntimeError):
    pass


def find_unique(root: Path, filename: str) -> Path:
    matches = [p for p in root.rglob(filename) if p.is_file()]
    if len(matches) != 1:
        raise SourceResolutionError(f"Expected exactly one {filename!r} under {root}, found {len(matches)}: {matches[:10]}")
    return matches[0]


def find_index_detail(list_path: Path, destination: str, index: int) -> Path:
    target = f"{index}.json"
    candidates = [p for p in list_path.parent.rglob(target) if p.is_file()]
    # Prefer a parent/grandparent whose name matches the destination.
    preferred = []
    d = destination.casefold()
    for p in candidates:
        parent_names = {p.parent.name.casefold(), p.parent.parent.name.casefold() if p.parent.parent else ""}
        if d in parent_names:
            preferred.append(p)
    pool = preferred or candidates
    if len(pool) != 1:
        raise SourceResolutionError(
            f"Could not uniquely resolve detail {target} for destination={destination!r} near {list_path}; "
            f"candidates={pool[:20]}"
        )
    return pool[0]
