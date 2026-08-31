"""Versioned evaluation contracts and deterministic scoring for Appeal."""

from .contracts import (
    SCHEMA_VERSION,
    AppealCasePackage,
    AppealPrediction,
    EvaluationTask,
    EvidenceLabel,
    SourceCapabilities,
    SourceClass,
)
from .scoring import EvaluationReport, MetricResult, evaluate_predictions, wilson_interval
from .annotations import (
    AnnotationDisposition,
    CaseAnnotation,
    OperationalRoute,
    RationaleCategory,
    SourceSpanLabel,
    requires_adjudication,
    route_for,
)

__all__ = [
    "SCHEMA_VERSION",
    "AppealCasePackage",
    "AppealPrediction",
    "AnnotationDisposition",
    "CaseAnnotation",
    "EvaluationReport",
    "EvaluationTask",
    "EvidenceLabel",
    "MetricResult",
    "OperationalRoute",
    "RationaleCategory",
    "SourceCapabilities",
    "SourceClass",
    "SourceSpanLabel",
    "evaluate_predictions",
    "requires_adjudication",
    "route_for",
    "wilson_interval",
]
