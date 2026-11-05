from __future__ import annotations

from collections.abc import Sequence

from src.providers.base import (
    Provider,
    ProviderRequest,
)


class MockProvider(Provider):
    """Deterministic scripted provider used only for CP5."""

    def __init__(
        self,
        responses: Sequence[str],
        *,
        model_id: str = "mock-provider-v1",
    ) -> None:
        self.model_id = model_id

        self._responses = list(
            responses
        )

        self.calls: list[
            ProviderRequest
        ] = []

    @property
    def call_count(self) -> int:
        return len(
            self.calls
        )

    def generate(
        self,
        request: ProviderRequest,
    ) -> str:
        self.calls.append(
            request
        )

        response_index = (
            len(self.calls) - 1
        )

        if (
            response_index
            >= len(self._responses)
        ):
            raise RuntimeError(
                "MockProvider has no scripted response for "
                f"call {response_index + 1}"
            )

        response = self._responses[
            response_index
        ]

        if not isinstance(
            response,
            str,
        ):
            raise TypeError(
                "MockProvider responses must be strings"
            )

        return response