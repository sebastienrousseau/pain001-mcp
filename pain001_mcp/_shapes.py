# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Result shapes: the TypedDicts every tool's output schema comes from.

Every tool returns a JSON object, and any tool can answer with
``{"error": "..."}`` instead of its payload (ADR 0001: errors as data), so
each shape lists the payload keys plus ``error`` and marks all of them
optional. The MCP SDK derives the tool's outputSchema from these, which is
what an agent reads to know the keys before it calls; the exact keys and
wording are pinned by tests/test_tool_result_shapes.py.
"""

from typing import Any

# pydantic resolves nested TypedDicts on Python 3.11 only for the
# typing_extensions class; typing.TypedDict there yields no output schema.
from typing_extensions import TypedDict


class ErrorResult(TypedDict, total=False):
    """The failure payload every tool may return instead of its result."""

    error: str


class SchemaResult(TypedDict, total=False):
    """A JSON Schema (draft 7) for one message type's flat records."""

    error: str
    title: str
    description: str
    type: str
    properties: dict[str, Any]
    required: list[str]
    additionalProperties: bool
    version: str


class RecordError(TypedDict):
    """One schema violation: the record's row, the field path, the message."""

    row: int
    path: str
    message: str


class ValidateRecordsResult(TypedDict, total=False):
    """Verdict over a batch: one entry per violation, plus the counts."""

    error: str
    valid: bool
    total: int
    valid_count: int
    errors: list[RecordError]


class ValidateIdentifierResult(TypedDict, total=False):
    """An IBAN or BIC verdict, with the library's message when invalid."""

    error: str
    kind: str
    value: str
    valid: bool


class Camt053Result(TypedDict, total=False):
    """A parsed camt.053: the first statement's fields, and every one."""

    error: str
    statement_id: str
    electronic_sequence_number: str
    iban: str
    currency: str
    entries: list[dict[str, Any]]
    statements: list[dict[str, Any]]


class Pain002Result(TypedDict, total=False):
    """A parsed pain.002 status report, as the core library reports it."""

    error: str
    message_id: str
    creation_datetime: str
    original_message_id: str
    original_message_name_id: str
    group_status: str
    payment_statuses: list[dict[str, Any]]


class TemplateResult(TypedDict, total=False):
    """The bundled CSV template's column names for one message type."""

    error: str
    message_type: str
    columns: list[str]


class SchemeViolation(TypedDict):
    """One rulebook violation, with the remediation the library suggests."""

    rule: str
    field: str
    index: int
    message: str
    remediation: str
    severity: str


class SchemeResult(TypedDict, total=False):
    """Verdict against a scheme rulebook profile."""

    error: str
    profile: str
    is_valid: bool
    violations: list[SchemeViolation]


class DuplicateTransaction(TypedDict):
    """An intra-batch duplicate payment transaction."""

    row: int
    matching_row: int
    debtor_account_IBAN: str
    creditor_account_IBAN: str
    amount: str
    currency: str
    requested_execution_date: str


class SimulatePaymentBatchResult(TypedDict, total=False):
    """Simulation and pre-flight verdict over a payment batch."""

    error: str
    valid: bool
    total: int
    valid_count: int
    control_sum_by_currency: dict[str, str]
    unique_debtors: int
    unique_creditors: int
    duplicates: list[DuplicateTransaction]
    schema_errors: list[RecordError]
    scheme_violations: list[SchemeViolation]


MigrateResult = TypedDict(
    "MigrateResult",
    {
        "error": str,
        "records": list[dict[str, Any]],
        "migrated": int,
        "from": str,
        "to": str,
    },
    total=False,
)
MigrateResult.__doc__ = (
    "Records rewritten from one message edition to another."
)


class XsdResult(TypedDict, total=False):
    """Verdict of an XML document against the official XSD."""

    error: str
    valid: bool
    message_type: str


class SanitiseResult(TypedDict, total=False):
    """A value and its ISO 20022 charset-clean rendering."""

    value: str
    sanitised: str
    was_valid: bool
    changed: bool


class CorpusFileEntry(TypedDict, total=False):
    """One file of the example corpus, as the index lists it.

    Market files name a scenario, a country and a rail family; coverage
    files carry the edition only, so those three are null for them.
    """

    scenario_id: str | None
    version: str
    variant: str | None
    kind: str
    file: str
    country: str | None
    family: str | None


class CorpusListResult(TypedDict, total=False):
    """The example corpus index."""

    error: str
    count: int
    files: list[CorpusFileEntry]


class CorpusFileResult(TypedDict, total=False):
    """One corpus XML file with the request echoed beside it."""

    error: str
    scenario_id: str
    version: str
    variant: str | None
    xml: str


class CorpusProvenanceResult(TypedDict, total=False):
    """A scenario's provenance record, as the corpus ships it."""

    error: str
    scenario: str
    message_type: str
    variant: str | None
    country: str
    family: str
    description: str
    sha256: str
    provenance: dict[str, Any]
    validation: dict[str, Any]
    constraints: list[Any]
    twins: dict[str, Any]
    build: dict[str, Any]


class CoverageCount(TypedDict):
    """Declared schema elements, how many the corpus hits, as a percentage."""

    declared: int
    hit: int
    percent: float


class CorpusCoverageResult(TypedDict, total=False):
    """Schema-path coverage of the corpus for one message edition."""

    error: str
    message_type: str
    complete: bool
    sources: list[Any]
    files: list[dict[str, Any]]
    paths: CoverageCount
    branches: CoverageCount
    missing_paths: list[str]
    missing_branches: list[str]
    exempt: list[str]
    unknown: list[str]


class StagedBatchResult(TypedDict, total=False):
    """Result of staging a payment batch for simulation and approval."""

    error: str
    stage_id: str
    sha256_fingerprint: str
    total_transactions: int
    control_sum_by_currency: dict[str, str]
    estimated_fees: dict[str, str]
    risk_score: int
    risk_level: str
    risk_factors: list[str]
    status: str
    confirmation_token: str
    expires_at: str


class ClearingCheck(TypedDict):
    """An individual rule check during clearing simulation."""

    check: str
    status: str
    detail: str


class SimulateClearingResult(TypedDict, total=False):
    """Clearing network simulation verdict and settlement estimation."""

    error: str
    stage_id: str
    clearing_system: str
    clearing_status: str
    settlement_window: str
    checks: list[ClearingCheck]


class CommitPaymentBatchResult(TypedDict, total=False):
    """Confirmation of authorized payment batch commit."""

    error: str
    stage_id: str
    status: str
    sha256_fingerprint: str
    total_transactions: int
    output_file_path: str | None
    committed_at: str


class SchemeProfileEntry(TypedDict):
    """One scheme profile: its name, what it checks, and where from.

    ``rule_prefix`` begins every rule id a rail profile reports (``UK-FPS``
    for ``UK-FPS-AMT``); it is null for the other profiles, whose rule ids
    the core does not group under one prefix. ``sources`` are the public
    documents a rail or purpose mandate was built from, empty otherwise.
    """

    name: str
    description: str
    rule_prefix: str | None
    sources: list[str]


class SchemeProfilesResult(TypedDict, total=False):
    """Every scheme profile the core ships, in name order."""

    error: str
    count: int
    profiles: list[SchemeProfileEntry]
