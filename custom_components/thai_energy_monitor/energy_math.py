"""Pure helpers for reset-safe energy totals (no Home Assistant imports).

Energy sensors may be lifetime counters or counters that reset every day
(common on inverters such as Solis). Subtracting a single baseline only works
for the former. Home Assistant's long-term statistics already turn a
``total_increasing`` sensor into reset-safe hourly ``change`` values, so cycle
totals are built from those, plus a live partial for the hour that has not
been compiled into statistics yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Iterable


def partial_since_last_stat(curr_state: float, last_state: float | None) -> float:
    """Return energy accrued since the last compiled statistics row.

    A reading below the last compiled state means the meter reset in between
    (for example at midnight), so everything on the meter now is new energy.
    """
    if last_state is None:
        return 0.0
    if curr_state >= last_state:
        return curr_state - last_state
    return max(0.0, curr_state)


def summarize_hourly_changes(
    rows: Iterable[dict[str, Any]],
    cycle_start: datetime,
    today_start: datetime,
    parse_start: Callable[[Any], datetime],
) -> dict[str, Any] | None:
    """Sum hourly ``change`` values for the billing cycle and for today.

    ``rows`` must be sorted chronologically. Rows that start before
    ``cycle_start`` are only used to learn the last compiled meter state.
    Returns None when there are no rows at all.
    """
    monthly = 0.0
    today = 0.0
    last_row: dict[str, Any] | None = None
    last_start: datetime | None = None

    for row in rows:
        start = parse_start(row.get("start"))
        last_row = row
        last_start = start
        if start < cycle_start:
            continue
        change = row.get("change")
        if change is None:
            continue
        try:
            change = float(change)
        except (TypeError, ValueError):
            continue
        if change < 0.0:
            continue
        monthly += change
        if start >= today_start:
            today += change

    if last_row is None or last_start is None:
        return None

    def _as_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    return {
        "monthly": monthly,
        "today": today,
        "last_state": _as_float(last_row.get("state")),
        "last_sum": _as_float(last_row.get("sum")),
        "last_end": last_start + timedelta(hours=1),
    }
