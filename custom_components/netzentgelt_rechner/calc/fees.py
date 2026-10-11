"""Stages, quarters, prices and the grid-fee series (pure)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

from .models import Params, Slot

QUARTERS = ("Q1", "Q2", "Q3", "Q4")
WINDOW_RE = re.compile(r"^[NSH]{24}$")


def validate_windows(windows: Mapping[str, str]) -> None:
    """Raise ValueError unless every quarter has a valid 24-character window."""
    for q in QUARTERS:
        if q not in windows or not WINDOW_RE.fullmatch(windows[q]):
            raise ValueError(f"invalid time window for {q}")


def quarter_of(day: date) -> str:
    """Quarter label of a local date."""
    return f"Q{(day.month - 1) // 3 + 1}"


def stage(windows: Mapping[str, str], quarter: str, hour: int) -> str:
    """Stage 'N' | 'S' | 'H' for a local hour."""
    if not 0 <= hour <= 23:
        raise ValueError(f"hour out of range: {hour}")
    return windows[quarter][hour]


def price(stage_: str, quarter: str, p: Params) -> float:
    """Gross grid fee in EUR/kWh. The only place that resolves a stage price (docs/02 §3.3).

    ``quarter`` is unused today (open question F-2: prices per quarter).
    """
    del quarter
    if stage_ == "N":
        return p.nt
    if stage_ == "S":
        return p.st
    if stage_ == "H":
        return p.ht
    raise ValueError(f"unknown stage: {stage_!r}")


def _slot(start_local: datetime, p: Params, windows: Mapping[str, str]) -> Slot:
    quarter = quarter_of(start_local.date())
    st = stage(windows, quarter, start_local.hour)
    end_local = (start_local.astimezone(UTC) + timedelta(hours=1)).astimezone(start_local.tzinfo)
    return Slot(start_local, end_local, st, price(st, quarter, p))


def slot_at(now_local: datetime, p: Params, windows: Mapping[str, str]) -> Slot:
    """The hourly slot that contains ``now_local``."""
    return _slot(now_local.replace(minute=0, second=0, microsecond=0), p, windows)


def slots(now_local: datetime, p: Params, windows: Mapping[str, str]) -> list[Slot]:
    """Hourly slots from today 00:00 up to the day after tomorrow 00:00 (local)."""
    tz = now_local.tzinfo
    if tz is None:
        raise ValueError("now_local must be timezone-aware")
    first = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    stop = datetime.combine(now_local.date() + timedelta(days=2), time.min, tzinfo=tz)
    cursor = first.astimezone(UTC)
    stop_utc = stop.astimezone(UTC)
    out: list[Slot] = []
    while cursor < stop_utc:
        out.append(_slot(cursor.astimezone(tz), p, windows))
        cursor += timedelta(hours=1)
    return out
