from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from src.common.evidence_resolver import (
    MULTIPLE_MATCH,
    RESOLVED,
    ZERO_MATCH,
    resolve_evidence,
)


ROOT = Path(__file__).resolve().parents[2]

CONSTANTS_PATH = (
    ROOT
    / "configs"
    / "constants_v0_2.yaml"
)

RAW_SCHEMA_PATH = (
    ROOT
    / "schemas"
    / "cep_schema_v1.json"
)

FINAL_SCHEMA_PATH = (
    ROOT
    / "schemas"
    / "cep_final_record_schema_v1.json"
)


_CONSTANTS = yaml.safe_load(
    CONSTANTS_PATH.read_text(
        encoding="utf-8"
    )
)

FACET_ORDER = tuple(
    _CONSTANTS["candidate_facets"]
)

CEP_ELIGIBILITY = dict(
    _CONSTANTS["cep_eligibility"]
)

MEMBERSHIP_EFFECT = dict(
    _CONSTANTS["membership_effect"]
)

GROUNDING_REQUIRED = dict(
    _CONSTANTS[
        "external_grounding_required"
    ]
)


_LOCATION_STATUS = {
    RESOLVED:
        "resolved",

    ZERO_MATCH:
        "invalid_zero_match",

    MULTIPLE_MATCH:
        "ambiguous_duplicate",
}


class CEPPostprocessError(ValueError):
    """Technical failure, never cultural abstention."""

    def __init__(
        self,
        message: str,
        errors: Sequence[str] | None = None,
    ):
        super().__init__(message)

        self.errors = list(
            errors or [message]
        )

        self.run_status = "failed"

        self.cultural_abstention = None


def _load_validator(
    path: Path,
) -> Draft202012Validator:
    schema = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator.check_schema(
        schema
    )

    return Draft202012Validator(
        schema
    )


def _raw_validator() -> Draft202012Validator:
    return _load_validator(
        RAW_SCHEMA_PATH
    )


def _final_validator() -> Draft202012Validator:
    return _load_validator(
        FINAL_SCHEMA_PATH
    )


def _schema_error_messages(
    prefix: str,
    errors: Sequence[Any],
) -> list[str]:
    messages: list[str] = []

    sorted_errors = sorted(
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
    )

    for error in sorted_errors:
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
            f"{prefix}:{path}:"
            f"{error.message}"
        )

    return messages


def _validate_metadata(
    run_metadata: Mapping[str, Any],
    te_metadata: Mapping[str, Any],
) -> None:
    required_run = (
        "run_id",
        "model_id",
        "prompt_version",
        "config_version",
        "adapter_version",
    )

    required_te = (
        "te_id",
        "platform",
        "dataset_destination",
        "url",
        "itinerary_status",
        "input_status",
    )

    missing_run = [
        key
        for key in required_run
        if key not in run_metadata
    ]

    missing_te = [
        key
        for key in required_te
        if key not in te_metadata
    ]

    if missing_run or missing_te:
        errors = [
            f"missing_run_metadata:{key}"
            for key in missing_run
        ]

        errors += [
            f"missing_te_metadata:{key}"
            for key in missing_te
        ]

        raise CEPPostprocessError(
            "missing deterministic metadata",
            errors,
        )

    if (
        not isinstance(
            te_metadata["te_id"],
            str,
        )
        or not te_metadata["te_id"]
    ):
        raise CEPPostprocessError(
            "te_id must be a non-empty string"
        )


