"""Outcome-blinded annotation contracts for regulator-summary evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NON_HUMAN_ROLE_TOKENS: Final[frozenset[str]] = frozenset(
    {"ai", "agent", "assistant", "gemini", "llm", "model", "system"}
)


class RationaleCategory(str, Enum):
    NON_FORMULARY_EXCEPTION = "non_formulary_exception"
    TIERING_EXCEPTION = "tiering_exception"
    PRIOR_AUTHORIZATION = "prior_authorization"
    STEP_THERAPY = "step_therapy"
    QUANTITY_LIMIT = "quantity_limit"
    MEDICALLY_ACCEPTED_INDICATION = "medically_accepted_indication"
    PAYMENT_OR_COST_SHARING = "payment_or_cost_sharing"
    COVERAGE_EXCLUSION = "coverage_exclusion"
    PART_B_PART_D_COORDINATION = "part_b_part_d_coordination"
    AT_RISK_DRUG_MANAGEMENT = "at_risk_drug_management"
    PROCEDURAL_OR_JURISDICTIONAL = "procedural_or_jurisdictional"
    OTHER_COVERAGE_RULE = "other_coverage_rule"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class OperationalRoute(str, Enum):
    FORMULARY_EXCEPTION_REVIEW = "formulary_exception_review"
    UTILIZATION_MANAGEMENT_EXCEPTION = "utilization_management_exception"
    MEDICALLY_ACCEPTED_INDICATION_REVIEW = "medically_accepted_indication_review"
    PAYMENT_APPEAL = "payment_appeal"
    AUTOMATIC_IRE_REVIEW = "automatic_ire_review"
    PROCEDURAL_HUMAN_REVIEW = "procedural_human_review"
    COVERAGE_RULE_REVIEW = "coverage_rule_review"
    BENEFIT_COORDINATION_REVIEW = "benefit_coordination_review"
    REQUEST_ADDITIONAL_INFORMATION = "request_additional_information"


class AnnotationDisposition(str, Enum):
    ANNOTATED = "annotated"
    ABSTAINED = "abstained"


class GoldResolution(str, Enum):
    CONSENSUS = "consensus"
    ADJUDICATED = "adjudicated"


class SpanRole(str, Enum):
    OPERATIVE_HOLDING = "operative_holding"
    POLICY_CONTEXT = "policy_context"


@dataclass(frozen=True)
class SourceSpanLabel:
    source_field: str
    start: int
    end: int
    source_sha256: str
    span_role: SpanRole = SpanRole.OPERATIVE_HOLDING

    def __post_init__(self) -> None:
        if self.source_field not in {"decision_rationale", "policy_context"}:
            raise ValueError("annotation spans must reference rationale or policy context")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("annotation span offsets must be non-empty")
        if _SHA256.fullmatch(self.source_sha256) is None:
            raise ValueError("annotation source hash must be a lowercase SHA-256")
        expected_role = (
            SpanRole.OPERATIVE_HOLDING
            if self.source_field == "decision_rationale"
            else SpanRole.POLICY_CONTEXT
        )
        if self.span_role is not expected_role:
            raise ValueError("annotation span role does not match its source field")


@dataclass(frozen=True)
class CaseAnnotation:
    case_ref: str
    taxonomy_version: str
    annotator_id: str
    annotator_role: str
    blinded_to_outcome: bool
    disposition: AnnotationDisposition
    primary_category: RationaleCategory
    secondary_categories: tuple[RationaleCategory, ...]
    route: OperationalRoute
    rationale_spans: tuple[SourceSpanLabel, ...]
    policy_spans: tuple[SourceSpanLabel, ...]
    confidence: int
    adjudication_required: bool = False

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.case_ref) is None:
            raise ValueError("annotation case_ref must be a lowercase SHA-256")
        if not self.taxonomy_version.strip() or not self.annotator_id.strip() or not self.annotator_role.strip():
            raise ValueError("annotation identity and taxonomy version are required")
        role_tokens = set(re.findall(r"[a-z0-9]+", self.annotator_role.casefold()))
        if role_tokens & _NON_HUMAN_ROLE_TOKENS:
            raise ValueError("gold annotations must be authored by a human reviewer")
        if not self.blinded_to_outcome:
            raise ValueError("benchmark annotations must be blinded to regulator outcome")
        if not 1 <= self.confidence <= 5:
            raise ValueError("annotation confidence must be between 1 and 5")
        if len(self.secondary_categories) != len(set(self.secondary_categories)):
            raise ValueError("secondary categories must not contain duplicates")
        if self.primary_category in self.secondary_categories:
            raise ValueError("primary category cannot also be secondary")
        if RationaleCategory.INSUFFICIENT_INFORMATION in self.secondary_categories:
            raise ValueError("insufficient_information cannot be a secondary category")
        if self.route is not route_for(self.primary_category):
            raise ValueError("route does not match the frozen taxonomy policy")
        if self.disposition is AnnotationDisposition.ABSTAINED:
            if self.primary_category is not RationaleCategory.INSUFFICIENT_INFORMATION:
                raise ValueError("abstention requires insufficient_information")
            if self.route is not OperationalRoute.REQUEST_ADDITIONAL_INFORMATION:
                raise ValueError("abstention must request additional information")
        elif not self.rationale_spans and not self.policy_spans:
            raise ValueError("an annotated category requires at least one source span")


ROUTE_POLICY: dict[RationaleCategory, OperationalRoute] = {
    RationaleCategory.NON_FORMULARY_EXCEPTION: OperationalRoute.FORMULARY_EXCEPTION_REVIEW,
    RationaleCategory.TIERING_EXCEPTION: OperationalRoute.FORMULARY_EXCEPTION_REVIEW,
    RationaleCategory.PRIOR_AUTHORIZATION: OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
    RationaleCategory.STEP_THERAPY: OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
    RationaleCategory.QUANTITY_LIMIT: OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
    RationaleCategory.MEDICALLY_ACCEPTED_INDICATION: OperationalRoute.MEDICALLY_ACCEPTED_INDICATION_REVIEW,
    RationaleCategory.PAYMENT_OR_COST_SHARING: OperationalRoute.PAYMENT_APPEAL,
    RationaleCategory.COVERAGE_EXCLUSION: OperationalRoute.COVERAGE_RULE_REVIEW,
    RationaleCategory.PART_B_PART_D_COORDINATION: OperationalRoute.BENEFIT_COORDINATION_REVIEW,
    RationaleCategory.AT_RISK_DRUG_MANAGEMENT: OperationalRoute.AUTOMATIC_IRE_REVIEW,
    RationaleCategory.PROCEDURAL_OR_JURISDICTIONAL: OperationalRoute.PROCEDURAL_HUMAN_REVIEW,
    RationaleCategory.OTHER_COVERAGE_RULE: OperationalRoute.COVERAGE_RULE_REVIEW,
    RationaleCategory.INSUFFICIENT_INFORMATION: OperationalRoute.REQUEST_ADDITIONAL_INFORMATION,
}


def route_for(category: RationaleCategory) -> OperationalRoute:
    return ROUTE_POLICY[category]


def requires_adjudication(first: CaseAnnotation, second: CaseAnnotation) -> bool:
    if first.case_ref != second.case_ref or first.taxonomy_version != second.taxonomy_version:
        raise ValueError("annotations must describe the same case and taxonomy version")
    return (
        first.disposition is not second.disposition
        or first.primary_category is not second.primary_category
        or first.route is not second.route
        or set(first.secondary_categories) != set(second.secondary_categories)
        or _span_signature(first.rationale_spans) != _span_signature(second.rationale_spans)
        or _span_signature(first.policy_spans) != _span_signature(second.policy_spans)
    )


def annotation_signature(annotation: CaseAnnotation) -> tuple[object, ...]:
    """Return the label fields that must agree before a consensus is gold."""

    return (
        annotation.disposition,
        annotation.primary_category,
        tuple(sorted(annotation.secondary_categories)),
        annotation.route,
        _span_signature(annotation.rationale_spans),
        _span_signature(annotation.policy_spans),
    )


def _span_signature(spans: tuple[SourceSpanLabel, ...]) -> tuple[tuple[str, int, int, str, str], ...]:
    return tuple(sorted((span.source_field, span.start, span.end, span.source_sha256, span.span_role.value) for span in spans))


@dataclass(frozen=True)
class GoldLabel:
    """A human-only gold label produced from two independent reviews."""

    case_ref: str
    taxonomy_version: str
    independent_annotator_ids: tuple[str, str]
    resolution: GoldResolution
    disposition: AnnotationDisposition
    primary_category: RationaleCategory
    secondary_categories: tuple[RationaleCategory, ...]
    route: OperationalRoute
    rationale_spans: tuple[SourceSpanLabel, ...]
    policy_spans: tuple[SourceSpanLabel, ...]
    confidence: int
    adjudicator_id: str | None = None
    adjudicator_role: str | None = None
    adjudication_note_sha256: str | None = None

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.case_ref) is None:
            raise ValueError("gold case_ref must be a lowercase SHA-256")
        if not self.taxonomy_version.strip():
            raise ValueError("gold taxonomy version is required")
        if len(self.independent_annotator_ids) != 2 or len(set(self.independent_annotator_ids)) != 2:
            raise ValueError("gold labels require two distinct independent annotators")
        if any(not value.strip() for value in self.independent_annotator_ids):
            raise ValueError("gold annotator IDs must not be empty")
        if self.resolution is GoldResolution.ADJUDICATED:
            if not self.adjudicator_id or not self.adjudicator_role or not self.adjudication_note_sha256:
                raise ValueError("adjudicated gold labels require an adjudicator and decision-note hash")
            if _SHA256.fullmatch(self.adjudication_note_sha256) is None:
                raise ValueError("adjudication note hash must be a lowercase SHA-256")
            if self.adjudicator_id in self.independent_annotator_ids:
                raise ValueError("adjudicator must be independent of both reviewers")
            role_tokens = set(re.findall(r"[a-z0-9]+", self.adjudicator_role.casefold()))
            if role_tokens & _NON_HUMAN_ROLE_TOKENS:
                raise ValueError("adjudicated gold labels require a human adjudicator")
        elif any(value is not None for value in (self.adjudicator_id, self.adjudicator_role, self.adjudication_note_sha256)):
            raise ValueError("consensus gold labels must not contain adjudicator metadata")
        if not 1 <= self.confidence <= 5:
            raise ValueError("gold confidence must be between 1 and 5")
        if len(self.secondary_categories) != len(set(self.secondary_categories)):
            raise ValueError("gold secondary categories must not contain duplicates")
        if self.primary_category in self.secondary_categories:
            raise ValueError("gold primary category cannot also be secondary")
        if RationaleCategory.INSUFFICIENT_INFORMATION in self.secondary_categories:
            raise ValueError("gold insufficient_information cannot be a secondary category")
        if self.route is not route_for(self.primary_category):
            raise ValueError("gold route does not match the frozen taxonomy policy")
        if self.disposition is AnnotationDisposition.ABSTAINED:
            if self.primary_category is not RationaleCategory.INSUFFICIENT_INFORMATION:
                raise ValueError("gold abstention requires insufficient_information")
            if self.route is not OperationalRoute.REQUEST_ADDITIONAL_INFORMATION:
                raise ValueError("gold abstention must request additional information")
        elif not self.rationale_spans and not self.policy_spans:
            raise ValueError("annotated gold labels require at least one source span")


def gold_from_consensus(first: CaseAnnotation, second: CaseAnnotation) -> GoldLabel:
    """Create gold only when independent labels agree, including source spans."""

    if first.annotator_id == second.annotator_id:
        raise ValueError("consensus requires distinct annotators")
    if requires_adjudication(first, second):
        raise ValueError("disagreement requires adjudication")
    return GoldLabel(
        case_ref=first.case_ref,
        taxonomy_version=first.taxonomy_version,
        independent_annotator_ids=(first.annotator_id, second.annotator_id),
        resolution=GoldResolution.CONSENSUS,
        disposition=first.disposition,
        primary_category=first.primary_category,
        secondary_categories=first.secondary_categories,
        route=first.route,
        rationale_spans=first.rationale_spans,
        policy_spans=first.policy_spans,
        confidence=min(first.confidence, second.confidence),
    )
