"""Generic raw-layer S3 writer, reusable by any future extractor."""

from __future__ import annotations

from typing import Any


def write_raw_json(s3_client: Any, bucket: str, key: str, body: bytes) -> None:
    """Write raw JSON bytes verbatim to S3."""
    s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
