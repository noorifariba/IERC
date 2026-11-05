from __future__ import annotations

import copy
import json
from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import Path
from typing import Any

import yaml
from jsonschema import (
    Draft202012Validator,
)

from src.common.hashing import (
    sha256_json,
    sha256_text,
)
from src.common.io import (
    dump_json,
    load_json,
)
from src.postprocess.cep_postprocess import (
    CEPPostprocessError,
    postprocess_cep,
)
from src.providers.base import (
    Provider,
    ProviderRequest,
)


ROOT = Path(__file__).resolve().parents[2]


DEFAULT_CANONICAL_PATH = (
    ROOT
    / "data"
    / "manifests"
    / "regression_24_canonical_inputs_v02.json"
)

DEFAULT_PROMPT_PATH = (
    ROOT
    / "prompts"
    / "prompt_cep_v1.md"
)

DEFAULT_PROMPT_META_PATH = (
    ROOT
    / "prompts"
    / "prompt_cep_v1.meta.json"
)

DEFAULT_RAW_SCHEMA_PATH = (
    ROOT
    / "schemas"
    / "cep_schema_v1.json"
)

DEFAULT_FINAL_SCHEMA_PATH = (
    ROOT
    / "schemas"
    / "cep_final_record_schema_v1.json"
)

DEFAULT_CONFIG_PATH = (
    ROOT
    / "configs"
    / "experiment_regression_td24_r1_v02.yaml"
)


ALLOWED_GENERATION_FIELDS = frozenset(
    {
        "title",
        "description",
    }
)

MAX_REPAIR_ATTEMPTS = 2

MAX_PROVIDER_CALLS = (
    1
    + MAX_REPAIR_ATTEMPTS
)


class CEPRunnerError(
    RuntimeError
):
    """Base CP5 runner error."""


class CanonicalInputError(
    CEPRunnerError
):
    """Frozen canonical-input artifact problem."""


class FrozenArtifactError(
    CEPRunnerError
):
    """Frozen control artifact integrity problem."""


def _schema_error_messages(
    errors: Sequence[Any],
) -> list[str]:
    messages: list[str] = []

    for error in sorted(
        errors,
        key=lambda item: (
            tuple(
                map(
                    str,
                    item.absolute_path,
                )
            ),
            item.message,
        ),
    ):
        path = (
            "/".join(
                map(
                    str,
                    error.absolute_path,
                )
            )
            or "<root>"
        )

        messages.append(
            f"raw_schema:{path}:"
            f"{error.message}"
        )

    return messages

def _json_text_for_parsing(
    raw_text: str,
) -> str:
    """Remove one exact outer JSON Markdown fence for parsing only.

    The original provider response remains preserved verbatim.
    No other text normalization or extraction is permitted.
    """

    stripped = raw_text.strip()

    lines = stripped.splitlines()

    if (
        len(lines) >= 3
        and lines[0].strip() == "```json"
        and lines[-1].strip() == "```"
    ):
        return "\n".join(
            lines[1:-1]
        )

    return raw_text


def _contains_nonrepairable_s4_grounding_inconsistency(
    parsed: Any,
) -> bool:
    """Return True for S4 grounding inconsistency.

    Manager guardrail:

    An S4 assertion with
    external_grounding_required != true must not
    trigger semantic regeneration or repair.

    Although the frozen CP1 schema rejects that
    object, this specific semantic-consistency
    outcome is final for the generation attempt.
    """

    if not isinstance(
        parsed,
        Mapping,
    ):
        return False

    assertions = parsed.get(
        "assertions"
    )

    if not isinstance(
        assertions,
        list,
    ):
        return False

    for assertion in assertions:

        if not isinstance(
            assertion,
            Mapping,
        ):
            continue

        if (
            assertion.get(
                "assertion_state"
            )
            != "S4"
        ):
            continue

        if (
            assertion.get(
                "external_grounding_required"
            )
            is not True
        ):
            return True

    return False


