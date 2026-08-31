"""Outcome-blinded annotation contracts for regulator-summary evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RationaleCategory(str, Enum):
    NON_FORMULARY_EXCEPTION = "non_formulary_exception"
    TIERING_EXCEPTION = "tiering_exception"
    PRIOR_AUTHORIZATION = "prior_authorization"
    STEP_THERAPY = "step_therapy"
    QUANTITY_LIMIT = "quantity_limit"
    MEDICALLY_ACCEPTED_INDICATION = "medically_accepted_indication"
    PAYMENT_OR_COST_SHARING = "payment_or_cost_sharing"
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
    REQUEST_ADDITIONAL_INFORMATION = "request_additional_information"


class AnnotationDisposition(str, Enum):
    ANNOTATED = "annotated"
    ABSTAINED = "abstained"


@dataclass(frozen=True)
class SourceSpanLabel:
    source_field: str
    start: int
    end: int
    source_sha256: str

    def __post_init__(self) -> None:
        if self.source_field not in {"decision_rationale", "policy_context"}:
            raise ValueError("annotation spans must reference rationale or policy context")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("annotation span offsets must be non-empty")
        if _SHA256.fullmatch(self.source_sha256) is None:
            raise ValueError("annotation source hash must be a lowercase SHA-256")


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
        if not self.blinded_to_outcome:
            raise ValueError("benchmark annotations must be blinded to regulator outcome")
        if not 1 <= self.confidence <= 5:
            raise ValueError("annotation confidence must be between 1 and 5")
        if len(self.secondary_categories) != len(set(self.secondary_categories)):
            raise ValueError("secondary categories must not contain duplicates")
        if self.primary_category in self.secondary_categories:
            raise ValueError("primary category cannot also be secondary")
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
    )
