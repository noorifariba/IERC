from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.adapters.base import build_canonical_te
from src.common.canonicalize import canonicalize_text
from src.common.io import load_json

ADAPTER_VERSION = "adapters_v0.2"

def find_booking_experience(root: Path, filename: str) -> Path:
    matches = [
        p for p in root.rglob(filename)
        if p.is_file()
        and any(part.casefold() == "experiences" for part in p.parts)
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one Booking experience file {filename!r}, "
            f"found {len(matches)}: {matches}"
        )

    return matches[0]

def adapt_booking(root: Path, record: Mapping[str, Any]):
    product_id = str(record["selector"])
    experience_path = find_booking_experience(
        root,
        record["experience_filename"]
    )
    detail = load_json(experience_path)
    if detail.get("id") != product_id:
        raise ValueError(f"Booking product ID mismatch: manifest={product_id}, file id={detail.get('id')} at {experience_path}")

    title = canonicalize_text(detail["name"])
    description = canonicalize_text(detail["description"])

    provenance = {
        "te_id": record["te_id"],
        "platform": "Booking.com",
        "dataset_destination": record["dataset_destination"],
        "source_selector": product_id,
        "url": detail.get("url"),
        # Phase 5/6: Booking itinerary.type / addresses are not verified structured stop lists.
        "itinerary_status": "no_verified_structured_itinerary",
        "input_status": "complete" if title and description else "partial",
        "input_fields_used": ["title", "description"],
        "detail_source_path": str(experience_path),
        "canonical_title_source": "experience.name",
        "canonical_description_source": "experience.description",
        "adapter_version": ADAPTER_VERSION,
    }
    return build_canonical_te(title=title, description=description, provenance=provenance)
