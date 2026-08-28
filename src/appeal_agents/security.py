"""Local safety boundaries used until managed security services are connected."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final


class InspectionStatus(str, Enum):
    CLEAR = "clear"
    BLOCKED = "blocked"


INJECTION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(?:exfiltrate|export|send)\s+(?:the\s+)?patient\s+(?:list|records)", re.IGNORECASE),
    re.compile(r"reveal\s+(?:the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"override\s+(?:the\s+)?safety", re.IGNORECASE),
    re.compile(r"call\s+(?:the\s+)?tool", re.IGNORECASE),
)
PHI_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:member\s+id|medical\s+record\s+number)\s*[:#]?\s*[A-Z0-9-]{4,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
)


@dataclass(frozen=True)
class InspectionResult:
    surface: str
    status: InspectionStatus
    provider: str
    categories: tuple[str, ...]
    reason: str


def _matches(patterns: tuple[re.Pattern[str], ...], value: str) -> tuple[str, ...]:
    names: list[str] = []
    for pattern in patterns:
        if pattern.search(value):
            names.append(pattern.pattern)
    return tuple(names)


class LocalSecurityBoundary:
    """Deterministic fallback for inbound injection and outbound PHI checks."""

    implementation = "local_deterministic_fallback"

    def inspect_inbound(self, content: str) -> InspectionResult:
        matches = _matches(INJECTION_PATTERNS, content)
        if matches:
            return InspectionResult(
                surface="inbound_document",
                status=InspectionStatus.BLOCKED,
                provider=self.implementation,
                categories=("prompt_injection",),
                reason="untrusted document contains an instruction-like exfiltration or control attempt",
            )
        return InspectionResult(
            surface="inbound_document",
            status=InspectionStatus.CLEAR,
            provider=self.implementation,
            categories=(),
            reason="no local injection indicators matched",
        )

    def inspect_egress(self, content: str) -> InspectionResult:
        matches = _matches(PHI_PATTERNS, content)
        if matches:
            return InspectionResult(
                surface="egress_to_zone_c",
                status=InspectionStatus.BLOCKED,
                provider=self.implementation,
                categories=("possible_phi",),
                reason="draft contains a possible identifier-shaped value",
            )
        return InspectionResult(
            surface="egress_to_zone_c",
            status=InspectionStatus.CLEAR,
            provider=self.implementation,
            categories=(),
            reason="no local identifier-shaped value matched",
        )

    def inspect_memory(self, content: str) -> InspectionResult:
        injection_matches = _matches(INJECTION_PATTERNS, content)
        if injection_matches:
            return InspectionResult(
                surface="memory_bank",
                status=InspectionStatus.BLOCKED,
                provider=self.implementation,
                categories=("prompt_injection",),
                reason="memory contains an instruction-like poisoning attempt",
            )
        phi_matches = _matches(PHI_PATTERNS, content)
        if phi_matches:
            return InspectionResult(
                surface="memory_bank",
                status=InspectionStatus.BLOCKED,
                provider=self.implementation,
                categories=("possible_phi",),
                reason="memory contains a possible identifier-shaped value",
            )
        return InspectionResult(
            surface="memory_bank",
            status=InspectionStatus.CLEAR,
            provider=self.implementation,
            categories=(),
            reason="no local memory-poisoning or identifier-shaped value matched",
        )