def _base_record(
    *,
    run_status: str,
    run_metadata: Mapping[str, Any],
    te_metadata: Mapping[str, Any],
    components: list[
        dict[str, Any]
    ] | None = None,
    assertions: list[
        dict[str, Any]
    ] | None = None,
    facet_summaries: list[
        dict[str, Any]
    ] | None = None,
    cultural_abstention: bool | None = None,
    abstention_reason: str | None = None,
    unmapped: list[
        dict[str, Any]
    ] | None = None,
    raw_output_schema_valid: bool,
    evidence_valid: bool | None,
    ambiguity_count: int,
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema_version":
            "cep_schema_v1",

        "run_status":
            run_status,

        "run_metadata": {
            "run_id":
                run_metadata["run_id"],

            "model_id":
                run_metadata["model_id"],

            "prompt_version":
                run_metadata[
                    "prompt_version"
                ],

            "config_version":
                run_metadata[
                    "config_version"
                ],

            "adapter_version":
                run_metadata[
                    "adapter_version"
                ],
        },

        "te": {
            "te_id":
                te_metadata["te_id"],

            "platform":
                te_metadata["platform"],

            "dataset_destination":
                te_metadata[
                    "dataset_destination"
                ],

            "url":
                te_metadata["url"],

            "itinerary_status":
                te_metadata[
                    "itinerary_status"
                ],

            "input_status":
                te_metadata[
                    "input_status"
                ],

            "input_fields_used": [
                "title",
                "description",
            ],
        },

        "components":
            components or [],

        "assertions":
            assertions or [],

        "te_level_cep": {
            "facet_summaries":
                facet_summaries or [],

            "cultural_abstention":
                cultural_abstention,

            "abstention_reason":
                abstention_reason,
        },

        "unmapped_cultural_content":
            unmapped or [],

        "validation": {
            "schema_valid":
                True,

            "raw_output_schema_valid":
                raw_output_schema_valid,

            "evidence_valid":
                evidence_valid,

            "evidence_location_ambiguity_count":
                ambiguity_count,

            "validation_errors":
                validation_errors,
        },
    }


def _validate_final_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    schema_errors = list(
        _final_validator().iter_errors(
            record
        )
    )

    if schema_errors:
        raise CEPPostprocessError(
            "final record schema validation failed",
            _schema_error_messages(
                "final_schema",
                schema_errors,
            ),
        )

    return record


