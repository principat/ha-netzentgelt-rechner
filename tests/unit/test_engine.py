from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.netzentgelt_rechner.calc import (
    CalcError,
    Hour,
    build_days,
    dp_day,
    evaluate,
    import_price,
)

BERLIN = ZoneInfo("Europe/Berlin")
DAY = date(2026, 1, 15)  # Q1 -> default windows


def _hours(spot: float = 0.1, imp: float = 1.0, exp: float = 0.0, n: int = 24) -> list[Hour]:
    return [Hour(h % 24, imp, exp, spot) for h in range(n)]


def _year(day_hours: list[Hour], n_days: int = 10) -> dict[date, list[Hour]]:
    return {date(2026, 1, 1) + timedelta(days=i): list(day_hours) for i in range(n_days)}


# --- price formulas (docs/01 §4), computed by hand -------------------------------------


def test_import_price_formulas(params, windows):  # AK-5
    # Q1, hour 0 -> N (0.0441), hour 11 -> H (0.1607); spot 0.10, markup 0.02, vat 1.19
    e_fix = 0.341 - 0.1106 - 0.088
    assert import_price("heute", params, windows, DAY, 0, 0.10) == pytest.approx(0.341)
    assert import_price("modul3", params, windows, DAY, 0, 0.10) == pytest.approx(
        e_fix + 0.0441 + 0.088
    )
    assert import_price("modul3", params, windows, DAY, 11, 0.10) == pytest.approx(
        e_fix + 0.1607 + 0.088
    )
    assert import_price("dynamisch", params, windows, DAY, 11, 0.10) == pytest.approx(
        (0.10 + 0.02) * 1.19 + 0.1106 + 0.088
    )
    assert import_price("kombination", params, windows, DAY, 11, 0.10) == pytest.approx(
        (0.10 + 0.02) * 1.19 + 0.1607 + 0.088
    )


def test_negative_spot_is_passed_through(params, windows):
    low = import_price("kombination", params, windows, DAY, 12, -0.20)
    assert low == pytest.approx((-0.20 + 0.02) * 1.19 + 0.1607 + 0.088)
    assert low > 0  # grid fee and levies stay positive


def test_unknown_scenario(params, windows):
    with pytest.raises(ValueError):
        import_price("nope", params, windows, DAY, 0, 0.1)


# --- build_days ------------------------------------------------------------------------


def _series(day: date, hours: int, value: float | None = 0.1) -> dict[datetime, float | None]:
    start = datetime(day.year, day.month, day.day, tzinfo=BERLIN).astimezone(UTC)
    return {start + timedelta(hours=i): value for i in range(hours)}


def test_build_days_keeps_complete_days_only():  # AK-8
    spot = {**_series(date(2026, 1, 1), 24), **_series(date(2026, 1, 2), 20)}
    days = build_days({}, {}, spot, BERLIN)
    assert list(days) == [date(2026, 1, 1)]
    assert [h.h for h in days[date(2026, 1, 1)]] == list(range(24))


def test_build_days_dst_lengths():  # AK-3
    spring = build_days({}, {}, _series(date(2026, 3, 29), 23), BERLIN)
    autumn = build_days({}, {}, _series(date(2026, 10, 25), 25), BERLIN)
    assert len(spring[date(2026, 3, 29)]) == 23
    assert len(autumn[date(2026, 10, 25)]) == 25


def test_build_days_cleans_values():  # AK-8
    spot = _series(date(2026, 1, 1), 24)
    ts = sorted(spot)
    spot[ts[3]] = None  # hour without price is skipped -> 23 hours remain
    imp: dict[datetime, float | None] = {ts[0]: -5.0, ts[1]: math.nan, ts[2]: 2.0, ts[4]: None}
    exp: dict[datetime, float | None] = {ts[0]: 1.5}
    hours = build_days(imp, exp, spot, BERLIN)[date(2026, 1, 1)]
    assert len(hours) == 23
    assert hours[0].imp == 0.0  # negative meter change (reset) -> 0
    assert hours[1].imp == 0.0  # NaN -> 0
    assert hours[2].imp == 2.0
    assert hours[0].exp == 1.5


def test_build_days_skips_nan_price():
    spot = _series(date(2026, 1, 1), 24)
    spot[sorted(spot)[0]] = math.nan
    assert len(build_days({}, {}, spot, BERLIN)[date(2026, 1, 1)]) == 23


# --- dp_day invariants -----------------------------------------------------------------


def test_dp_zero_capacity(params):
    assert dp_day([0.3] * 4, [0.0] * 4, [1.0] * 4, [0.0] * 4, 0.0, params) == 0.0


