"""Deterministic criterion-tree evaluation and the Evidence Floor.

The model may retrieve a policy clause or draft prose, but this module decides
boolean criterion satisfaction and validates that every supported claim points
to evidence observations returned by the Evidence Miner.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, cast

from .state_machine import EvidenceRef


JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
HASH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class CriterionValidationError(ValueError):
    """Raised when a criterion tree is malformed or untraceable."""


class EvidenceFloorViolation(ValueError):
    """Raised when a draft claim exceeds the surfaced evidence."""


class CriterionLogic(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    LEAF = "LEAF"


class EvidenceDisposition(str, Enum):
    SATISFIED = "satisfied"
    CONTRADICTED = "contradicted"
    ABSENT = "absent"


class CriterionStatus(str, Enum):
    SATISFIED = "satisfied"
    CONTRADICTED = "contradicted"
    ABSENT = "absent"
    CONFLICTED = "conflicted"


ClaimKind = Literal["supported", "absence", "contradiction"]


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise CriterionValidationError(f"{label} must not be empty")
    return value


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise CriterionValidationError(f"{label} must be an object")
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str):
        raise CriterionValidationError(f"{label} must be a string")
    return value


def _integer(value: JsonValue | None, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CriterionValidationError(f"{label} must be an integer")
    return value


def _strings(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CriterionValidationError(f"{label} must be an array")
    return tuple(_string(item, f"{label}[{index}]") for index, item in enumerate(value))


@dataclass(frozen=True)
class SourceSpan:
    source_hash: str
    start_offset: int
    end_offset: int
    quote: str

    def __post_init__(self) -> None:
        if not HASH_PATTERN.fullmatch(self.source_hash):
            raise CriterionValidationError("source_hash must be a lowercase SHA-256")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise CriterionValidationError("source offsets must describe a non-empty span")
        _require(self.quote, "verbatim quote")

    @classmethod
    def from_json(cls, document: JsonObject) -> "SourceSpan":
        return cls(
            source_hash=_string(document.get("source_hash"), "source_span.source_hash"),
            start_offset=_integer(document.get("start_offset"), "source_span.start_offset"),
            end_offset=_integer(document.get("end_offset"), "source_span.end_offset"),
            quote=_string(document.get("quote"), "source_span.quote"),
        )


@dataclass(frozen=True)
class PolicyCriterion:
    policy_id: str
    payer: str
    section_ref: str
    cpt_codes: tuple[str, ...]
    effective_date: str
    criterion_id: str
    text: str
    logic: CriterionLogic
    children: tuple["PolicyCriterion", ...]
    satisfied_by: tuple[str, ...]
    source_hash: str
    source_span: SourceSpan

    def __post_init__(self) -> None:
        for value, label in [
            (self.policy_id, "policy_id"),
            (self.payer, "payer"),
            (self.section_ref, "section_ref"),
            (self.effective_date, "effective_date"),
            (self.criterion_id, "criterion_id"),
            (self.text, "criterion text"),
        ]:
            _require(value, label)
        if not HASH_PATTERN.fullmatch(self.source_hash):
            raise CriterionValidationError("criterion source_hash must be a lowercase SHA-256")
        if self.source_span.source_hash != self.source_hash:
            raise CriterionValidationError("criterion source_hash must match source_span.source_hash")
        if self.logic is CriterionLogic.LEAF and self.children:
            raise CriterionValidationError("LEAF criteria cannot have children")
        if self.logic in {CriterionLogic.AND, CriterionLogic.OR} and len(self.children) < 2:
            raise CriterionValidationError(f"{self.logic.value} criteria require at least two children")
        if self.logic is CriterionLogic.NOT and len(self.children) != 1:
            raise CriterionValidationError("NOT criteria require exactly one child")
        if self.logic is CriterionLogic.LEAF and not self.satisfied_by:
            raise CriterionValidationError("LEAF criteria must declare evidence types")

    def to_json(self) -> JsonObject:
        return {
            "policy_id": self.policy_id,
            "payer": self.payer,
            "section_ref": self.section_ref,
            "cpt_codes": list(self.cpt_codes),
            "effective_date": self.effective_date,
            "criterion_id": self.criterion_id,
            "text": self.text,
            "logic": self.logic.value,
            "children": [child.to_json() for child in self.children],
            "satisfied_by": list(self.satisfied_by),
            "source_hash": self.source_hash,
            "source_span": {
                "source_hash": self.source_span.source_hash,
                "start_offset": self.source_span.start_offset,
                "end_offset": self.source_span.end_offset,
                "quote": self.source_span.quote,
            },
        }

    @classmethod
    def from_json(cls, document: JsonObject) -> "PolicyCriterion":
        logic_text = _string(document.get("logic"), "criterion.logic")
        try:
            logic = CriterionLogic(logic_text)
        except ValueError as error:
            raise CriterionValidationError(f"unknown criterion logic: {logic_text}") from error
        children_value = document.get("children")
        if not isinstance(children_value, list):
            raise CriterionValidationError("criterion.children must be an array")
        source_span_value = _object(document.get("source_span"), "criterion.source_span")
        return cls(
            policy_id=_string(document.get("policy_id"), "criterion.policy_id"),
            payer=_string(document.get("payer"), "criterion.payer"),
            section_ref=_string(document.get("section_ref"), "criterion.section_ref"),
            cpt_codes=_strings(document.get("cpt_codes"), "criterion.cpt_codes"),
            effective_date=_string(document.get("effective_date"), "criterion.effective_date"),
            criterion_id=_string(document.get("criterion_id"), "criterion.criterion_id"),
            text=_string(document.get("text"), "criterion.text"),
            logic=logic,
            children=tuple(
                cls.from_json(_object(child, f"criterion.children[{index}]"))
                for index, child in enumerate(children_value)
            ),
            satisfied_by=_strings(document.get("satisfied_by"), "criterion.satisfied_by"),
            source_hash=_string(document.get("source_hash"), "criterion.source_hash"),
            source_span=SourceSpan.from_json(source_span_value),
        )

    def fingerprint(self) -> str:
        serialized = json.dumps(self.to_json(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceObservation:
    observation_id: str
    leaf_criterion_id: str
    disposition: EvidenceDisposition
    evidence_type: str
    references: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        for value, label in [
            (self.observation_id, "observation_id"),
            (self.leaf_criterion_id, "leaf_criterion_id"),
            (self.evidence_type, "evidence_type"),
        ]:
            _require(value, label)
        if self.disposition in {EvidenceDisposition.SATISFIED, EvidenceDisposition.CONTRADICTED} and not self.references:
            raise EvidenceFloorViolation(f"{self.disposition.value} observation requires a FHIR evidence reference")
        if self.disposition is EvidenceDisposition.ABSENT and self.references:
            raise EvidenceFloorViolation("absent observation cannot carry a supporting FHIR reference")


@dataclass(frozen=True)
class CriterionEvaluation:
    criterion_id: str
    status: CriterionStatus
    evidence_refs: tuple[EvidenceRef, ...]
    children: tuple["CriterionEvaluation", ...]


@dataclass(frozen=True)
class DraftClaim:
    claim_id: str
    criterion_id: str
    text: str
    kind: ClaimKind
    observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in [(self.claim_id, "claim_id"), (self.criterion_id, "criterion_id"), (self.text, "claim text")]:
            _require(value, label)
        if not self.observation_ids:
            raise EvidenceFloorViolation("every claim must name at least one Evidence Miner observation")


def _index_criteria(root: PolicyCriterion) -> dict[str, PolicyCriterion]:
    index: dict[str, PolicyCriterion] = {}

    def visit(node: PolicyCriterion) -> None:
        if node.criterion_id in index:
            raise CriterionValidationError(f"duplicate criterion_id: {node.criterion_id}")
        index[node.criterion_id] = node
        for child in node.children:
            visit(child)

    visit(root)
    return index


def _leaf_ids(node: PolicyCriterion) -> set[str]:
    if node.logic is CriterionLogic.LEAF:
        return {node.criterion_id}
    result: set[str] = set()
    for child in node.children:
        result.update(_leaf_ids(child))
    return result


def _merge_refs(evaluations: tuple[CriterionEvaluation, ...]) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str]] = set()
    merged: list[EvidenceRef] = []
    for evaluation in evaluations:
        for ref in evaluation.evidence_refs:
            key = (ref.kind, ref.uri)
            if key not in seen:
                seen.add(key)
                merged.append(ref)
    return tuple(merged)


def _combine(logic: CriterionLogic, children: tuple[CriterionEvaluation, ...]) -> CriterionStatus:
    statuses = [child.status for child in children]
    if CriterionStatus.CONFLICTED in statuses:
        return CriterionStatus.CONFLICTED
    if logic is CriterionLogic.AND:
        if CriterionStatus.CONTRADICTED in statuses:
            return CriterionStatus.CONTRADICTED
        if CriterionStatus.ABSENT in statuses:
            return CriterionStatus.ABSENT
        return CriterionStatus.SATISFIED
    if logic is CriterionLogic.OR:
        if CriterionStatus.SATISFIED in statuses:
            return CriterionStatus.SATISFIED
        if all(status is CriterionStatus.CONTRADICTED for status in statuses):
            return CriterionStatus.CONTRADICTED
        return CriterionStatus.ABSENT
    if logic is CriterionLogic.NOT:
        child_status = statuses[0]
        if child_status is CriterionStatus.SATISFIED:
            return CriterionStatus.CONTRADICTED
        if child_status is CriterionStatus.CONTRADICTED:
            return CriterionStatus.SATISFIED
        return CriterionStatus.ABSENT
    raise CriterionValidationError(f"cannot combine LEAF node with {len(children)} children")


def evaluate_criterion(root: PolicyCriterion, observations: tuple[EvidenceObservation, ...]) -> CriterionEvaluation:
    """Evaluate the exact boolean tree; absent evidence never becomes satisfied."""

    index = _index_criteria(root)
    observations_by_leaf: dict[str, list[EvidenceObservation]] = {}
    observation_ids: set[str] = set()
    for observation in observations:
        if observation.observation_id in observation_ids:
            raise CriterionValidationError(f"duplicate observation_id: {observation.observation_id}")
        observation_ids.add(observation.observation_id)
        if observation.leaf_criterion_id not in index:
            raise CriterionValidationError(f"observation references unknown criterion: {observation.leaf_criterion_id}")
        if index[observation.leaf_criterion_id].logic is not CriterionLogic.LEAF:
            raise CriterionValidationError("evidence observations must reference LEAF criteria")
        observations_by_leaf.setdefault(observation.leaf_criterion_id, []).append(observation)

    def visit(node: PolicyCriterion) -> CriterionEvaluation:
        if node.logic is CriterionLogic.LEAF:
            leaf_observations = observations_by_leaf.get(node.criterion_id, [])
            if not leaf_observations:
                return CriterionEvaluation(node.criterion_id, CriterionStatus.ABSENT, (), ())
            dispositions = [item.disposition for item in leaf_observations]
            refs = tuple(ref for item in leaf_observations for ref in item.references)
            if EvidenceDisposition.SATISFIED in dispositions and EvidenceDisposition.CONTRADICTED in dispositions:
                status = CriterionStatus.CONFLICTED
            elif EvidenceDisposition.SATISFIED in dispositions:
                status = CriterionStatus.SATISFIED
            elif EvidenceDisposition.CONTRADICTED in dispositions:
                status = CriterionStatus.CONTRADICTED
            else:
                status = CriterionStatus.ABSENT
            return CriterionEvaluation(node.criterion_id, status, refs, ())
        children = tuple(visit(child) for child in node.children)
        return CriterionEvaluation(node.criterion_id, _combine(node.logic, children), _merge_refs(children), children)

    return visit(root)


def validate_claims(
    root: PolicyCriterion,
    evaluation: CriterionEvaluation,
    observations: tuple[EvidenceObservation, ...],
    claims: tuple[DraftClaim, ...],
) -> tuple[DraftClaim, ...]:
    """Enforce the Evidence Floor for claims proposed by a drafting model."""

    index = _index_criteria(root)
    by_id = {observation.observation_id: observation for observation in observations}
    evaluations: dict[str, CriterionEvaluation] = {}

    def index_evaluation(item: CriterionEvaluation) -> None:
        evaluations[item.criterion_id] = item
        for child in item.children:
            index_evaluation(child)

    index_evaluation(evaluation)
    seen_claim_ids: set[str] = set()
    for claim in claims:
        if claim.claim_id in seen_claim_ids:
            raise EvidenceFloorViolation(f"duplicate claim_id: {claim.claim_id}")
        seen_claim_ids.add(claim.claim_id)
        node = index.get(claim.criterion_id)
        criterion_evaluation = evaluations.get(claim.criterion_id)
        if node is None or criterion_evaluation is None:
            raise EvidenceFloorViolation(f"claim references unknown criterion: {claim.criterion_id}")
        allowed_leaf_ids = _leaf_ids(node)
        selected: list[EvidenceObservation] = []
        for observation_id in claim.observation_ids:
            observation = by_id.get(observation_id)
            if observation is None:
                raise EvidenceFloorViolation(f"claim {claim.claim_id} references unknown observation: {observation_id}")
            if observation.leaf_criterion_id not in allowed_leaf_ids:
                raise EvidenceFloorViolation(f"claim {claim.claim_id} cites evidence outside its criterion subtree")
            selected.append(observation)
        dispositions = {observation.disposition for observation in selected}
        if claim.kind == "supported":
            if dispositions != {EvidenceDisposition.SATISFIED} or criterion_evaluation.status is not CriterionStatus.SATISFIED:
                raise EvidenceFloorViolation(f"claim {claim.claim_id} asserts support the deterministic tree does not establish")
        elif claim.kind == "absence":
            if dispositions != {EvidenceDisposition.ABSENT} or criterion_evaluation.status is not CriterionStatus.ABSENT:
                raise EvidenceFloorViolation(f"claim {claim.claim_id} asserts absence the Evidence Miner did not establish")
        elif claim.kind == "contradiction":
            if dispositions != {EvidenceDisposition.CONTRADICTED} or criterion_evaluation.status is not CriterionStatus.CONTRADICTED:
                raise EvidenceFloorViolation(f"claim {claim.claim_id} asserts contradiction the deterministic tree does not establish")
        else:
            raise EvidenceFloorViolation(f"unknown claim kind: {claim.kind}")
    return claims