def _select_canonical_record(
    artifact: Any,
    te_id: str,
) -> dict[str, Any]:
    """Select exactly one TE by frozen TE ID."""

    if not isinstance(
        artifact,
        Mapping,
    ):
        raise CanonicalInputError(
            "canonical artifact must be a JSON object"
        )

    records = artifact.get(
        "records"
    )

    if not isinstance(
        records,
        list,
    ):
        raise CanonicalInputError(
            "canonical artifact must contain a records array"
        )

    matches = [
        row
        for row
        in records
        if (
            isinstance(
                row,
                Mapping,
            )
            and (
                row.get(
                    "te_id"
                )
                == te_id
            )
        )
    ]

    if not matches:
        raise CanonicalInputError(
            f"unknown TE ID: {te_id}"
        )

    if len(matches) != 1:
        raise CanonicalInputError(
            "duplicate TE ID in canonical artifact: "
            f"{te_id}"
        )

    return dict(
        matches[0]
    )


def load_canonical_record(
    artifact_path: Path,
    te_id: str,
) -> dict[str, Any]:
    """Load the frozen artifact and select one exact TE."""

    artifact = load_json(
        artifact_path
    )

    return _select_canonical_record(
        artifact,
        te_id,
    )


def build_generation_payload(
    record: Mapping[str, Any],
) -> dict[str, str]:
    """Return only canonical Title and Description."""

    generation_input = (
        record.get(
            "generation_input"
        )
    )

    if not isinstance(
        generation_input,
        Mapping,
    ):
        raise CanonicalInputError(
            "record generation_input must be an object"
        )

    keys = set(
        generation_input
    )

    if (
        keys
        != ALLOWED_GENERATION_FIELDS
    ):
        raise CanonicalInputError(
            "generation_input must contain exactly "
            "title and description; "
            f"found {sorted(keys)}"
        )

    title = generation_input[
        "title"
    ]

    description = generation_input[
        "description"
    ]

    if (
        not isinstance(
            title,
            str,
        )
        or not isinstance(
            description,
            str,
        )
    ):
        raise CanonicalInputError(
            "title and description must both be strings"
        )

    payload = {
        "title":
            title,

        "description":
            description,
    }

    input_hashes = record.get(
        "input_hashes"
    )

    if not isinstance(
        input_hashes,
        Mapping,
    ):
        raise CanonicalInputError(
            "record input_hashes must be an object"
        )

    expected_hash = (
        input_hashes.get(
            "generation_input_sha256"
        )
    )

    if (
        not isinstance(
            expected_hash,
            str,
        )
        or not expected_hash
    ):
        raise CanonicalInputError(
            "generation_input_sha256 is missing"
        )

    actual_hash = sha256_json(
        payload
    )

    if (
        actual_hash
        != expected_hash
    ):
        raise FrozenArtifactError(
            "generation input hash mismatch "
            "for canonical record"
        )

    return payload


