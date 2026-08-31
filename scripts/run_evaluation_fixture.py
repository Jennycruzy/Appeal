#!/usr/bin/env python3
"""Generate a deterministic, network-free evaluation report from a fixture."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from appeal_evaluation import (
    SCHEMA_VERSION,
    AppealCasePackage,
    AppealPrediction,
    EvaluationTask,
    SourceCapabilities,
    SourceClass,
    evaluate_predictions,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_FINGERPRINT = "c" * 64
POLICY_FINGERPRINT = "d" * 64


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(list[Any], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _texts(value: object, label: str) -> tuple[str, ...]:
    return tuple(_text(item, f"{label}[]") for item in _array(value, label))


def load_fixture(path: Path) -> tuple[SourceCapabilities, tuple[AppealCasePackage, ...], tuple[AppealPrediction, ...]]:
    document = _object(json.loads(path.read_text(encoding="utf-8")), "fixture")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"fixture schema_version must be {SCHEMA_VERSION}")
    source = _object(document.get("source"), "source")
    source_id = _text(source.get("source_id"), "source.source_id")
    source_class = SourceClass(_text(source.get("source_class"), "source.source_class"))
    tasks = frozenset(EvaluationTask(value) for value in _texts(source.get("supported_tasks"), "source.supported_tasks"))
    capabilities = SourceCapabilities(source_id, source_class, tasks)

    cases: list[AppealCasePackage] = []
    for index, value in enumerate(_array(document.get("cases"), "cases")):
        item = _object(value, f"cases[{index}]")
        cases.append(
            AppealCasePackage(
                case_ref=_text(item.get("case_ref"), "case_ref"),
                source_id=source_id,
                source_class=source_class,
                source_fingerprint=_text(item.get("source_fingerprint"), "source_fingerprint"),
                split=_text(item.get("split"), "split"),
                allowed_tasks=tasks,
                appeal_type=_optional_text(item.get("appeal_type"), "appeal_type"),
                requested_item_class=_optional_text(item.get("requested_item_class"), "requested_item_class"),
                coverage_rule_ids=_texts(item.get("coverage_rule_ids", []), "coverage_rule_ids"),
                route=_optional_text(item.get("route"), "route"),
                regulator_outcome=_optional_text(item.get("regulator_outcome"), "regulator_outcome"),
            )
        )

    predictions: list[AppealPrediction] = []
    for index, value in enumerate(_array(document.get("predictions"), "predictions")):
        item = _object(value, f"predictions[{index}]")
        latency = item.get("latency_ms", 0)
        if not isinstance(latency, int) or isinstance(latency, bool):
            raise ValueError("latency_ms must be an integer")
        predictions.append(
            AppealPrediction(
                case_ref=_text(item.get("case_ref"), "case_ref"),
                model_fingerprint=MODEL_FINGERPRINT,
                policy_fingerprint=POLICY_FINGERPRINT,
                code_revision="fixture-v1",
                appeal_type=_optional_text(item.get("appeal_type"), "appeal_type"),
                requested_item_class=_optional_text(item.get("requested_item_class"), "requested_item_class"),
                coverage_rule_ids=_texts(item.get("coverage_rule_ids", []), "coverage_rule_ids"),
                route=_optional_text(item.get("route"), "route"),
                regulator_outcome=_optional_text(item.get("regulator_outcome"), "regulator_outcome"),
                abstained_tasks=frozenset(EvaluationTask(task) for task in _texts(item.get("abstained_tasks", []), "abstained_tasks")),
                latency_ms=latency,
            )
        )
    return capabilities, tuple(cases), tuple(predictions)


def report_document(path: Path) -> dict[str, object]:
    capabilities, cases, predictions = load_fixture(path)
    report = evaluate_predictions(capabilities, cases, predictions)
    return {
        "schema_version": report.schema_version,
        "status": "deterministic_fixture_complete",
        "source": {
            "source_id": capabilities.source_id,
            "source_class": capabilities.source_class.value,
            "supported_tasks": sorted(task.value for task in capabilities.supported_tasks),
            "complete_denial_package": capabilities.complete_denial_package,
            "clinical_ground_truth": capabilities.clinical_ground_truth,
        },
        "case_count": report.case_count,
        "prediction_count": report.prediction_count,
        "metrics": [
            {
                **asdict(metric),
                "task": metric.task.value,
            }
            for metric in report.metrics
        ],
        "limitations": [
            "This committed fixture verifies the scorer; it is not a real-world benchmark result.",
            "Regulator-summary tasks do not establish complete-case clinical efficacy.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "config" / "evaluation_fixture.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = report_document(args.fixture.expanduser().resolve())
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
