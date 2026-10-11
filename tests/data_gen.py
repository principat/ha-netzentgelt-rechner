"""Synthetic test data (fixed seed, invented values, no real meter readings)."""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, time, timedelta, tzinfo

Series = dict[datetime, float]


def synthetic_year(
    start: date, days: int, tz: tzinfo, seed: int = 42
) -> tuple[Series, Series, Series]:
    """Hourly import/export (kWh) and spot price (EUR/kWh netto), keyed by UTC hour starts."""
    rng = random.Random(seed)
    imp: Series = {}
    exp: Series = {}
    spot: Series = {}
    cursor = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC)
    stop = datetime.combine(start + timedelta(days=days), time.min, tzinfo=tz).astimezone(UTC)
    while cursor < stop:
        local = cursor.astimezone(tz)
        doy = local.timetuple().tm_yday
        winter = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 15) / 365)  # 1 in January
        sun = max(0.0, math.sin(math.pi * (local.hour - 6) / 12)) * (1.0 - 0.8 * winter)
        load = 0.25 + 0.35 * winter + (0.3 if local.hour in (7, 8, 18, 19, 20) else 0.0)
        net = load + rng.uniform(-0.05, 0.05) - 4.0 * sun
        imp[cursor] = round(max(0.0, net), 4)
        exp[cursor] = round(max(0.0, -net), 4)
        price = 0.09 + 0.04 * winter + 0.03 * math.cos(2 * math.pi * (local.hour - 19) / 24)
        price -= 0.09 * sun * rng.random()  # occasional negative midday prices in summer
        spot[cursor] = round(price + rng.uniform(-0.01, 0.01), 5)
        cursor += timedelta(hours=1)
    return imp, exp, spot
