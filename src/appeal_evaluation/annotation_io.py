"""Safe import and adjudication of outcome-blinded human annotations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .annotations import (
    AnnotationDisposition,
    CaseAnnotation,
    GoldLabel,
    GoldResolution,
    OperationalRoute,
    RationaleCategory,
    SourceSpanLabel,
    gold_from_consensus,
    requires_adjudication,
)


ANNOTATION_FIELDS = frozenset(
    {
        "disposition",
        "primary_category",
        "secondary_categories",
        "route",
        "rationale_spans",
        "policy_spans",
        "confidence",
    }
)
SOURCE_FIELDS = ("decision_rationale", "policy_context")
FORBIDDEN_KEYS = frozenset(
    {
        "regulator_outcome",
        "hidden_labels",
        "final_outcome",
        "outcome_label",
    }
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _enum(enum_type: type[Any], value: object, label: str) -> Any:
    try:
        return enum_type(_text(value, label))
    except ValueError as error:
        raise ValueError(f"{label} is not supported") from error


def _string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))


def _span_array(value: object, label: str) -> tuple[SourceSpanLabel, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    spans: list[SourceSpanLabel] = []
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]")
        start = item.get("start")
        end = item.get("end")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError(f"{label}[{index}] offsets must be integers")
        spans.append(
            SourceSpanLabel(
                source_field=_text(item.get("source_field"), f"{label}[{index}].source_field"),
                start=start,
                end=end,
                source_sha256=_text(item.get("source_sha256"), f"{label}[{index}].source_sha256"),
            )
        )
    return tuple(spans)


def _contains_forbidden_key(value: object) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key in FORBIDDEN_KEYS:
                return key
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    return None


def _case_ref(value: object, label: str = "case_ref") -> str:
    result = _text(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return result


def _validate_spans(
    spans: tuple[SourceSpanLabel, ...],
    context: Mapping[str, object],
    source_hashes: Mapping[str, object],
    label: str,
) -> None:
    for index, span in enumerate(spans):
        source = context.get(span.source_field)
        expected_hash = source_hashes.get(span.source_field)
        if not isinstance(source, str) or not isinstance(expected_hash, str):
            raise ValueError(f"{label}[{index}] references an unavailable source field")
        if span.source_sha256 != expected_hash:
            raise ValueError(f"{label}[{index}] hash does not match queue source")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected_hash:
            raise ValueError(f"{label}[{index}] source hash is inconsistent with queue content")
        if span.end > len(source):
            raise ValueError(f"{label}[{index}] exceeds source bounds")


def parse_annotation(
    value: Mapping[str, object],
    *,
    case_ref: str,
    taxonomy_version: str,
    annotator_id: str,
    annotator_role: str,
) -> CaseAnnotation:
    """Parse a reviewer payload; identity is supplied by the import command."""

    unknown = set(value) - ANNOTATION_FIELDS
    if unknown:
        raise ValueError(f"annotation has unsupported fields: {', '.join(sorted(unknown))}")
    return CaseAnnotation(
        case_ref=_case_ref(case_ref),
        taxonomy_version=taxonomy_version,
        annotator_id=annotator_id,
        annotator_role=annotator_role,
        blinded_to_outcome=True,
        disposition=_enum(AnnotationDisposition, value.get("disposition"), "annotation.disposition"),
        primary_category=_enum(RationaleCategory, value.get("primary_category"), "annotation.primary_category"),
        secondary_categories=tuple(
            _enum(RationaleCategory, item, f"annotation.secondary_categories[{index}]")
            for index, item in enumerate(_string_array(value.get("secondary_categories", []), "annotation.secondary_categories"))
        ),
        route=_enum(OperationalRoute, value.get("route"), "annotation.route"),
        rationale_spans=_span_array(value.get("rationale_spans", []), "annotation.rationale_spans"),
        policy_spans=_span_array(value.get("policy_spans", []), "annotation.policy_spans"),
        confidence=_confidence(value.get("confidence"), "annotation.confidence"),
    )


def _confidence(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ValueError(f"{label} must be an integer from 1 to 5")
    return value


def annotation_to_json(annotation: CaseAnnotation) -> dict[str, object]:
    return {
        "case_ref": annotation.case_ref,
        "taxonomy_version": annotation.taxonomy_version,
        "annotator_id": annotation.annotator_id,
        "annotator_role": annotation.annotator_role,
        "blinded_to_outcome": annotation.blinded_to_outcome,
        "disposition": annotation.disposition.value,
        "primary_category": annotation.primary_category.value,
        "secondary_categories": [item.value for item in annotation.secondary_categories],
        "route": annotation.route.value,
        "rationale_spans": [
            {
                "source_field": span.source_field,
                "start": span.start,
                "end": span.end,
                "source_sha256": span.source_sha256,
            }
            for span in annotation.rationale_spans
        ],
        "policy_spans": [
            {
                "source_field": span.source_field,
                "start": span.start,
                "end": span.end,
                "source_sha256": span.source_sha256,
            }
            for span in annotation.policy_spans
        ],
        "confidence": annotation.confidence,
    }


@dataclass(frozen=True)
class QueueRow:
    case_ref: str
    split: str
    context_fingerprint: str
    context: Mapping[str, object]
    source_hashes: Mapping[str, object]
    annotation: CaseAnnotation | None
    human_reviewed: bool


@dataclass(frozen=True)
class QueueInspection:
    path: Path
    sha256: str
    row_count: int
    complete_count: int
    pending_count: int
    partial_count: int
    unreviewed_count: int
    split_counts: dict[str, int]
    rows: tuple[QueueRow, ...]

    @property
    def complete(self) -> bool:
        return self.pending_count == 0 and self.partial_count == 0 and self.unreviewed_count == 0

    @property
    def order_fingerprint(self) -> str:
        payload = "\n".join(row.case_ref for row in self.rows).encode("ascii")
        return hashlib.sha256(payload).hexdigest()

    @property
    def context_fingerprint(self) -> str:
        payload = "\n".join(
            f"{row.case_ref}:{row.split}:{row.context_fingerprint}"
            for row in sorted(self.rows, key=lambda item: item.case_ref)
        ).encode("ascii")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class AdjudicationRecord:
    annotation: CaseAnnotation
    decision_note_sha256: str


def _context_fingerprint(case_ref: str, split: str, context: Mapping[str, object], source_hashes: Mapping[str, object]) -> str:
    payload = {
        "case_ref": case_ref,
        "split": split,
        "context": {
            key: context.get(key)
            for key in ("part", "appeal_type", "condition", "requested_item_or_drug")
        },
        "source_hashes": dict(source_hashes),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inspect_queue(
    path: Path,
    *,
    taxonomy_version: str,
    annotator_id: str,
    annotator_role: str,
    require_locked_test: bool = True,
) -> QueueInspection:
    rows: list[QueueRow] = []
    seen: set[str] = set()
    split_counts: Counter[str] = Counter()
    complete_count = 0
    pending_count = 0
    partial_count = 0
    unreviewed_count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                raw = _object(json.loads(line), f"queue row {line_number}")
                case_ref = _case_ref(raw.get("case_ref"), f"queue row {line_number}.case_ref")
                if case_ref in seen:
                    raise ValueError("duplicate case_ref")
                seen.add(case_ref)
                split = _text(raw.get("split"), f"queue row {line_number}.split")
                if require_locked_test and split != "locked_test":
                    raise ValueError("gold annotation queue must contain locked_test rows only")
                context = _object(raw.get("context"), f"queue row {line_number}.context")
                source_hashes = _object(raw.get("source_hashes"), f"queue row {line_number}.source_hashes")
                if _contains_forbidden_key(raw) is not None:
                    raise ValueError("outcome labels are forbidden in annotation queues")
                for field in SOURCE_FIELDS:
                    source = context.get(field)
                    source_hash = source_hashes.get(field)
                    if not isinstance(source, str) or not isinstance(source_hash, str):
                        raise ValueError(f"queue row {line_number} lacks {field} source material")
                    if hashlib.sha256(source.encode("utf-8")).hexdigest() != source_hash:
                        raise ValueError(f"queue row {line_number} has a {field} hash mismatch")
                context_fingerprint = _context_fingerprint(case_ref, split, context, source_hashes)
                annotation_value = _object(raw.get("annotation"), f"queue row {line_number}.annotation")
                values = [annotation_value.get(field) for field in ANNOTATION_FIELDS]
                has_values = any(value is not None and value != [] for value in values)
                has_missing = any(value is None for value in values)
                annotation: CaseAnnotation | None = None
                review_meta = raw.get("review_meta")
                human_reviewed = isinstance(review_meta, dict) and review_meta.get("human_reviewed") is True
                if has_values and has_missing:
                    partial_count += 1
                elif not has_values:
                    pending_count += 1
                else:
                    annotation = parse_annotation(
                        annotation_value,
                        case_ref=case_ref,
                        taxonomy_version=taxonomy_version,
                        annotator_id=annotator_id,
                        annotator_role=annotator_role,
                    )
                    _validate_spans(annotation.rationale_spans, context, source_hashes, f"queue row {line_number}.rationale_spans")
                    _validate_spans(annotation.policy_spans, context, source_hashes, f"queue row {line_number}.policy_spans")
                    complete_count += 1
                    if not human_reviewed:
                        unreviewed_count += 1
                split_counts[split] += 1
                rows.append(QueueRow(case_ref, split, context_fingerprint, context, source_hashes, annotation, human_reviewed))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid annotation queue row {line_number}: {error}") from error
    return QueueInspection(
        path=path,
        sha256=sha256_file(path),
        row_count=len(rows),
        complete_count=complete_count,
        pending_count=pending_count,
        partial_count=partial_count,
        unreviewed_count=unreviewed_count,
        split_counts=dict(sorted(split_counts.items())),
        rows=tuple(rows),
    )


def _rows_by_case(inspection: QueueInspection, *, split: str | None = None) -> dict[str, QueueRow]:
    return {row.case_ref: row for row in inspection.rows if split is None or row.split == split}


def build_gold_labels(
    first: QueueInspection,
    second: QueueInspection,
    *,
    adjudication_path: Path | None,
    taxonomy_version: str,
    adjudicator_id: str | None = None,
    adjudicator_role: str | None = None,
) -> tuple[GoldLabel, ...]:
    """Build gold labels, requiring a third human decision for every disagreement."""

    first_by_case = _rows_by_case(first, split="locked_test")
    second_by_case = _rows_by_case(second, split="locked_test")
    if set(first_by_case) != set(second_by_case):
        raise ValueError("independent queues do not contain the same case set")
    if any(row.annotation is None or not row.human_reviewed for row in first_by_case.values()) or any(
        row.annotation is None or not row.human_reviewed for row in second_by_case.values()
    ):
        raise ValueError("both independent annotation queues must be complete for locked_test")
    for case_ref, first_row in first_by_case.items():
        second_row = second_by_case[case_ref]
        if first_row.split != second_row.split or first_row.context_fingerprint != second_row.context_fingerprint:
            raise ValueError(f"queue context mismatch for case {case_ref}")
        if first_row.annotation is None or second_row.annotation is None:
            raise ValueError(f"missing independent annotation for case {case_ref}")
        if first_row.annotation.taxonomy_version != taxonomy_version or second_row.annotation.taxonomy_version != taxonomy_version:
            raise ValueError(f"taxonomy version mismatch for case {case_ref}")
        if first_row.annotation.annotator_id == second_row.annotation.annotator_id:
            raise ValueError("independent queues must have distinct reviewer identities")

    adjudications = _load_adjudications(
        adjudication_path,
        taxonomy_version=taxonomy_version,
        adjudicator_id=adjudicator_id,
        adjudicator_role=adjudicator_role,
    )
    gold: list[GoldLabel] = []
    expected_adjudications: set[str] = set()
    for case_ref in sorted(first_by_case):
        first_annotation = first_by_case[case_ref].annotation
        second_annotation = second_by_case[case_ref].annotation
        assert first_annotation is not None and second_annotation is not None
        if requires_adjudication(first_annotation, second_annotation):
            expected_adjudications.add(case_ref)
            resolution = adjudications.get(case_ref)
            if resolution is None:
                raise ValueError(f"case {case_ref} disagrees and has no adjudication")
            gold.append(
                _gold_from_adjudication(
                    first_annotation,
                    second_annotation,
                    resolution,
                    context=first_by_case[case_ref].context,
                    source_hashes=first_by_case[case_ref].source_hashes,
                    taxonomy_version=taxonomy_version,
                )
            )
        else:
            if case_ref in adjudications:
                raise ValueError(f"case {case_ref} has an unnecessary adjudication record")
            gold.append(gold_from_consensus(first_annotation, second_annotation))
    extra = set(adjudications) - expected_adjudications
    if extra:
        raise ValueError("adjudication file contains a case without a reviewer disagreement")
    return tuple(gold)


def _load_adjudications(
    path: Path | None,
    *,
    taxonomy_version: str,
    adjudicator_id: str | None,
    adjudicator_role: str | None,
) -> dict[str, AdjudicationRecord]:
    if path is None:
        return {}
    if not adjudicator_id or not adjudicator_role:
        raise ValueError("adjudicator identity is required when an adjudication file is supplied")
    result: dict[str, AdjudicationRecord] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = _object(json.loads(line), f"adjudication row {line_number}")
            case_ref = _case_ref(raw.get("case_ref"), f"adjudication row {line_number}.case_ref")
            if case_ref in result:
                raise ValueError(f"duplicate adjudication for case {case_ref}")
            if raw.get("resolution") != GoldResolution.ADJUDICATED.value:
                raise ValueError(f"adjudication row {line_number} must have resolution=adjudicated")
            decision_note = _text(raw.get("decision_note"), f"adjudication row {line_number}.decision_note")
            if _contains_forbidden_key(raw) is not None:
                raise ValueError("outcome labels are forbidden in adjudication files")
            annotation = parse_annotation(
                _object(raw.get("annotation"), f"adjudication row {line_number}.annotation"),
                case_ref=case_ref,
                taxonomy_version=taxonomy_version,
                annotator_id=adjudicator_id,
                annotator_role=adjudicator_role,
            )
            result[case_ref] = AdjudicationRecord(
                annotation=annotation,
                decision_note_sha256=hashlib.sha256(decision_note.encode("utf-8")).hexdigest(),
            )
    return result


def _gold_from_adjudication(
    first: CaseAnnotation,
    second: CaseAnnotation,
    adjudicated: AdjudicationRecord,
    *,
    context: Mapping[str, object],
    source_hashes: Mapping[str, object],
    taxonomy_version: str,
) -> GoldLabel:
    annotation = adjudicated.annotation
    _validate_spans(annotation.rationale_spans, context, source_hashes, f"adjudication.{first.case_ref}.rationale_spans")
    _validate_spans(annotation.policy_spans, context, source_hashes, f"adjudication.{first.case_ref}.policy_spans")
    if annotation.case_ref != first.case_ref or annotation.taxonomy_version != taxonomy_version:
        raise ValueError(f"adjudication identity mismatch for case {first.case_ref}")
    if annotation.annotator_id in {first.annotator_id, second.annotator_id}:
        raise ValueError(f"adjudicator is not independent for case {first.case_ref}")
    return GoldLabel(
        case_ref=first.case_ref,
        taxonomy_version=taxonomy_version,
        independent_annotator_ids=(first.annotator_id, second.annotator_id),
        resolution=GoldResolution.ADJUDICATED,
        disposition=annotation.disposition,
        primary_category=annotation.primary_category,
        secondary_categories=annotation.secondary_categories,
        route=annotation.route,
        rationale_spans=annotation.rationale_spans,
        policy_spans=annotation.policy_spans,
        confidence=annotation.confidence,
        adjudicator_id=annotation.annotator_id,
        adjudicator_role=annotation.annotator_role,
        adjudication_note_sha256=adjudicated.decision_note_sha256,
    )


def gold_to_json(label: GoldLabel) -> dict[str, object]:
    return {
        "case_ref": label.case_ref,
        "taxonomy_version": label.taxonomy_version,
        "independent_annotator_ids": list(label.independent_annotator_ids),
        "resolution": label.resolution.value,
        "disposition": label.disposition.value,
        "primary_category": label.primary_category.value,
        "secondary_categories": [item.value for item in label.secondary_categories],
        "route": label.route.value,
        "rationale_spans": [
            {
                "source_field": span.source_field,
                "start": span.start,
                "end": span.end,
                "source_sha256": span.source_sha256,
            }
            for span in label.rationale_spans
        ],
        "policy_spans": [
            {
                "source_field": span.source_field,
                "start": span.start,
                "end": span.end,
                "source_sha256": span.source_sha256,
            }
            for span in label.policy_spans
        ],
        "confidence": label.confidence,
        "adjudicator_id": label.adjudicator_id,
        "adjudicator_role": label.adjudicator_role,
        "adjudication_note_sha256": label.adjudication_note_sha256,
    }


def annotation_status(
    first: QueueInspection,
    second: QueueInspection,
    *,
    taxonomy_version: str,
    adjudication_path: Path | None,
) -> dict[str, object]:
    """Return an aggregate-only status report safe to commit."""

    first_cases = {row.case_ref for row in first.rows}
    second_cases = {row.case_ref for row in second.rows}
    same_case_set = first_cases == second_cases
    first_locked = _rows_by_case(first, split="locked_test")
    second_locked = _rows_by_case(second, split="locked_test")
    same_locked_case_set = set(first_locked) == set(second_locked)
    disagreements = 0
    if same_locked_case_set:
        for case_ref in first_locked:
            first_annotation = first_locked[case_ref].annotation
            second_annotation = second_locked[case_ref].annotation
            if first_annotation is not None and second_annotation is not None and requires_adjudication(first_annotation, second_annotation):
                disagreements += 1
    locked_complete_pair = (
        same_locked_case_set
        and all(row.annotation is not None and row.human_reviewed for row in first_locked.values())
        and all(row.annotation is not None and row.human_reviewed for row in second_locked.values())
    )
    adjudication_exists = adjudication_path is not None and adjudication_path.exists()
    status = "ready_for_gold_build" if locked_complete_pair and disagreements == 0 else "pending_human_annotation"
    if locked_complete_pair and disagreements and not adjudication_exists:
        status = "pending_adjudication"
    if locked_complete_pair and disagreements and adjudication_exists:
        status = "adjudication_submitted_pending_validation"
    return {
        "schema_version": "1.0",
        "status": status,
        "gold_claim_allowed": False,
        "source": {
            "queue_a_sha256": first.sha256,
            "queue_b_sha256": second.sha256,
            "queue_a_rows": first.row_count,
            "queue_b_rows": second.row_count,
            "same_case_set": same_case_set,
            "same_locked_test_case_set": same_locked_case_set,
            "taxonomy_version": taxonomy_version,
            "outcome_labels_seen": False,
            "source_narratives_emitted": False,
        },
        "review_progress": {
            "queue_a": {
                "complete": first.complete_count,
                "pending": first.pending_count,
                "partial": first.partial_count,
                "unreviewed": first.unreviewed_count,
                "splits": first.split_counts,
            },
            "queue_b": {
                "complete": second.complete_count,
                "pending": second.pending_count,
                "partial": second.partial_count,
                "unreviewed": second.unreviewed_count,
                "splits": second.split_counts,
            },
            "locked_test": {
                "rows": len(first_locked),
                "queue_a_complete": sum(row.annotation is not None for row in first_locked.values()),
                "queue_b_complete": sum(row.annotation is not None for row in second_locked.values()),
                "queue_a_human_reviewed": sum(row.annotation is not None and row.human_reviewed for row in first_locked.values()),
                "queue_b_human_reviewed": sum(row.annotation is not None and row.human_reviewed for row in second_locked.values()),
                "complete_pair": locked_complete_pair,
            },
            "independent_disagreements": disagreements,
            "adjudication_file_present": adjudication_exists,
        },
        "gold_policy": {
            "minimum_independent_annotations": 2,
            "disagreement_requires_third_human": True,
            "model_generated_label_can_be_gold": False,
            "gold_status": status,
        },
    }