def _raw_schema_failure_record(
    *,
    raw_errors: Sequence[Any],
    run_metadata: Mapping[str, Any],
    te_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    record = _base_record(
        run_status="failed",

        run_metadata=
            run_metadata,

        te_metadata=
            te_metadata,

        raw_output_schema_valid=
            False,

        evidence_valid=
            None,

        ambiguity_count=
            0,

        validation_errors=
            _schema_error_messages(
                "raw_schema",
                raw_errors,
            ),
    )

    return _validate_final_record(
        record
    )


def _unique_index(
    items: Sequence[
        Mapping[str, Any]
    ],
    key: str,
) -> dict[
    str,
    Mapping[str, Any],
]:
    index: dict[
        str,
        Mapping[str, Any],
    ] = {}

    errors: list[str] = []

    for item in items:
        value = item.get(
            key
        )

        if (
            not isinstance(
                value,
                str,
            )
            or not value
        ):
            errors.append(
                f"missing_or_invalid_{key}"
            )
            continue

        if value in index:
            errors.append(
                f"duplicate_{key}:{value}"
            )
            continue

        index[value] = item

    if errors:
        raise CEPPostprocessError(
            "invalid local identifiers",
            errors,
        )

    return index


def _require_refs(
    refs: Sequence[str],
    available: Mapping[
        str,
        Any,
    ],
    context: str,
) -> None:
    missing = [
        ref
        for ref in refs
        if ref not in available
    ]

    if missing:
        raise CEPPostprocessError(
            f"broken references in {context}",
            [
                (
                    "broken_reference:"
                    f"{context}:{ref}"
                )
                for ref in missing
            ],
        )


def postprocess_cep(
    raw_output: Any,
    *,
    title: str,
    description: str,
    run_metadata: Mapping[str, Any],
    te_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic final CEP record.

    Raw model output is validated against the
    frozen CP1 schema before any aggregation.

    Schema-invalid raw output is a technical
    failure and is never cultural abstention.
    """

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
        raise CEPPostprocessError(
            "title and description must be strings"
        )

    _validate_metadata(
        run_metadata,
        te_metadata,
    )

    # CRITICAL CP4 GATE:
    # Validate complete raw model output against
    # frozen CP1 schema BEFORE any aggregation.
    raw_errors = list(
        _raw_validator().iter_errors(
            raw_output
        )
    )

    if raw_errors:
        return _raw_schema_failure_record(
            raw_errors=
                raw_errors,

            run_metadata=
                run_metadata,

            te_metadata=
                te_metadata,
        )

    # Direct access is intentional.
    # CP1 schema has already established that
    # every required section exists and has
    # the expected top-level type.
    components_raw = list(
        raw_output["components"]
    )

    evidence_raw = list(
        raw_output["evidence"]
    )

    assertions_raw = list(
        raw_output["assertions"]
    )

    salience_raw = list(
        raw_output[
            "salience_proposals"
        ]
    )

    unmapped_raw = list(
        raw_output[
            "unmapped_content"
        ]
    )

    component_index = _unique_index(
        components_raw,
        "component_local_id",
    )

    evidence_index = _unique_index(
        evidence_raw,
        "evidence_id",
    )

    _unique_index(
        assertions_raw,
        "assertion_local_id",
    )

    _unique_index(
        unmapped_raw,
        "unmapped_local_id",
    )

    for component in components_raw:
        _require_refs(
            component[
                "evidence_refs"
            ],

            evidence_index,

            (
                "component:"
                f"{component['component_local_id']}"
            ),
        )

    for assertion in assertions_raw:
        component_ref = assertion[
            "component_local_id"
        ]

        _require_refs(
            [component_ref],

            component_index,

            (
                "assertion_component:"
                f"{assertion['assertion_local_id']}"
            ),
        )

        _require_refs(
            assertion[
                "evidence_refs"
            ],

            evidence_index,

            (
                "assertion_evidence:"
                f"{assertion['assertion_local_id']}"
            ),
        )

    for item in unmapped_raw:
        component_ref = item[
            "component_local_id"
        ]

        _require_refs(
            [component_ref],

            component_index,

            (
                "unmapped_component:"
                f"{item['unmapped_local_id']}"
            ),
        )

        _require_refs(
            item["evidence_refs"],

            evidence_index,

            (
                "unmapped_evidence:"
                f"{item['unmapped_local_id']}"
            ),
        )

    te_id = te_metadata[
        "te_id"
    ]

    component_id_map = {
        component[
            "component_local_id"
        ]:
            f"{te_id}-C{index}"

        for index, component
        in enumerate(
            components_raw,
            start=1,
        )
    }

    assertion_id_map = {
        assertion[
            "assertion_local_id"
        ]:
            f"{te_id}-A{index}"

        for index, assertion
        in enumerate(
            assertions_raw,
            start=1,
        )
    }

    resolved_evidence: dict[
        str,
        dict[str, Any],
    ] = {}

    validation_errors: list[str] = []

    ambiguity_count = 0

    for evidence in evidence_raw:
        resolved = resolve_evidence(
            evidence,

            title=
                title,

            description=
                description,
        )

        resolved_evidence[
            evidence[
                "evidence_id"
            ]
        ] = resolved

        if (
            resolved[
                "resolution_status"
            ]
            == ZERO_MATCH
        ):
            validation_errors.append(
                (
                    "evidence_zero_match:"
                    f"{evidence['evidence_id']}"
                )
            )

        elif (
            resolved[
                "resolution_status"
            ]
            == MULTIPLE_MATCH
        ):
            ambiguity_count += 1

            validation_errors.append(
                (
                    "evidence_ambiguous_duplicate:"
                    f"{evidence['evidence_id']}"
                )
            )

    evidence_valid = all(
        item[
            "resolution_status"
        ]
        == RESOLVED

        for item
        in resolved_evidence.values()
    )

    assertion_by_component: dict[
        str,
        list[
            Mapping[str, Any]
        ],
    ] = {
        local_id: []
        for local_id
        in component_index
    }

    for assertion in assertions_raw:
        assertion_by_component[
            assertion[
                "component_local_id"
            ]
        ].append(
            assertion
        )

    unmapped_by_component: dict[
        str,
        list[
            Mapping[str, Any]
        ],
    ] = {
        local_id: []
        for local_id
        in component_index
    }

    for item in unmapped_raw:
        unmapped_by_component[
            item[
                "component_local_id"
            ]
        ].append(
            item
        )

    final_components: list[
        dict[str, Any]
    ] = []

    evidence_id_map: dict[
        tuple[str, str],
        str,
    ] = {}

    for component in components_raw:
        local_component_id = (
            component[
                "component_local_id"
            ]
        )

        final_component_id = (
            component_id_map[
                local_component_id
            ]
        )

        related_refs = set(
            component[
                "evidence_refs"
            ]
        )

        for assertion in (
            assertion_by_component[
                local_component_id
            ]
        ):
            related_refs.update(
                assertion[
                    "evidence_refs"
                ]
            )

        for item in (
            unmapped_by_component[
                local_component_id
            ]
        ):
            related_refs.update(
                item[
                    "evidence_refs"
                ]
            )

        evidence_spans: list[
            dict[str, Any]
        ] = []

        component_evidence_number = 0

        for evidence in evidence_raw:
            local_evidence_id = (
                evidence[
                    "evidence_id"
                ]
            )

            if (
                local_evidence_id
                not in related_refs
            ):
                continue

            component_evidence_number += 1

            final_evidence_id = (
                f"{final_component_id}"
                f"-E{component_evidence_number}"
            )

            evidence_id_map[
                (
                    local_component_id,
                    local_evidence_id,
                )
            ] = final_evidence_id

            resolved = (
                resolved_evidence[
                    local_evidence_id
                ]
            )

            evidence_spans.append(
                {
                    "evidence_id":
                        final_evidence_id,

                    "source_field":
                        resolved[
                            "source_field"
                        ],

                    "exact_text":
                        resolved[
                            "exact_text"
                        ],

                    "char_start":
                        resolved[
                            "char_start"
                        ],

                    "char_end":
                        resolved[
                            "char_end"
                        ],

                    "location_status":
                        _LOCATION_STATUS[
                            resolved[
                                "resolution_status"
                            ]
                        ],
                }
            )

        role = component[
            "component_role"
        ]

        final_components.append(
            {
                "component_id":
                    final_component_id,

                "normalized_label":
                    component[
                        "normalized_label"
                    ],

                "component_type":
                    component[
                        "component_type"
                    ],

                "component_role":
                    role,

                "cep_eligible":
                    bool(
                        CEP_ELIGIBILITY[
                            role
                        ]
                    ),

                "evidence_spans":
                    evidence_spans,
            }
        )

    final_assertions: list[
        dict[str, Any]
    ] = []

    for assertion in assertions_raw:
        local_component_id = (
            assertion[
                "component_local_id"
            ]
        )

        state = assertion[
            "assertion_state"
        ]

        expected_grounding = bool(
            GROUNDING_REQUIRED[
                state
            ]
        )

        # Defense in depth.
        # Frozen CP1 schema should already
        # enforce this before reaching here.
        if (
            bool(
                assertion[
                    "external_grounding_required"
                ]
            )
            != expected_grounding
        ):
            validation_errors.append(
                (
                    "external_grounding_inconsistent:"
                    f"{assertion['assertion_local_id']}"
                )
            )

        final_assertions.append(
            {
                "assertion_id":
                    assertion_id_map[
                        assertion[
                            "assertion_local_id"
                        ]
                    ],

                "component_id":
                    component_id_map[
                        local_component_id
                    ],

                "facet":
                    assertion[
                        "facet"
                    ],

                "observable_cue":
                    assertion[
                        "observable_cue"
                    ],

                "evidence_refs": [
                    evidence_id_map[
                        (
                            local_component_id,
                            ref,
                        )
                    ]

                    for ref
                    in assertion[
                        "evidence_refs"
                    ]
                ],

                "relation_qualifier":
                    assertion[
                        "relation_qualifier"
                    ],

                "assertion_state":
                    state,

                "external_grounding_required":
                    expected_grounding,

                "membership_effect":
                    MEMBERSHIP_EFFECT[
                        state
                    ],

                "ambiguity_note":
                    assertion[
                        "ambiguity_note"
                    ],
            }
        )

    salience_map: dict[
        str,
        int,
    ] = {}

    for proposal in salience_raw:
        facet = proposal[
            "facet"
        ]

        if facet in salience_map:
            validation_errors.append(
                (
                    "duplicate_salience_proposal:"
                    f"{facet}"
                )
            )

        else:
            salience_map[
                facet
            ] = proposal[
                "salience"
            ]

    final_component_by_id = {
        component[
            "component_id"
        ]:
            component

        for component
        in final_components
    }

    supported: dict[
        str,
        dict[
            str,
            list[str],
        ],
    ] = {}

    for assertion in final_assertions:
        if (
            assertion[
                "assertion_state"
            ]
            != "S1"
        ):
            continue

        component = (
            final_component_by_id[
                assertion[
                    "component_id"
                ]
            ]
        )

        if not component[
            "cep_eligible"
        ]:
            continue

        facet = assertion[
            "facet"
        ]

        bucket = supported.setdefault(
            facet,
            {
                "component_ids": [],
                "assertion_ids": [],
            },
        )

        if (
            assertion[
                "component_id"
            ]
            not in bucket[
                "component_ids"
            ]
        ):
            bucket[
                "component_ids"
            ].append(
                assertion[
                    "component_id"
                ]
            )

        bucket[
            "assertion_ids"
        ].append(
            assertion[
                "assertion_id"
            ]
        )

    supported_facets = set(
        supported
    )

    salience_facets = set(
        salience_map
    )

    for facet in sorted(
        (
            supported_facets
            - salience_facets
        ),
        key=
            FACET_ORDER.index,
    ):
        validation_errors.append(
            (
                "missing_salience_for_supported_facet:"
                f"{facet}"
            )
        )

    for facet in sorted(
        (
            salience_facets
            - supported_facets
        ),
        key=
            FACET_ORDER.index,
    ):
        validation_errors.append(
            (
                "salience_without_supported_fixed_s1:"
                f"{facet}"
            )
        )

    run_status = (
        "accepted"

        if (
            not validation_errors
            and evidence_valid
        )

        else "failed"
    )

    eligible_count = sum(
        component[
            "cep_eligible"
        ]

        for component
        in final_components
    )

    facet_summaries: list[
        dict[str, Any]
    ] = []

    if run_status == "accepted":
        for facet in FACET_ORDER:
            if (
                facet
                not in supported
            ):
                continue

            component_ids = (
                supported[
                    facet
                ][
                    "component_ids"
                ]
            )

            numerator = len(
                component_ids
            )

            facet_summaries.append(
                {
                    "facet":
                        facet,

                    "supported_membership":
                        True,

                    "salience_ordinal":
                        salience_map[
                            facet
                        ],

                    "supporting_s1_component_ids":
                        component_ids,

                    "coverage_numerator":
                        numerator,

                    "coverage_denominator":
                        eligible_count,

                    "component_coverage":
                        (
                            numerator
                            / eligible_count
                        ),

                    "assertion_refs":
                        supported[
                            facet
                        ][
                            "assertion_ids"
                        ],
                }
            )

        cultural_abstention = (
            not bool(
                facet_summaries
            )
        )

        if not cultural_abstention:
            abstention_reason = None

        elif eligible_count == 0:
            abstention_reason = (
                "no_eligible_component_identified"
            )

        else:
            abstention_reason = (
                "no_s1_supported_facet"
            )

    else:
        cultural_abstention = None
        abstention_reason = None

    final_unmapped: list[
        dict[str, Any]
    ] = []

    for item in unmapped_raw:
        local_component_id = (
            item[
                "component_local_id"
            ]
        )

        final_unmapped.append(
            {
                "component_id":
                    component_id_map[
                        local_component_id
                    ],

                "evidence_refs": [
                    evidence_id_map[
                        (
                            local_component_id,
                            ref,
                        )
                    ]

                    for ref
                    in item[
                        "evidence_refs"
                    ]
                ],

                "observed_content":
                    item[
                        "observable_cue"
                    ],

                "status":
                    item[
                        "status"
                    ],

                "note":
                    item[
                        "note"
                    ],
            }
        )

    record = _base_record(
        run_status=
            run_status,

        run_metadata=
            run_metadata,

        te_metadata=
            te_metadata,

        components=
            final_components,

        assertions=
            final_assertions,

        facet_summaries=
            facet_summaries,

        cultural_abstention=
            cultural_abstention,

        abstention_reason=
            abstention_reason,

        unmapped=
            final_unmapped,

        raw_output_schema_valid=
            True,

        evidence_valid=
            evidence_valid,

        ambiguity_count=
            ambiguity_count,

        validation_errors=
            validation_errors,
    )

    return _validate_final_record(
        record
    )