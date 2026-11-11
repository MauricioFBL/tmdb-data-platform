"""Raw-layer technical metadata envelope (PROJECT_PLAN.md Section 8).

"Verbatim" raw storage means no schema coercion, no dropped/renamed fields,
no typing of the source payload — not literal byte-for-byte identity, since
the payload is necessarily re-embedded inside this envelope. `payload` is
built via `json.loads`, which preserves every field and key order exactly as
TMDB sent them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RawEnvelope(BaseModel):
    """Technical metadata wrapper around one raw TMDB API response."""

    model_config = ConfigDict(frozen=True)

    pipeline_run_id: str
    request_id: str
    endpoint: str
    source_entity_id: str
    http_status: int
    extraction_timestamp: datetime
    ingestion_date: date
    payload: dict[str, Any]
