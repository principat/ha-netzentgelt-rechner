"""Recorder access: load the long-term statistics of the last 12 full local months."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, tzinfo
from typing import Any

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance

from .calc import CalcError

Series = dict[datetime, float | None]


def period(today: date, tz: tzinfo) -> tuple[date, date, datetime, datetime]:
    """Last 12 full local months: ``[1st of month 12 months ago, 1st of current month)``."""
    end = today.replace(day=1)
    start = date(end.year - 1, end.month, 1)
    start_utc = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(end, time.min, tzinfo=tz).astimezone(UTC)
    return start, end, start_utc, end_utc


def _ts(row: dict[str, Any]) -> datetime:
    """Normalise the row start (float seconds or datetime depending on HA version) to UTC."""
    start = row["start"]
    if isinstance(start, int | float):
        return datetime.fromtimestamp(start, UTC)
    return start.astimezone(UTC)  # type: ignore[no-any-return]


def _series(rows: list[dict[str, Any]], key: str) -> Series:
    return {_ts(row): row.get(key) for row in rows}


async def async_load_statistics(
    hass: HomeAssistant,
    import_id: str,
    export_id: str,
    price_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[Series, Series, Series]:
    """Return hourly import, export (``change``) and spot price (``mean``) series."""
    instance = get_instance(hass)
    meters = await instance.async_add_executor_job(
        statistics_during_period,
        hass,
        start_utc,
        end_utc,
        {import_id, export_id},
        "hour",
        None,
        {"change"},
    )
    prices = await instance.async_add_executor_job(
        statistics_during_period,
        hass,
        start_utc,
        end_utc,
        {price_id},
        "hour",
        None,
        {"mean"},
    )
    for label, entity_id, found in (
        ("Bezug", import_id, meters),
        ("Einspeisung", export_id, meters),
        ("Börsenpreis", price_id, prices),
    ):
        if not found.get(entity_id):
            raise CalcError(f"Keine Langzeitstatistik für {label} ({entity_id}) vorhanden.")
    return (
        _series(meters[import_id], "change"),  # type: ignore[arg-type]
        _series(meters[export_id], "change"),  # type: ignore[arg-type]
        _series(prices[price_id], "mean"),  # type: ignore[arg-type]
    )
