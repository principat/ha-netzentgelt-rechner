"""Scenario prices, daily storage optimisation and yearly evaluation (pure)."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, tzinfo

from .fees import TariffWindow, day_stages, price, project_day, quarter_of, stage
from .models import CalcError, Hour, Params, Result, ScenarioResult

SCENARIOS = ("modul3", "dynamisch", "kombination")
MIN_DAYS = 200
_MIN_IMPORT_KWH = 0.5


def _scenario_price(scenario: str, p: Params, netz: float, spot: float) -> float:
    """Gross price per imported kWh in EUR for a given grid fee ``netz`` (docs/01 §4)."""
    if scenario == "heute":
        return p.fixed
    if scenario == "modul3":
        e_fix = p.fixed - p.st - p.levies
        return e_fix + netz + p.levies
    if scenario == "dynamisch":
        return (spot + p.markup) * p.vat + p.st + p.levies
    if scenario == "kombination":
        return (spot + p.markup) * p.vat + netz + p.levies
    raise ValueError(f"unknown scenario: {scenario!r}")


def import_price(
    scenario: str,
    p: Params,
    windows: Sequence[TariffWindow],
    day: date,
    hour: int,
    spot: float,
) -> float:
    """Gross price per imported kWh in EUR for a local date and hour (docs/01 §4)."""
    netz = price(stage(windows, day, hour), quarter_of(day), p)
    return _scenario_price(scenario, p, netz, spot)


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def build_days(
    imp: Mapping[datetime, float | None],
    exp: Mapping[datetime, float | None],
    spot: Mapping[datetime, float | None],
    tz: tzinfo,
) -> dict[date, list[Hour]]:
    """Group hourly rows by local day; keep only complete days (23, 24 or 25 hours).

    Keys are timezone-aware hour starts. Hours without a price are skipped, missing or
    negative consumption counts as 0.
    """
    days: dict[date, list[Hour]] = defaultdict(list)
    for ts in sorted(spot):
        s = _finite(spot[ts])
        if s is None:
            continue
        local = ts.astimezone(tz)
        i = _finite(imp.get(ts)) or 0.0
        e = _finite(exp.get(ts)) or 0.0
        days[local.date()].append(Hour(local.hour, max(0.0, i), max(0.0, e), s))
    return {d: hours for d, hours in days.items() if len(hours) in (23, 24, 25)}


def dp_day(
    cbuy: Sequence[float],
    fi: Sequence[float],
    imp: Sequence[float],
    exp: Sequence[float],
    cap_kwh: float,
    p: Params,
) -> float:
    """Minimal extra cost of one day with ``cap_kwh`` storage (<= 0 means profit). Exact DP."""
    q = p.step
    n = int(cap_kwh / q + 1e-9)
    if n <= 0:
        return 0.0
    eta = math.sqrt(p.eta_rt)
    pmax = p.c_rate * cap_kwh
    kc = max(1, int(pmax * eta / q))  # max charge steps per hour (stored energy)
    kd = max(1, int(pmax / (eta * q)))  # max discharge steps per hour
    hours = len(cbuy)
    costs: list[dict[int, float]] = []
    for h in range(hours):
        row: dict[int, float] = {0: 0.0}
        for k in range(1, kc + 1):
            bus = k * q / eta
            ab = min(exp[h], bus)
            row[k] = (bus - ab) * cbuy[h] + ab * fi[h] + p.wear * k * q
        for k in range(1, kd + 1):
            d = k * q * eta
            use = min(d, imp[h])
            row[-k] = -use * cbuy[h] - (d - use) * fi[h] + p.wear * k * q
        costs.append(row)
    value = [0.0] * (n + 1)
    for h in range(hours - 1, -1, -1):
        row = costs[h]
        nxt = [0.0] * (n + 1)
        for e in range(n + 1):
            nxt[e] = min(row[k] + value[e + k] for k in range(-min(kd, e), min(kc, n - e) + 1))
        value = nxt
    return value[0]


def evaluate(
    days: Mapping[date, Sequence[Hour]],
    p: Params,
    windows: Sequence[TariffWindow],
    *,
    ref_year: int,
    pause: Callable[[], None] | None = None,
    min_days: int = MIN_DAYS,
) -> Result:
    """Savings per scenario in EUR/year against today's fixed price.

    Tariff windows are applied by day and month only: every day is mapped to ``ref_year`` (AK-16).
    ``pause`` is called after every optimisation (and every day) so that the caller can yield
    the CPU or cancel (by raising) a long run.
    """
    n_days = len(days)
    if n_days < min_days:
        raise CalcError(
            f"Nur {n_days} vollständige Tage mit Preisen vorhanden, nötig sind {min_days}."
        )
    acc: dict[str, float] = defaultdict(float)
    for day, hrs in days.items():
        proj = project_day(day, ref_year)
        quarter = quarter_of(proj)
        stages = day_stages(windows, proj)
        netz = [price(stages[x.h], quarter, p) for x in hrs]
        imp = [x.imp for x in hrs]
        exp = [x.exp for x in hrs]
        acc["imp"] += sum(imp)
        acc["exp"] += sum(exp)
        fi = [p.feedin if x.spot >= 0 else 0.0 for x in hrs]
        for s in SCENARIOS:
            cb = [_scenario_price(s, p, n, x.spot) for n, x in zip(netz, hrs, strict=True)]
            acc[s + "_pass"] += sum(i * (p.fixed - c) for i, c in zip(imp, cb, strict=True))
            if sum(imp) > _MIN_IMPORT_KWH:
                acc[s + "_flex"] += -dp_day(cb, fi, imp, exp, p.flex_kwh, p)
                if pause is not None:
                    pause()
                acc[s + "_ext"] += -dp_day(cb, fi, imp, exp, p.flex_kwh + p.extra_kwh, p)
                if pause is not None:
                    pause()
        acc["spot_sum"] += sum(x.spot for x in hrs)
        acc["spot_n"] += len(hrs)
        if pause is not None:
            pause()
    scale = 365.0 / n_days
    base = {
        "modul3": p.rebate - p.m3_base_delta,
        "dynamisch": -p.dyn_base,
        "kombination": p.rebate - p.dyn_base - p.m3_base_delta,
    }
    scenarios: dict[str, ScenarioResult] = {}
    for s in SCENARIOS:
        passive = acc[s + "_pass"] * scale + base[s]
        mehrwert = (acc[s + "_ext"] - acc[s + "_flex"]) * scale
        scenarios[s] = ScenarioResult(
            passiv=passive,
            speicher=passive + acc[s + "_flex"] * scale,
            erweiterung=passive + acc[s + "_ext"] * scale,
            mehrwert=mehrwert,
            amortisation_jahre=p.invest / mehrwert if mehrwert > 1.0 else None,
        )
    return Result(
        tage=n_days,
        bezug_kwh=acc["imp"] * scale,
        einspeisung_kwh=acc["exp"] * scale,
        boersenmittel=acc["spot_sum"] / acc["spot_n"],
        modul1=p.rebate,
        szenarien=scenarios,
    )
