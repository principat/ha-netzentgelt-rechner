"""Stages, quarters, prices and the grid-fee series (pure)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .models import Params, Slot

QUARTERS = ("Q1", "Q2", "Q3", "Q4")
_QUARTER_RE = re.compile(r"^[NSH]{24}$")
_QUARTER_SPAN = {
    "Q1": ((1, 1), (3, 31)),
    "Q2": ((4, 1), (6, 30)),
    "Q3": ((7, 1), (9, 30)),
    "Q4": ((10, 1), (12, 31)),
}


class WindowError(ValueError):
    """An invalid tariff window; ``code`` selects the localized message (docs/02 §3.2)."""

    def __init__(self, code: str, index: int, other: int | None = None) -> None:
        super().__init__(
            f"tariff window {index}: {code}" + (f" (vs {other})" if other is not None else "")
        )
        self.code = code
        self.index = index
        self.other = other


@dataclass(frozen=True, slots=True)
class TariffWindow:
    """HT or NT time frame: dates inclusive, hours from_hour <= h < to_hour (wraps if less)."""

    stage: str  # 'N' | 'H'
    start: date
    end: date
    from_hour: int  # 0..23
    to_hour: int  # 1..24

    def hours(self) -> frozenset[int]:
        """Hours of the day covered (wrapping over midnight when ``to_hour < from_hour``)."""
        if self.from_hour < self.to_hour:
            return frozenset(range(self.from_hour, self.to_hour))
        return frozenset(range(self.from_hour, 24)) | frozenset(range(self.to_hour))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stufe": self.stage,
            "von": self.start.isoformat(),
            "bis": self.end.isoformat(),
            "stunde_von": self.from_hour,
            "stunde_bis": self.to_hour,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TariffWindow:
        """Inverse of :meth:`to_dict`; raises ValueError for anything malformed."""
        try:
            hours = (data["stunde_von"], data["stunde_bis"])
            if any(isinstance(h, bool) or not isinstance(h, int) for h in hours):
                raise ValueError("hours must be integers")
            return cls(
                str(data["stufe"]),
                date.fromisoformat(data["von"]),
                date.fromisoformat(data["bis"]),
                hours[0],
                hours[1],
            )
        except (KeyError, TypeError) as err:
            raise ValueError(f"malformed tariff window: {data!r}") from err


def _validate_one(w: TariffWindow, index: int) -> None:
    if w.stage not in ("N", "H"):
        raise WindowError("stage", index)
    if w.start > w.end:
        raise WindowError("date_order", index)
    if not (0 <= w.from_hour <= 23 and 1 <= w.to_hour <= 24):
        raise WindowError("hour_range", index)
    if w.from_hour == w.to_hour:
        raise WindowError("hours_equal", index)


def validate_windows(windows: Sequence[TariffWindow]) -> None:
    """Raise WindowError for the first invalid or overlapping entry (AK-14)."""
    for j, w in enumerate(windows):
        _validate_one(w, j)
        for i in range(j):
            o = windows[i]
            if w.start <= o.end and o.start <= w.end and w.hours() & o.hours():
                raise WindowError("overlap", j, i)


def quarter_of(day: date) -> str:
    """Quarter label of a local date."""
    return f"Q{(day.month - 1) // 3 + 1}"


def project_day(day: date, year: int) -> date:
    """Same day and month in ``year`` (29 Feb becomes 28 Feb in non-leap years), AK-16."""
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def day_stages(windows: Sequence[TariffWindow], day: date) -> str:
    """24 characters ('N' | 'S' | 'H', index = local hour) for one date."""
    stages = ["S"] * 24
    for w in windows:
        if w.start <= day <= w.end:
            for h in w.hours():
                stages[h] = w.stage
    return "".join(stages)


def stage(windows: Sequence[TariffWindow], day: date, hour: int) -> str:
    """Stage 'N' | 'S' | 'H' for a local date and hour (standard where no window applies)."""
    if not 0 <= hour <= 23:
        raise ValueError(f"hour out of range: {hour}")
    return day_stages(windows, day)[hour]


def _runs(text: str, letter: str) -> list[tuple[int, int]]:
    """Maximal [start, end) hour runs of ``letter`` in a 24-character string."""
    runs: list[tuple[int, int]] = []
    for h, ch in enumerate(text):
        if ch != letter:
            continue
        if runs and runs[-1][1] == h:
            runs[-1] = (runs[-1][0], h + 1)
        else:
            runs.append((h, h + 1))
    return runs


def windows_from_quarters(quarters: Mapping[str, str], year: int) -> list[TariffWindow]:
    """Convert v1.0.0 quarterly 24-character windows into tariff windows (AK-17)."""
    out: list[TariffWindow] = []
    for q in QUARTERS:
        text = quarters.get(q)
        if text is None or not _QUARTER_RE.fullmatch(text):
            raise ValueError(f"invalid time window for {q}")
        (m1, d1), (m2, d2) = _QUARTER_SPAN[q]
        first, last = date(year, m1, d1), date(year, m2, d2)
        for letter in ("N", "H"):
            runs = _runs(text, letter)
            if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 24:
                runs = [(runs[-1][0], runs[0][1]), *runs[1:-1]]  # one window over midnight
            out.extend(TariffWindow(letter, first, last, a, b) for a, b in runs)
    return out


def default_windows(year: int) -> list[TariffWindow]:
    """Example list for a calendar year: NT 23-5, HT 11-13 and 17-19 (docs/01 §7)."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    return [
        TariffWindow("N", first, last, 23, 5),
        TariffWindow("H", first, last, 11, 13),
        TariffWindow("H", first, last, 17, 19),
    ]


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


def _slot(start_local: datetime, p: Params, windows: Sequence[TariffWindow]) -> Slot:
    day = start_local.date()
    quarter = quarter_of(day)
    st = stage(windows, day, start_local.hour)
    end_local = (start_local.astimezone(UTC) + timedelta(hours=1)).astimezone(start_local.tzinfo)
    return Slot(start_local, end_local, st, price(st, quarter, p))


def slot_at(now_local: datetime, p: Params, windows: Sequence[TariffWindow]) -> Slot:
    """The hourly slot that contains ``now_local``."""
    return _slot(now_local.replace(minute=0, second=0, microsecond=0), p, windows)


def slots(now_local: datetime, p: Params, windows: Sequence[TariffWindow]) -> list[Slot]:
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