def test_dp_is_never_a_loss_and_monotone_in_capacity(params):  # invariants
    cb = [0.05, 0.05, 0.40, 0.40, 0.05, 0.40]
    fi = [0.06] * 6
    imp = [0.5, 0.5, 2.0, 2.0, 0.5, 2.0]
    exp = [0.0] * 6
    small = dp_day(cb, fi, imp, exp, 2.0, params)
    large = dp_day(cb, fi, imp, exp, 6.0, params)
    assert small <= 0.0
    assert large <= small  # more storage is never worse
    assert large < 0.0  # real arbitrage exists here


def test_dp_perfect_efficiency_conserves_energy(params):  # invariants
    # eta 100 %: charge 1 kWh at 0.1, discharge into import at 0.3 -> gain exactly 0.2/kWh
    p = replace(params, eta_rt=1.0, c_rate=1.0)
    cost = dp_day([0.1, 0.3], [0.0, 0.0], [0.0, 5.0], [0.0, 0.0], 2.0, p)
    assert cost == pytest.approx(-0.2 * 2.0 + 0.0, abs=1e-9)


def test_dp_no_export_credit_at_negative_price(params):  # negative price: fi = 0
    p = replace(params, c_rate=1.0)
    with_fi = dp_day([0.3, 0.3], [0.0, 0.0], [0.0, 0.0], [2.0, 0.0], 2.0, p)
    assert with_fi == 0.0  # charging from surplus (worth 0) and discharging nowhere useful


def test_dp_wear_makes_trading_unprofitable(params):
    p = replace(params, wear=10.0)
    assert dp_day([0.05, 0.4], [0.0, 0.0], [0.0, 3.0], [0.0, 0.0], 2.0, p) == 0.0


# --- evaluate --------------------------------------------------------------------------


def test_evaluate_flat_day_has_no_storage_gain(params, windows):  # AK-5
    # constant spot, import every hour: modul1 only the rebate, passive savings by formula
    result = evaluate(_year(_hours(spot=0.10)), params, windows, ref_year=2026, min_days=5)
    assert result.tage == 10
    assert result.modul1 == pytest.approx(162.91)
    assert result.bezug_kwh == pytest.approx(24 * 365.0)
    k = result.szenarien["kombination"]
    stages_cost = sum(import_price("kombination", params, windows, DAY, h, 0.10) for h in range(24))
    expected = (24 * params.fixed - stages_cost) * 365 + params.rebate - params.dyn_base
    assert k.passiv == pytest.approx(expected)
    assert k.speicher >= k.passiv - 1e-9


def test_evaluate_scenario_ordering_and_amortisation(params, windows):  # invariants
    day = [Hour(h, 1.0, 0.0, 0.02 if h < 6 else 0.30) for h in range(24)]
    result = evaluate(_year(day), params, windows, ref_year=2026, min_days=5)
    for s in result.szenarien.values():
        assert s.speicher >= s.passiv
        assert s.erweiterung >= s.speicher - 1e-9
        assert s.mehrwert == pytest.approx(s.erweiterung - s.speicher)
    dyn = result.szenarien["dynamisch"]
    assert dyn.mehrwert > 1.0
    assert dyn.amortisation_jahre == pytest.approx(params.invest / dyn.mehrwert)


def test_evaluate_no_amortisation_without_gain(params, windows):
    result = evaluate(
        _year(_hours(imp=0.0)), params, windows, ref_year=2026, min_days=5
    )  # no import at all
    for s in result.szenarien.values():
        assert s.mehrwert == 0.0
        assert s.amortisation_jahre is None


def test_evaluate_requires_enough_days(params, windows):  # AK-8
    with pytest.raises(CalcError, match="199"):
        evaluate(_year(_hours(), 199), params, windows, ref_year=2026)


def test_evaluate_calls_pause_and_can_cancel(params, windows):  # AK-7
    calls: list[int] = []

    def pause() -> None:
        calls.append(1)

    evaluate(_year(_hours(), 6), params, windows, ref_year=2026, pause=pause, min_days=5)
    assert len(calls) == 6 * (1 + 3 * 2)  # per day: one per optimisation and one at the end

    class Cancelled(Exception):
        pass

    def cancel() -> None:
        raise Cancelled

    with pytest.raises(Cancelled):
        evaluate(_year(_hours(), 6), params, windows, ref_year=2026, pause=cancel, min_days=5)


def test_result_to_dict_rounds(params, windows):  # docs/02 §4.2
    out = evaluate(
        _year(_hours(spot=0.1234567)), params, windows, ref_year=2026, min_days=5
    ).to_dict()
    assert set(out["szenarien"]) == {"modul1", "modul3", "dynamisch", "kombination"}
    assert out["szenarien"]["modul1"] == {"passiv": 162.91}
    assert out["szenarien"]["dynamisch"]["amortisation_jahre"] is None  # flat spot, no arbitrage
    assert out["basis"]["tage"] == 10
    assert out["basis"]["boersenmittel_ct"] == pytest.approx(12.35)
    for s in ("modul3", "dynamisch", "kombination"):
        for value in out["szenarien"][s].values():
            assert value is None or round(value, 2) == value
