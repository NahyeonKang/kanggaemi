from __future__ import annotations

from datetime import date
from typing import Iterator, Protocol

from frontend.contracts import NodeEvent


class AgentEventAdapter(Protocol):
    """Only boundary the Streamlit UI knows about agent execution."""

    def stream(self, query: str, as_of_date: date) -> Iterator[NodeEvent]: ...
