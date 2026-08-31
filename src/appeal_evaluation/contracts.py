"""Source-aware contracts for reproducible Appeal evaluation.

The contracts intentionally distinguish regulator summaries, reconstructed
cases, composite operating cases, and authorized complete denial packages.
Each source declares the tasks its fields can support; scoring rejects any task
outside that declaration rather than manufacturing a denominator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final


SCHEMA_VERSION: Final[str] = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceClass(str, Enum):
    REGULATOR_SUMMARY = "regulator_summary"
    RECONSTRUCTED_PUBLIC_CASE = "reconstructed_public_case"
    COMPOSITE_EVALUATION_CASE = "composite_evaluation_case"
    AUTHORIZED_COMPLETE_DENIAL = "authorized_complete_denial"


class EvaluationTask(str, Enum):
    APPEAL_TYPE = "appeal_type"
    REQUESTED_ITEM_CLASS = "requested_item_class"
    DENIAL_REASON = "denial_reason"
    COVERAGE_RULES = "coverage_rules"
    POLICY_CRITERIA = "policy_criteria"
    EVIDENCE_SELECTION = "evidence_selection"
    MISSING_EVIDENCE = "missing_evidence"
    ROUTE = "route"
    REGULATOR_OUTCOME = "regulator_outcome"
    CLAIM_SUPPORT = "claim_support"


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")


def _require_hash(value: str, label: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")


def _unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")
    for value in values:
        _require_text(value, label)


@dataclass(frozen=True)
class SourceCapabilities:
    source_id: str
    source_class: SourceClass
    supported_tasks: frozenset[EvaluationTask]
    complete_denial_package: bool = False
    clinical_ground_truth: bool = False

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        if self.clinical_ground_truth and not self.complete_denial_package:
            raise ValueError("clinical ground truth requires a complete denial package")
        if self.source_class is SourceClass.REGULATOR_SUMMARY and self.complete_denial_package:
            raise ValueError("a regulator summary cannot be a complete denial package")

    def require(self, task: EvaluationTask) -> None:
        if task not in self.supported_tasks:
            raise ValueError(f"source {self.source_id} does not support task {task.value}")


@dataclass(frozen=True)
class EvidenceLabel:
    evidence_ref: str
    criterion_id: str
    disposition: str

    def __post_init__(self) -> None:
        _require_text(self.evidence_ref, "evidence_ref")
        _require_text(self.criterion_id, "criterion_id")
        if self.disposition not in {"satisfied", "contradicted", "absent", "conflicted"}:
            raise ValueError(f"unsupported evidence disposition: {self.disposition}")


@dataclass(frozen=True)
class AppealCasePackage:
    case_ref: str
    source_id: str
    source_class: SourceClass
    source_fingerprint: str
    split: str
    allowed_tasks: frozenset[EvaluationTask]
    appeal_type: str | None = None
    requested_item_class: str | None = None
    denial_reason: str | None = None
    coverage_rule_ids: tuple[str, ...] = ()
    policy_criterion_ids: tuple[str, ...] = ()
    evidence_labels: tuple[EvidenceLabel, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    route: str | None = None
    regulator_outcome: str | None = None
    supported_claim_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.case_ref, "case_ref")
        _require_text(self.source_id, "source_id")
        _require_hash(self.source_fingerprint, "source_fingerprint")
        if self.split not in {"development", "validation", "locked_test"}:
            raise ValueError(f"unsupported split: {self.split}")
        _unique(self.coverage_rule_ids, "coverage_rule_ids")
        _unique(self.policy_criterion_ids, "policy_criterion_ids")
        _unique(self.missing_evidence_ids, "missing_evidence_ids")
        _unique(self.supported_claim_ids, "supported_claim_ids")

    def require_compatible(self, capabilities: SourceCapabilities) -> None:
        if self.source_id != capabilities.source_id or self.source_class is not capabilities.source_class:
            raise ValueError(f"case {self.case_ref} does not match source capabilities")
        unsupported = self.allowed_tasks - capabilities.supported_tasks
        if unsupported:
            names = ", ".join(sorted(task.value for task in unsupported))
            raise ValueError(f"case {self.case_ref} declares unsupported tasks: {names}")


@dataclass(frozen=True)
class AppealPrediction:
    case_ref: str
    model_fingerprint: str
    policy_fingerprint: str
    code_revision: str
    appeal_type: str | None = None
    requested_item_class: str | None = None
    denial_reason: str | None = None
    coverage_rule_ids: tuple[str, ...] = ()
    policy_criterion_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    route: str | None = None
    regulator_outcome: str | None = None
    supported_claim_ids: tuple[str, ...] = ()
    unsupported_claim_ids: tuple[str, ...] = ()
    abstained_tasks: frozenset[EvaluationTask] = frozenset()
    latency_ms: int = 0

    def __post_init__(self) -> None:
        _require_text(self.case_ref, "case_ref")
        _require_hash(self.model_fingerprint, "model_fingerprint")
        _require_hash(self.policy_fingerprint, "policy_fingerprint")
        _require_text(self.code_revision, "code_revision")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        _unique(self.coverage_rule_ids, "coverage_rule_ids")
        _unique(self.policy_criterion_ids, "policy_criterion_ids")
        _unique(self.evidence_refs, "evidence_refs")
        _unique(self.missing_evidence_ids, "missing_evidence_ids")
        _unique(self.supported_claim_ids, "supported_claim_ids")
        _unique(self.unsupported_claim_ids, "unsupported_claim_ids")
        if set(self.supported_claim_ids) & set(self.unsupported_claim_ids):
            raise ValueError("a claim cannot be both supported and unsupported")
