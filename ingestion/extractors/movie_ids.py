"""Milestone-1 movie ID scope.

This is a "prove the pipeline" placeholder only — NOT PROJECT_PLAN.md
Section 9's real scope-filtering logic (daily ID export, year/vote/language
filters), which is explicitly deferred to a later engineering decision.
"""

from __future__ import annotations

import os
from typing import Final

DEFAULT_MOVIE_IDS: Final[list[int]] = [550, 238, 129, 155, 424, 19404, 372058, 496243]

_MOVIE_IDS_ENV_VAR: Final[str] = "MOVIE_IDS"


def get_movie_ids() -> list[int]:
    """Return the MOVIE_IDS env var (comma-separated ints) if set, else the default list."""
    raw = os.environ.get(_MOVIE_IDS_ENV_VAR)
    if not raw:
        return list(DEFAULT_MOVIE_IDS)
    return [int(value.strip()) for value in raw.split(",") if value.strip()]
