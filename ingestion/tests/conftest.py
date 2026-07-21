"""Shared test fixtures/helpers for ingestion tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeResponse:
    """Duck-types the subset of requests.Response the client touches."""

    status_code: int
    json_body: Any = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self) -> Any:
        return self.json_body
