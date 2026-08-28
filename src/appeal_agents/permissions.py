"""Versioned least-privilege contracts for the Appeal fleet."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class CapabilityDenied(PermissionError):
    """Raised when a role attempts an operation outside its policy."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _strings(value: JsonValue | None, label: str) -> frozenset[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a string list")
    values: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} must be a string list")
        values.add(item)
    return frozenset(values)


def _boolean(value: JsonValue | None, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


@dataclass(frozen=True)
class AgentPolicy:
    role: str
    identity: str
    read_scopes: frozenset[str]
    write_scopes: frozenset[str]
    can_mutate_external: bool
    patient_scoped: bool

    def __post_init__(self) -> None:
        _require(self.role, "agent role")
        _require(self.identity, "agent identity")

    def require_read(self, scope: str) -> None:
        if scope not in self.read_scopes:
            raise CapabilityDenied(f"{self.role} cannot read {scope}")

    def require_write(self, scope: str) -> None:
        if scope not in self.write_scopes:
            raise CapabilityDenied(f"{self.role} cannot write {scope}")

    def require_external_mutation(self) -> None:
        if not self.can_mutate_external:
            raise CapabilityDenied(f"{self.role} cannot perform an external mutation")

    def require_patient_scope(self, requested_patient_id: str, open_patient_id: str) -> None:
        if not self.patient_scoped:
            raise CapabilityDenied(f"{self.role} has no patient-chart access")
        if _require(requested_patient_id, "requested patient ID") != _require(open_patient_id, "open patient ID"):
            raise CapabilityDenied(f"{self.role} attempted cross-patient chart access")


class AgentPolicyRegistry:
    """Validated role-to-capability mapping loaded from project config."""

    def __init__(self, policies: dict[str, AgentPolicy]) -> None:
        self._policies = dict(policies)

    @classmethod
    def from_path(cls, path: Path) -> "AgentPolicyRegistry":
        raw = json.loads(path.read_text(encoding="utf-8"))
        document = _object(cast(JsonValue, raw), "agent policy document")
        agents = _object(document.get("agents"), "agents")
        policies: dict[str, AgentPolicy] = {}
        for role, value in agents.items():
            config = _object(value, f"agents.{role}")
            policies[role] = AgentPolicy(
                role=role,
                identity=_string(config.get("identity"), f"agents.{role}.identity"),
                read_scopes=_strings(config.get("read_scopes"), f"agents.{role}.read_scopes"),
                write_scopes=_strings(config.get("write_scopes"), f"agents.{role}.write_scopes"),
                can_mutate_external=_boolean(
                    config.get("can_mutate_external"), f"agents.{role}.can_mutate_external"
                ),
                patient_scoped=_boolean(config.get("patient_scoped"), f"agents.{role}.patient_scoped"),
            )
        if not policies:
            raise ValueError("agent policy document must contain at least one role")
        return cls(policies)

    def for_role(self, role: str) -> AgentPolicy:
        policy = self._policies.get(_require(role, "agent role"))
        if policy is None:
            raise CapabilityDenied(f"unknown agent role {role}")
        return policy

    def roles(self) -> tuple[str, ...]:
        return tuple(self._policies)


DEFAULT_POLICY_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "config" / "agent_policies.json"


def default_policy_registry() -> AgentPolicyRegistry:
    return AgentPolicyRegistry.from_path(DEFAULT_POLICY_PATH)
