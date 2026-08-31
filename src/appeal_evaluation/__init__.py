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

__all__ = [
    "SCHEMA_VERSION",
    "AppealCasePackage",
    "AppealPrediction",
    "EvaluationReport",
    "EvaluationTask",
    "EvidenceLabel",
    "MetricResult",
    "SourceCapabilities",
    "SourceClass",
    "evaluate_predictions",
    "wilson_interval",
]
