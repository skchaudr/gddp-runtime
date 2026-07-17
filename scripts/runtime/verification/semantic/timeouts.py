"""Shared evaluator timeout budget constants."""

from __future__ import annotations

import os


PI_TIMEOUT_SECONDS = int(os.environ.get("GDDP_PI_TIMEOUT_SECONDS", "1200"))
BRIDGE_TIMEOUT_OVERHEAD_SECONDS = int(
    os.environ.get("GDDP_VERIFY_TIMEOUT_OVERHEAD_SECONDS", "120")
)
SEQUENTIAL_LANE_COUNT = 2


def bridge_timeout_seconds(configured_timeout_seconds: int) -> int:
    """Keep the outer verifier alive for both sequential pi lanes and cleanup."""
    minimum = (
        SEQUENTIAL_LANE_COUNT * PI_TIMEOUT_SECONDS
        + BRIDGE_TIMEOUT_OVERHEAD_SECONDS
    )
    return max(configured_timeout_seconds, minimum)