def _te_metadata_from_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract provenance for deterministic reattachment only."""

    hidden = record.get(
        "hidden_provenance"
    )

    if not isinstance(
        hidden,
        Mapping,
    ):
        raise CanonicalInputError(
            "hidden_provenance must be an object"
        )

    outer_te_id = record.get(
        "te_id"
    )

    hidden_te_id = hidden.get(
        "te_id"
    )

    if (
        outer_te_id
        != hidden_te_id
    ):
        raise CanonicalInputError(
            "outer te_id and hidden_provenance "
            "te_id disagree"
        )

    required = (
        "te_id",
        "platform",
        "dataset_destination",
        "url",
        "itinerary_status",
        "input_status",
        "adapter_version",
    )

    missing = [
        key
        for key in required
        if key not in hidden
    ]

    if missing:
        raise CanonicalInputError(
            "hidden provenance missing required fields: "
            + ", ".join(
                missing
            )
        )

    return {
        "te_id":
            hidden[
                "te_id"
            ],

        "platform":
            hidden[
                "platform"
            ],

        "dataset_destination":
            hidden[
                "dataset_destination"
            ],

        "url":
            hidden[
                "url"
            ],

        "itinerary_status":
            hidden[
                "itinerary_status"
            ],

        "input_status":
            hidden[
                "input_status"
            ],

        "adapter_version":
            hidden[
                "adapter_version"
            ],
    }


class CEPRunner:
    """CP5 runner using provider abstraction and immutable artifacts."""

    def __init__(
        self,
        provider: Provider,
        *,
        canonical_path:
            Path
            = DEFAULT_CANONICAL_PATH,
        prompt_path:
            Path
            = DEFAULT_PROMPT_PATH,
        prompt_meta_path:
            Path
            = DEFAULT_PROMPT_META_PATH,
        raw_schema_path:
            Path
            = DEFAULT_RAW_SCHEMA_PATH,
        final_schema_path:
            Path
            = DEFAULT_FINAL_SCHEMA_PATH,
        config_path:
            Path
            = DEFAULT_CONFIG_PATH,
    ) -> None:

        self.provider = provider

        self.canonical_path = Path(
            canonical_path
        )

        self.prompt_path = Path(
            prompt_path
        )

        self.prompt_meta_path = Path(
            prompt_meta_path
        )

        self.raw_schema_path = Path(
            raw_schema_path
        )

        self.final_schema_path = Path(
            final_schema_path
        )

        self.config_path = Path(
            config_path
        )

        self.prompt_text = (
            self.prompt_path.read_text(
                encoding="utf-8"
            )
        )

        self.prompt_meta = load_json(
            self.prompt_meta_path
        )

        self.raw_schema_text = (
            self.raw_schema_path.read_text(
                encoding="utf-8"
            )
        )

        self.raw_schema = json.loads(
            self.raw_schema_text
        )

        self.final_schema_text = (
            self.final_schema_path.read_text(
                encoding="utf-8"
            )
        )

        self.final_schema = json.loads(
            self.final_schema_text
        )

        self.config_text = (
            self.config_path.read_text(
                encoding="utf-8"
            )
        )

        self.config = yaml.safe_load(
            self.config_text
        )

        self.canonical_artifact = load_json(
            self.canonical_path
        )

        Draft202012Validator.check_schema(
            self.raw_schema
        )

        Draft202012Validator.check_schema(
            self.final_schema
        )

        self.raw_validator = (
            Draft202012Validator(
                self.raw_schema
            )
        )

        self._verify_frozen_control_contract()

    def _verify_frozen_control_contract(
        self,
    ) -> None:

        if not isinstance(
            self.prompt_meta,
            Mapping,
        ):
            raise FrozenArtifactError(
                "prompt metadata must be an object"
            )

        if not isinstance(
            self.config,
            Mapping,
        ):
            raise FrozenArtifactError(
                "experiment config must be an object"
            )

        if not isinstance(
            self.canonical_artifact,
            Mapping,
        ):
            raise FrozenArtifactError(
                "canonical artifact must be an object"
            )

        actual_prompt_hash = (
            sha256_text(
                self.prompt_text
            )
        )

        expected_prompt_hash = (
            self.prompt_meta.get(
                "prompt_sha256"
            )
        )

        if (
            actual_prompt_hash
            != expected_prompt_hash
        ):
            raise FrozenArtifactError(
                "prompt SHA-256 does not match "
                "frozen prompt metadata"
            )

        artifacts = self.config.get(
            "artifacts"
        )

        if not isinstance(
            artifacts,
            Mapping,
        ):
            raise FrozenArtifactError(
                "experiment config artifacts "
                "section is missing"
            )

        if (
            artifacts.get(
                "prompt_version"
            )
            != self.prompt_meta.get(
                "prompt_version"
            )
        ):
            raise FrozenArtifactError(
                "prompt version mismatch between "
                "config and metadata"
            )

        if (
            artifacts.get(
                "schema_version"
            )
            != self.prompt_meta.get(
                "schema_version"
            )
        ):
            raise FrozenArtifactError(
                "schema version mismatch between "
                "config and prompt metadata"
            )

        if (
            list(
                self.config.get(
                    "input_fields",
                    [],
                )
            )
            != [
                "title",
                "description",
            ]
        ):
            raise FrozenArtifactError(
                "config input_fields must be exactly "
                "title, description"
            )

        if (
            self.config.get(
                "max_schema_repair_attempts"
            )
            != MAX_REPAIR_ATTEMPTS
        ):
            raise FrozenArtifactError(
                "CP5 requires exactly two "
                "repair attempts"
            )

        if (
            self.canonical_artifact.get(
                "experiment_id"
            )
            != self.config.get(
                "experiment_id"
            )
        ):
            raise FrozenArtifactError(
                "canonical artifact and experiment "
                "config ID mismatch"
            )

    def _control_artifacts(
        self,
        *,
        generation_payload:
            Mapping[str, str],
    ) -> dict[str, Any]:

        return {
            "experiment_id":
                self.config[
                    "experiment_id"
                ],

            "config_version":
                self.config[
                    "config_version"
                ],

            "provider_type":
                type(
                    self.provider
                ).__name__,

            "model_id":
                self.provider.model_id,

            "prompt_version":
                self.prompt_meta[
                    "prompt_version"
                ],

            "prompt_sha256":
                sha256_text(
                    self.prompt_text
                ),

            "raw_schema_version":
                self.prompt_meta[
                    "schema_version"
                ],

            "raw_schema_sha256":
                sha256_text(
                    self.raw_schema_text
                ),

            "final_schema_version":
                "cep_final_record_schema_v1",

            "final_schema_sha256":
                sha256_text(
                    self.final_schema_text
                ),

            "config_sha256":
                sha256_text(
                    self.config_text
                ),

            "generation_input_sha256":
                sha256_json(
                    generation_payload
                ),

            "max_repair_attempts":
                MAX_REPAIR_ATTEMPTS,

            "max_provider_calls":
                MAX_PROVIDER_CALLS,
        }

    def _provider_request(
        self,
        *,
        attempt_index: int,
        generation_payload:
            Mapping[str, str],
        previous_raw_response:
            str | None,
        validation_errors:
            Sequence[str],
    ) -> ProviderRequest:

        purpose = (
            "initial"
            if attempt_index == 0
            else "repair"
        )

        return ProviderRequest(
            attempt_index=
                attempt_index,

            purpose=
                purpose,

            generation_payload=
                dict(
                    generation_payload
                ),

            prompt_template=
                self.prompt_text,

            raw_schema=
                copy.deepcopy(
                    self.raw_schema
                ),

            previous_raw_response=
                previous_raw_response,

            validation_errors=
                tuple(
                    validation_errors
                ),
        )

    def _write_attempt_validation(
        self,
        path: Path,
        *,
        attempt_index: int,
        purpose: str,
        raw_response: str,
        json_parse_valid: bool,
        raw_schema_valid:
            bool | None,
        errors:
            Sequence[str],
        repair_eligible: bool,
    ) -> None:

        dump_json(
            path,
            {
                "attempt_index":
                    attempt_index,

                "purpose":
                    purpose,

                "raw_response_sha256":
                    sha256_text(
                        raw_response
                    ),

                "json_parse_valid":
                    json_parse_valid,

                "raw_schema_valid":
                    raw_schema_valid,

                "repair_eligible":
                    repair_eligible,

                "errors":
                    list(
                        errors
                    ),
            },
        )

    def _finish_runner_failure(
        self,
        *,
        run_dir: Path,
        run_id: str,
        te_id: str,
        attempt_count: int,
        failure_stage: str,
        errors:
            Sequence[str],
    ) -> dict[str, Any]:

        result = {
            "run_id":
                run_id,

            "te_id":
                te_id,

            "run_status":
                "failed",

            "failure_stage":
                failure_stage,

            "cultural_abstention":
                None,

            "provider_call_count":
                attempt_count,

            "repair_attempt_count":
                max(
                    0,
                    attempt_count - 1,
                ),

            "raw_output_accepted":
                False,

            "errors":
                list(
                    errors
                ),
        }

        dump_json(
            run_dir
            / "run_result.json",
            result,
        )

        return result

    def run(
        self,
        *,
        te_id: str,
        run_id: str,
        run_dir: Path,
    ) -> dict[str, Any]:

        if (
            not isinstance(
                run_id,
                str,
            )
            or not run_id
        ):
            raise CEPRunnerError(
                "run_id must be a non-empty string"
            )

        record = _select_canonical_record(
            self.canonical_artifact,
            te_id,
        )

        generation_payload = (
            build_generation_payload(
                record
            )
        )

        te_metadata = (
            _te_metadata_from_record(
                record
            )
        )

        run_dir = Path(
            run_dir
        )

        run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        attempts_dir = (
            run_dir
            / "provider_attempts"
        )

        attempts_dir.mkdir()

        dump_json(
            run_dir
            / "generation_input.json",
            generation_payload,
        )

        dump_json(
            run_dir
            / "reattached_provenance.json",
            te_metadata,
        )

        dump_json(
            run_dir
            / "control_artifacts.json",
            self._control_artifacts(
                generation_payload=
                    generation_payload
            ),
        )

        previous_raw_response: str | None = None

        previous_errors:list[str] = []

        for attempt_index in range(
            MAX_PROVIDER_CALLS
        ):

            request = (
                self._provider_request(
                    attempt_index=
                        attempt_index,

                    generation_payload=
                        generation_payload,

                    previous_raw_response=
                        previous_raw_response,

                    validation_errors=
                        previous_errors,
                )
            )

            try:
                raw_response = (
                    self.provider.generate(
                        request
                    )
                )

            except Exception as exc:

                return (
                    self._finish_runner_failure(
                        run_dir=
                            run_dir,

                        run_id=
                            run_id,

                        te_id=
                            te_id,

                        attempt_count=
                            attempt_index + 1,

                        failure_stage=
                            "provider_call",

                        errors=[
                            (
                                "provider_error:"
                                f"{type(exc).__name__}:"
                                f"{exc}"
                            )
                        ],
                    )
                )

            if not isinstance(
                raw_response,
                str,
            ):
                return (
                    self._finish_runner_failure(
                        run_dir=
                            run_dir,

                        run_id=
                            run_id,

                        te_id=
                            te_id,

                        attempt_count=
                            attempt_index + 1,

                        failure_stage=
                            "provider_call",

                        errors=[
                            "provider_response_must_be_text"
                        ],
                    )
                )

            raw_path = (
                attempts_dir
                / (
                    f"attempt_"
                    f"{attempt_index:02d}"
                    "_raw.txt"
                )
            )

            raw_path.write_bytes(
                raw_response.encode(
                    "utf-8"
                )
            )

            try:
                parse_text = (
                    _json_text_for_parsing(
                        raw_response
                    )
                )
                parsed = json.loads(
                    parse_text
                )

            except json.JSONDecodeError as exc:

                errors = [
                    (
                        "json_parse:"
                        f"line={exc.lineno}:"
                        f"column={exc.colno}:"
                        f"{exc.msg}"
                    )
                ]

                can_repair = (
                    attempt_index
                    < MAX_REPAIR_ATTEMPTS
                )

                self._write_attempt_validation(
                    (
                        attempts_dir
                        / (
                            f"attempt_"
                            f"{attempt_index:02d}"
                            "_validation.json"
                        )
                    ),

                    attempt_index=
                        attempt_index,

                    purpose=
                        request.purpose,

                    raw_response=
                        raw_response,

                    json_parse_valid=
                        False,

                    raw_schema_valid=
                        None,

                    errors=
                        errors,

                    repair_eligible=
                        can_repair,
                )

                if can_repair:

                    previous_raw_response = (
                        raw_response
                    )

                    previous_errors = (
                        errors
                    )

                    continue

                return (
                    self._finish_runner_failure(
                        run_dir=
                            run_dir,

                        run_id=
                            run_id,

                        te_id=
                            te_id,

                        attempt_count=
                            attempt_index + 1,

                        failure_stage=
                            "raw_output_conformity",

                        errors=
                            errors,
                    )
                )

            schema_errors = list(
                self.raw_validator.iter_errors(
                    parsed
                )
            )

            if schema_errors:

                errors = (
                    _schema_error_messages(
                        schema_errors
                    )
                )

                s4_no_repair = (
                    _contains_nonrepairable_s4_grounding_inconsistency(
                        parsed
                    )
                )

                can_repair = (
                    (
                        attempt_index
                        < MAX_REPAIR_ATTEMPTS
                    )
                    and not s4_no_repair
                )

                self._write_attempt_validation(
                    (
                        attempts_dir
                        / (
                            f"attempt_"
                            f"{attempt_index:02d}"
                            "_validation.json"
                        )
                    ),

                    attempt_index=
                        attempt_index,

                    purpose=
                        request.purpose,

                    raw_response=
                        raw_response,

                    json_parse_valid=
                        True,

                    raw_schema_valid=
                        False,

                    errors=
                        errors,

                    repair_eligible=
                        can_repair,
                )

                if can_repair:

                    previous_raw_response = (
                        raw_response
                    )

                    previous_errors = (
                        errors
                    )

                    continue

                failure_stage = (
                    "raw_schema_semantic_consistency"
                    if s4_no_repair
                    else "raw_output_conformity"
                )

                return (
                    self._finish_runner_failure(
                        run_dir=
                            run_dir,

                        run_id=
                            run_id,

                        te_id=
                            te_id,

                        attempt_count=
                            attempt_index + 1,

                        failure_stage=
                            failure_stage,

                        errors=
                            errors,
                    )
                )

            self._write_attempt_validation(
                (
                    attempts_dir
                    / (
                        f"attempt_"
                        f"{attempt_index:02d}"
                        "_validation.json"
                    )
                ),

                attempt_index=
                    attempt_index,

                purpose=
                    request.purpose,

                raw_response=
                    raw_response,

                json_parse_valid=
                    True,

                raw_schema_valid=
                    True,

                errors=
                    [],

                repair_eligible=
                    False,
            )

            dump_json(
                run_dir
                / "accepted_raw_output.json",
                parsed,
            )

            run_metadata = {
                "run_id":
                    run_id,

                "model_id":
                    self.provider.model_id,

                "prompt_version":
                    self.prompt_meta[
                        "prompt_version"
                    ],

                "config_version":
                    self.config[
                        "config_version"
                    ],

                "adapter_version":
                    te_metadata[
                        "adapter_version"
                    ],
            }

            cp4_te_metadata = {
                "te_id":
                    te_metadata[
                        "te_id"
                    ],

                "platform":
                    te_metadata[
                        "platform"
                    ],

                "dataset_destination":
                    te_metadata[
                        "dataset_destination"
                    ],

                "url":
                    te_metadata[
                        "url"
                    ],

                "itinerary_status":
                    te_metadata[
                        "itinerary_status"
                    ],

                "input_status":
                    te_metadata[
                        "input_status"
                    ],
            }

            try:
                final_record = (
                    postprocess_cep(
                        parsed,

                        title=
                            generation_payload[
                                "title"
                            ],

                        description=
                            generation_payload[
                                "description"
                            ],

                        run_metadata=
                            run_metadata,

                        te_metadata=
                            cp4_te_metadata,
                    )
                )

            except CEPPostprocessError as exc:

                dump_json(
                    run_dir
                    / "postprocess_failure.json",
                    {
                        "run_status":
                            "failed",

                        "cultural_abstention":
                            None,

                        "errors":
                            exc.errors,
                    },
                )

                return (
                    self._finish_runner_failure(
                        run_dir=
                            run_dir,

                        run_id=
                            run_id,

                        te_id=
                            te_id,

                        attempt_count=
                            attempt_index + 1,

                        failure_stage=
                            "postprocess",

                        errors=
                            exc.errors,
                    )
                )

            dump_json(
                run_dir
                / "final_record.json",
                final_record,
            )

            result = {
                "run_id":
                    run_id,

                "te_id":
                    te_id,

                "run_status":
                    final_record[
                        "run_status"
                    ],

                "failure_stage":
                    (
                        None
                        if (
                            final_record[
                                "run_status"
                            ]
                            == "accepted"
                        )
                        else "postprocess"
                    ),

                "cultural_abstention":
                    final_record[
                        "te_level_cep"
                    ][
                        "cultural_abstention"
                    ],

                "provider_call_count":
                    attempt_index + 1,

                "repair_attempt_count":
                    attempt_index,

                "raw_output_accepted":
                    True,

                "errors":
                    final_record[
                        "validation"
                    ][
                        "validation_errors"
                    ],
            }

            dump_json(
                run_dir
                / "run_result.json",
                result,
            )

            return result

        raise AssertionError(
            "provider attempt loop exited unexpectedly"
        )