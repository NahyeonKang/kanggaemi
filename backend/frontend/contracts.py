from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping


EventType = Literal["node_start", "node_complete", "final", "error"]
EventStatus = Literal["running", "done", "failed"]


@dataclass(frozen=True)
class NodeEvent:
    type: EventType
    node_id: str
    node_name: str
    status: EventStatus
    summary: str | None = None
    payload: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NodeEvent":
        event = cls(
            type=value["type"], node_id=str(value["node_id"]),
            node_name=str(value["node_name"]), status=value["status"],
            summary=value.get("summary"), payload=value.get("payload"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        if self.type not in {"node_start", "node_complete", "final", "error"}:
            raise ValueError(f"invalid event type: {self.type}")
        if self.status not in {"running", "done", "failed"}:
            raise ValueError(f"invalid event status: {self.status}")
        if not self.node_id or not self.node_name:
            raise ValueError("node_id and node_name are required")
        if self.type == "final" and not isinstance(self.payload, dict):
            raise ValueError("final event requires a payload")
