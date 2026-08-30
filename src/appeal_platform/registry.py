"""Versioned, discoverable records for the Appeal reasoning fleet."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return _require(value, label)


def _strings(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty string list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} must be a string list")
        result.append(_require(item, label))
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return tuple(result)


def _boolean(value: JsonValue | None, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


@dataclass(frozen=True)
class AgentRegistration:
    """The public capability and data boundary for one discoverable agent."""

    role: str
    display_name: str
    version: str
    framework: str
    identity: str
    principal: str
    data_scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    restrictions: tuple[str, ...]
    discoverable: bool = True

    def __post_init__(self) -> None:
        _require(self.role, "agent role")
        _require(self.display_name, "agent display name")
        _require(self.version, "agent version")
        _require(self.framework, "agent framework")
        _require(self.identity, "agent identity")
        _require(self.principal, "agent principal")
        if not self.data_scopes or not self.capabilities or not self.restrictions:
            raise ValueError("agent registration scopes, capabilities, and restrictions are required")

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "display_name": self.display_name,
            "version": self.version,
            "framework": self.framework,
            "identity": self.identity,
            "principal": self.principal,
            "data_scopes": list(self.data_scopes),
            "capabilities": list(self.capabilities),
            "allowed_tools": list(self.allowed_tools),
            "restrictions": list(self.restrictions),
            "discoverable": self.discoverable,
        }


class AgentRegistry:
    """Validated registry view used by the UI and MCP authorization layer."""

    def __init__(self, records: tuple[AgentRegistration, ...]) -> None:
        if not records:
            raise ValueError("agent registry must contain at least one record")
        by_role = {record.role: record for record in records}
        if len(by_role) != len(records):
            raise ValueError("agent registry roles must be unique")
        self._records = records
        self._by_role = by_role

    @classmethod
    def from_path(cls, path: Path) -> "AgentRegistry":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("agent registry document must be an object")
        schema_version = raw.get("schema_version")
        if not isinstance(schema_version, str) or not schema_version:
            raise ValueError("agent registry schema_version must be a string")
        raw_agents = raw.get("agents")
        if not isinstance(raw_agents, list):
            raise ValueError("agent registry agents must be a list")
        records: list[AgentRegistration] = []
        for index, value in enumerate(raw_agents):
            if not isinstance(value, dict):
                raise ValueError(f"agent registry agents[{index}] must be an object")
            records.append(
                AgentRegistration(
                    role=_string(value.get("role"), f"agents[{index}].role"),
                    display_name=_string(value.get("display_name"), f"agents[{index}].display_name"),
                    version=_string(value.get("version"), f"agents[{index}].version"),
                    framework=_string(value.get("framework"), f"agents[{index}].framework"),
                    identity=_string(value.get("identity"), f"agents[{index}].identity"),
                    principal=_string(value.get("principal"), f"agents[{index}].principal"),
                    data_scopes=_strings(value.get("data_scopes"), f"agents[{index}].data_scopes"),
                    capabilities=_strings(value.get("capabilities"), f"agents[{index}].capabilities"),
                    allowed_tools=_strings(value.get("allowed_tools"), f"agents[{index}].allowed_tools"),
                    restrictions=_strings(value.get("restrictions"), f"agents[{index}].restrictions"),
                    discoverable=_boolean(value.get("discoverable"), f"agents[{index}].discoverable"),
                )
            )
        return cls(tuple(records))

    def for_role(self, role: str) -> AgentRegistration:
        role = _require(role, "agent role")
        record = self._by_role.get(role)
        if record is None or not record.discoverable:
            raise KeyError(f"agent role {role!r} is not discoverable")
        return record

    def roles(self) -> tuple[str, ...]:
        return tuple(record.role for record in self._records if record.discoverable)

    def records(self) -> tuple[AgentRegistration, ...]:
        return tuple(record for record in self._records if record.discoverable)

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "0.1",
            "agent_count": len(self.records()),
            "agents": [record.to_json() for record in self.records()],
        }

    def principals(self) -> dict[str, str]:
        """Return the verified transport-principal mapping for tool calls."""

        return {record.role: record.principal for record in self.records()}


DEFAULT_REGISTRY_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "config" / "agent_registry.json"


def default_agent_registry() -> AgentRegistry:
    return AgentRegistry.from_path(DEFAULT_REGISTRY_PATH)


__all__ = ["AgentRegistration", "AgentRegistry", "default_agent_registry"]
