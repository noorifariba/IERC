from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.adapters.airbnb import adapt_airbnb
from src.adapters.booking import adapt_booking
from src.adapters.tripadvisor import adapt_tripadvisor


def adapt_record(dataset_root: Path, record: Mapping[str, Any]):
    platform = record["platform"]
    if platform == "Airbnb":
        return adapt_airbnb(dataset_root, record)
    if platform == "TripAdvisor":
        return adapt_tripadvisor(dataset_root, record)
    if platform == "Booking.com":
        return adapt_booking(dataset_root, record)
    raise ValueError(f"Unsupported platform: {platform}")
