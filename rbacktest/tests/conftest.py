"""
Shared fixtures and helpers for the backtest test suite.
"""

import sys
from pathlib import Path

import pytest

# Ensure backend module is importable from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Default test universe
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def default_stocks():
    """Small representative stock pool that covers both exchanges."""
    return [
        "600519.SSE", "000858.SZSE", "600036.SSE",
        "000651.SZSE", "600276.SSE",
    ]


@pytest.fixture(scope="session")
def large_stocks():
    """Larger pool for strategies that need more candidates."""
    return [
        "600519.SSE", "000858.SZSE", "600036.SSE", "600030.SSE",
        "000651.SZSE", "600276.SSE", "600887.SSE", "000002.SZSE",
    ]


@pytest.fixture(scope="session")
def default_dates():
    """Default 5-month date range — fast enough for unit tests."""
    return {"start": "2023-06-01", "end": "2023-11-01"}


@pytest.fixture(scope="session")
def short_dates():
    """3-month range for smoke tests."""
    return {"start": "2023-06-01", "end": "2023-09-01"}
