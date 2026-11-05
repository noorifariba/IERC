from __future__ import annotations


import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from src.common.io import load_json
from src.providers.base import (
    Provider,
    ProviderRequest,
)


ROOT = Path(__file__).resolve().parents[2]

_ALLOWED_GENERATION_FIELDS = frozenset(
    {
        "title",
        "description",
    }
)


def _sha256_file(
    path: Path,
) -> str:

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


@dataclass(frozen=True)
class LlamaCppRuntimeConfig:

    model_id: str

    endpoint: str

    temperature: float

    top_k: int

    top_p: float

    seed: int | None

    max_output_tokens: int

    timeout_seconds: int

    authoritative_schema_path: Path

    authoritative_schema_sha256: str

class LlamaCppProvider(
    Provider
):
    """Local llama.cpp provider for frozen CEP Prototype v1."""

    def __init__(
        self,
        config: LlamaCppRuntimeConfig,
    ) -> None:

        self.config = config

        self.model_id = (
            config.model_id
        )

        if (
            _sha256_file(
                config.authoritative_schema_path
            )
            != config.authoritative_schema_sha256
        ):

            raise ValueError(
                "authoritative CP1 schema hash mismatch"
            )

        self._authoritative_schema = load_json(
            config.authoritative_schema_path
        )

        self._call_count = 0

    @property
    def call_count(
        self,
    ) -> int:

        return self._call_count

    @classmethod
    def from_config_path(
        cls,
        path: Path,
    ) -> "LlamaCppProvider":

        data = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            data,
            Mapping,
        ):

            raise ValueError(
                "local llama.cpp config must be a mapping"
            )

        model = data[
            "model"
        ]

        server = data[
            "server"
        ]

        generation = data[
            "generation"
        ]

        structured = data[
            "structured_output"
        ]

        if (
            server[
                "host"
            ]
            != "127.0.0.1"
        ):

            raise ValueError(
                "local llama.cpp server must bind "
                "only to localhost"
            )

        if (
            server[
                "cuda_visible_devices"
            ]
            != "0"
        ):

            raise ValueError(
                "CP6 must explicitly isolate GPU0"
            )

        if (
            server[
                "split_mode"
            ]
            != "none"
        ):

            raise ValueError(
                "CP6 must use single-GPU split mode"
            )

        if int(
            server[
                "main_gpu"
            ]
        ) != 0:

            raise ValueError(
                "CP6 main GPU must be GPU0"
            )

        if (
            server[
                "fit"
            ]
            is not False
        ):

            raise ValueError(
                "automatic runtime fitting must be disabled"
            )

        if int(
            server[
                "parallel"
            ]
        ) != 1:

            raise ValueError(
                "CP6 requires one TE at a time"
            )

        if (
            server[
                "gpu_layer_flag"
            ]
            not in {
                "--n-gpu-layers",
                "--gpu-layers",
            }
        ):

            raise ValueError(
                "unverified GPU-layer option"
            )

        if (
            server[
                "gpu_layers"
            ]
            != "all"
        ):

            raise ValueError(
                "GPU-layer configuration must use "
                "the help-verified 'all' value"
            )

        if (
            model[
                "text_only"
            ]
            is not True
        ):

            raise ValueError(
                "Gemma execution must remain text-only"
            )

        if (
            model[
                "vision_projector"
            ]
            is not None
        ):

            raise ValueError(
                "vision projector must not be configured"
            )

        if (
            server[
                "mmproj"
            ]
            is not False
        ):

            raise ValueError(
                "multimodal projector must remain disabled"
            )

        if (
            server[
                "jinja"
            ]
            is not True
        ):

            raise ValueError(
                "Jinja chat-template processing must be enabled"
            )

        if (
            server[
                "offline"
            ]
            is not True
        ):

            raise ValueError(
                "local llama.cpp runtime must remain offline"
            )

        if float(
            generation[
                "temperature"
            ]
        ) != 0.0:

            raise ValueError(
                "temperature must be zero"
            )

        if int(
            generation[
                "top_k"
            ]
        ) != 1:

            raise ValueError(
                "non-stochastic configuration requires top_k=1"
            )

        if (
            generation[
                "tools"
            ]
            is not False
        ):

            raise ValueError(
                "tools must remain disabled"
            )

        if (
            generation[
                "external_retrieval"
            ]
            is not False
        ):

            raise ValueError(
                "external retrieval must remain disabled"
            )

        if (
            structured[
                "mode"
            ]
            != "schema_control_text"
        ):

            raise ValueError(
                "unexpected structured-output strategy"
            )

        if (
            structured[
                "schema_constrained_decoding"
            ]
            is not False
        ):

            raise ValueError(
                "CP7 schema-constrained decoding must be disabled"
            )

        if (
            structured[
                "schema_injected_as_control_text"
            ]
            is not True
        ):

            raise ValueError(
                "CP7 requires authoritative schema control text"
            )

        if (
            structured[
                "markdown_fence_normalization"
            ]
            is not True
        ):

            raise ValueError(
                "CP7 requires Markdown fence normalization"
            )

        if (
            structured[
                "authoritative_validation_after_generation"
            ]
            is not True
        ):

            raise ValueError(
                "complete frozen CP1 must remain authoritative"
            )

        def resolve(
            value: str,
        ) -> Path:

            candidate = Path(
                value
            )

            if candidate.is_absolute():

                return candidate

            return (
                ROOT
                / candidate
            )

        return cls(
            LlamaCppRuntimeConfig(
                model_id=str(
                    model[
                        "alias"
                    ]
                ),

                endpoint=str(
                    server[
                        "endpoint"
                    ]
                ),

                temperature=float(
                    generation[
                        "temperature"
                    ]
                ),

                top_k=int(
                    generation[
                        "top_k"
                    ]
                ),

                top_p=float(
                    generation[
                        "top_p"
                    ]
                ),

                seed=(
                    None
                    if generation[
                        "seed"
                    ] is None
                    else int(
                        generation[
                            "seed"
                        ]
                    )
                ),

                max_output_tokens=int(
                    generation[
                        "max_output_tokens"
                    ]
                ),

                timeout_seconds=600,

                authoritative_schema_path=resolve(
                    structured[
                        "authoritative_schema_path"
                    ]
                ),

                authoritative_schema_sha256=str(
                    structured[
                        "authoritative_schema_sha256"
                    ]
                ),

            )
        )

    def _validate_provider_request(
        self,
        request: ProviderRequest,
    ) -> None:

        if set(
            request.generation_payload
        ) != _ALLOWED_GENERATION_FIELDS:

            raise ValueError(
                "local provider generation payload must "
                "contain exactly title and description"
            )

        for key, value in (
            request.generation_payload.items()
        ):

            if not isinstance(
                value,
                str,
            ):

                raise TypeError(
                    f"generation field {key} must be text"
                )

        if (
            dict(
                request.raw_schema
            )
            != self._authoritative_schema
        ):

            raise ValueError(
                "ProviderRequest raw_schema differs from "
                "the frozen authoritative CP1 schema"
            )

        if (
            request.purpose
            == "initial"
        ):

            if (
                request.previous_raw_response
                is not None
            ):

                raise ValueError(
                    "initial generation cannot contain "
                    "a previous provider response"
                )

        elif (
            request.purpose
            == "repair"
        ):

            if (
                request.previous_raw_response
                is None
            ):

                raise ValueError(
                    "repair requires the previous invalid "
                    "provider response"
                )

        else:

            raise ValueError(
                "unsupported provider purpose: "
                f"{request.purpose}"
            )

    @staticmethod
    def _render_prompt(
        request: ProviderRequest,
    ) -> str:

        template = (
            request.prompt_template
        )

        if (
            "{{TITLE}}" not in template
            or "{{DESCRIPTION}}" not in template
        ):

            raise ValueError(
                "frozen prompt placeholders are missing"
            )

        rendered = template.replace(
            "{{TITLE}}",
            request.generation_payload[
                "title"
            ],
        ).replace(
            "{{DESCRIPTION}}",
            request.generation_payload[
                "description"
            ],
        )

        if (
            "{{TITLE}}" in rendered
            or "{{DESCRIPTION}}" in rendered
        ):

            raise ValueError(
                "unresolved frozen prompt placeholder"
            )

        schema_control = json.dumps(
            request.raw_schema,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

        rendered += (
            "\n\n"
            "=== AUTHORITATIVE CEP JSON SCHEMA ===\n"
            "This schema is structural control information only. "
            "It is not source evidence. "
            "Return exactly one JSON object that conforms to it.\n"
            f"{schema_control}\n"
            "=== END AUTHORITATIVE CEP JSON SCHEMA ===\n"
        )

        if (
            request.purpose
            == "repair"
        ):

            errors = "\n".join(
                f"- {message}"
                for message
                in request.validation_errors
            )

            rendered += (
                "\n\n"
                "=== DETERMINISTIC REPAIR CONTROL ===\n"
                "The previous provider response failed JSON "
                "parsing or the frozen CP1 structural gate. "
                "Correct only the JSON/schema-conformity problems. "
                "Do not add information absent from the canonical "
                "Title and Description. Return only the corrected "
                "JSON object.\n\n"
                "Deterministic validation errors:\n"
                f"{errors or '- structural validation failure'}"
                "\n\n"
                "Previous invalid raw response:\n"
                "<<<PREVIOUS_RAW_RESPONSE\n"
                f"{request.previous_raw_response}\n"
                "PREVIOUS_RAW_RESPONSE\n"
            )

        return rendered

    def build_http_payload(
        self,
        request: ProviderRequest,
    ) -> dict[str, Any]:

        self._validate_provider_request(
            request
        )

        content = self._render_prompt(
            request
        )

        payload: dict[str, Any] = {
            "model":
                self.model_id,

            "messages": [
                {
                    "role":
                        "user",

                    "content":
                        content,
                }
            ],

            "temperature":
                self.config.temperature,

            "top_k":
                self.config.top_k,

            "top_p":
                self.config.top_p,

            "max_tokens":
                self.config.max_output_tokens,

            "stream":
                False,

        }

        if (
            self.config.seed
            is not None
        ):

            payload[
                "seed"
            ] = self.config.seed

        return payload

    def _post_json(
        self,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode(
            "utf-8"
        )

        http_request = Request(
            self.config.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type":
                    "application/json",
            },
        )

        try:

            with urlopen(
                http_request,
                timeout=
                    self.config.timeout_seconds,
            ) as response:

                raw = (
                    response.read()
                )

        except HTTPError as exc:

            raise RuntimeError(
                "local llama.cpp HTTP failure: "
                f"{exc.code}"
            ) from exc

        except URLError as exc:

            raise RuntimeError(
                "local llama.cpp connection failure"
            ) from exc

        parsed = json.loads(
            raw.decode(
                "utf-8"
            )
        )

        if not isinstance(
            parsed,
            Mapping,
        ):

            raise RuntimeError(
                "llama.cpp server returned a non-object response"
            )

        return parsed

    def generate(
        self,
        request: ProviderRequest,
    ) -> str:

        payload = (
            self.build_http_payload(
                request
            )
        )

        self._call_count += 1

        response = (
            self._post_json(
                payload
            )
        )

        try:

            content = (
                response[
                    "choices"
                ][
                    0
                ][
                    "message"
                ][
                    "content"
                ]
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise RuntimeError(
                "llama.cpp response lacks "
                "choices[0].message.content"
            ) from exc

        if not isinstance(
            content,
            str,
        ):

            raise RuntimeError(
                "llama.cpp completion content must be raw text"
            )

        return content
