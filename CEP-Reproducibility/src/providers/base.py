from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, Mapping


@dataclass(frozen=True)
class ProviderRequest:
    """Provider-facing request with no TE provenance record."""

    attempt_index: int
    purpose: Literal["initial", "repair"]

    generation_payload: Mapping[str, str]

    prompt_template: str
    raw_schema: Mapping[str, Any]

    previous_raw_response: str | None = None
    validation_errors: tuple[str, ...] = ()


class Provider(ABC):
    """Minimal provider interface for CEP generation."""

    model_id: str

    @abstractmethod
    def generate(
        self,
        request: ProviderRequest,
    ) -> str:
        """Return one raw provider response exactly as text."""
        raise NotImplementedError(
            "Provider subclasses must implement generate()."
        )