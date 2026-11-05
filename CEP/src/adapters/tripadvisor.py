from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.adapters.base import build_canonical_te, find_index_detail, find_unique
from src.common.canonicalize import canonicalize_text
from src.common.io import load_json

ADAPTER_VERSION = "adapters_v0.2"


def adapt_tripadvisor(root: Path, record: Mapping[str, Any]):
    index = int(record["selector"])
    list_path = find_unique(root, record["list_filename"])
    rows = load_json(list_path)
    if not isinstance(rows, list):
        raise ValueError(f"TripAdvisor list file is not a JSON array: {list_path}")
    if not 0 <= index < len(rows):
        raise IndexError(f"TripAdvisor index {index} out of range for {list_path} ({len(rows)} entries)")
    list_row = rows[index]
    detail_path = find_index_detail(list_path, str(record["dataset_destination"]), index)
    detail = load_json(detail_path)

    # Phase-5 mapping: title is present in detail as `title`; description is detail `description`.
    title = canonicalize_text(detail["title"])
    description = canonicalize_text(detail["description"])
    place_list = detail.get("placeList")
    if isinstance(place_list, list):
        itinerary_status = "verified_structured_nonempty" if len(place_list) > 0 else "verified_structured_empty"
    else:
        itinerary_status = "no_verified_structured_itinerary"

    provenance = {
        "te_id": record["te_id"],
        "platform": "TripAdvisor",
        "dataset_destination": record["dataset_destination"],
        "source_selector": index,
        "url": detail.get("url") or list_row.get("url"),
        "itinerary_status": itinerary_status,
        "input_status": "complete" if title and description else "partial",
        "input_fields_used": ["title", "description"],
        "list_source_path": str(list_path),
        "detail_source_path": str(detail_path),
        "canonical_title_source": "detail.title",
        "canonical_description_source": "detail.description",
        "adapter_version": ADAPTER_VERSION,
    }
    return build_canonical_te(title=title, description=description, provenance=provenance)
