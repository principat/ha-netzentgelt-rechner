from __future__ import annotations

import itertools
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.netzentgelt_rechner.calc import (
    Params,
    TariffWindow,
    WindowError,
    day_stages,
    default_windows,
    price,
    project_day,
    quarter_of,
    slot_at,
    slots,
    stage,
    validate_windows,
    windows_from_quarters,
)

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("day", "quarter"),
    [
        (date(2026, 1, 1), "Q1"),
        (date(2026, 3, 31), "Q1"),
        (date(2026, 4, 1), "Q2"),
        (date(2026, 9, 30), "Q3"),
        (date(2026, 10, 1), "Q4"),
        (date(2026, 12, 31), "Q4"),
    ],
)
def test_quarter_boundaries(day, quarter):  # AK-3
    assert quarter_of(day) == quarter


def _w(stage_, start, end, from_hour, to_hour):
    return TariffWindow(stage_, start, end, from_hour, to_hour)


Q1 = (date(2026, 1, 1), date(2026, 3, 31))


def test_stage_and_price(params, windows):  # AK-3
    d = date(2026, 1, 15)
    assert stage(windows, d, 0) == "N"
    assert stage(windows, d, 5) == "S"
    assert stage(windows, d, 11) == "H"
    assert price("N", "Q1", params) == pytest.approx(0.0441)
    assert price("S", "Q2", params) == pytest.approx(0.1106)
    assert price("H", "Q3", params) == pytest.approx(0.1607)


def test_stage_rejects_bad_input(windows, params):
    with pytest.raises(ValueError):
        stage(windows, date(2026, 1, 1), 24)
    with pytest.raises(ValueError):
        stage(windows, date(2026, 1, 1), -1)
    with pytest.raises(ValueError):
        price("X", "Q1", params)


def test_everything_outside_windows_is_standard():  # AK-15
    assert stage([], date(2026, 6, 1), 12) == "S"
    w = [_w("H", date(2026, 6, 1), date(2026, 6, 30), 10, 12)]
    assert stage(w, date(2026, 5, 31), 10) == "S"
    assert stage(w, date(2026, 7, 1), 10) == "S"
    assert stage(w, date(2026, 6, 15), 9) == "S"


def test_window_bounds_are_inclusive_dates_and_exclusive_end_hour():  # AK-3
    w = [_w("H", date(2026, 6, 1), date(2026, 6, 30), 17, 19)]
    assert stage(w, date(2026, 6, 1), 17) == "H"
    assert stage(w, date(2026, 6, 30), 18) == "H"
    assert stage(w, date(2026, 6, 15), 19) == "S"
    assert day_stages(w, date(2026, 6, 15)) == "S" * 17 + "HH" + "S" * 5


def test_window_over_midnight_and_all_day():  # AK-15
    night = [_w("N", date(2026, 1, 1), date(2026, 12, 31), 23, 5)]
    assert day_stages(night, date(2026, 3, 3)) == "N" * 5 + "S" * 18 + "N"
    full = [_w("H", date(2026, 1, 1), date(2026, 12, 31), 0, 24)]
    assert day_stages(full, date(2026, 3, 3)) == "H" * 24


def test_uniform_windows(params):  # AK-3: only N / only H
    only_n = [_w("N", date(2026, 1, 1), date(2026, 12, 31), 0, 24)]
    only_h = [_w("H", date(2026, 1, 1), date(2026, 12, 31), 0, 24)]
    now = datetime(2026, 5, 5, 12, 30, tzinfo=BERLIN)
    assert {s.stage for s in slots(now, params, only_n)} == {"N"}
    assert {s.price_per_kwh for s in slots(now, params, only_h)} == {params.ht}


def test_validate_windows_ok(windows):  # AK-14
    validate_windows(windows)
    validate_windows([])
    validate_windows(  # touching, not overlapping: other hours / other dates
        [
            _w("H", *Q1, 10, 12),
            _w("N", *Q1, 12, 14),
            _w("H", date(2026, 4, 1), date(2026, 4, 30), 10, 12),
        ]
    )


@pytest.mark.parametrize(
    ("window", "code"),
    [
        (_w("X", *Q1, 1, 2), "stage"),
        (_w("H", date(2026, 3, 31), date(2026, 1, 1), 1, 2), "date_order"),
        (_w("H", *Q1, 24, 5), "hour_range"),
        (_w("H", *Q1, -1, 5), "hour_range"),
        (_w("H", *Q1, 3, 0), "hour_range"),
        (_w("H", *Q1, 3, 25), "hour_range"),
        (_w("H", *Q1, 5, 5), "hours_equal"),
    ],
)
def test_validate_windows_single_errors(window, code):  # AK-14
    with pytest.raises(WindowError) as err:
        validate_windows([_w("N", *Q1, 0, 1), window])
    assert err.value.code == code
    assert err.value.index == 1
    assert err.value.other is None


def test_validate_windows_overlap(windows):  # AK-14
    base = [_w("H", *Q1, 17, 19)]
    for other in (
        _w("N", date(2026, 3, 31), date(2026, 5, 1), 18, 20),  # touching dates, shared hour
        _w("H", *Q1, 17, 19),  # identical, same stage
        _w("N", *Q1, 16, 18),
        _w("N", *Q1, 22, 18),  # over midnight reaching into 17:00
    ):
        with pytest.raises(WindowError) as err:
            validate_windows([*base, other])
        assert (err.value.code, err.value.index, err.value.other) == ("overlap", 1, 0)


def test_project_day():  # AK-16
    assert project_day(date(2025, 10, 1), 2026) == date(2026, 10, 1)
    assert project_day(date(2024, 2, 29), 2026) == date(2026, 2, 28)
    assert project_day(date(2024, 2, 29), 2028) == date(2028, 2, 29)


def test_windows_from_quarters_roundtrip():  # AK-16, AK-17
    quarters = {
        "Q1": "NNNNNSSSSSSHHSSSSHHSSSSN",
        "Q2": "H" * 24,
        "Q3": "S" * 24,
        "Q4": "N" * 24,
    }
    ws = windows_from_quarters(quarters, 2026)
    validate_windows(ws)
    for q, (first, last) in {
        "Q1": (date(2026, 1, 1), date(2026, 3, 31)),
        "Q2": (date(2026, 4, 1), date(2026, 6, 30)),
        "Q3": (date(2026, 7, 1), date(2026, 9, 30)),
        "Q4": (date(2026, 10, 1), date(2026, 12, 31)),
    }.items():
        for day in (first, last):
            assert day_stages(ws, day) == quarters[q]
    assert _w("N", date(2026, 1, 1), date(2026, 3, 31), 23, 5) in ws  # merged over midnight
    assert not [w for w in ws if w.start.month in (7, 8, 9)]  # all-standard quarter: no entry


def test_windows_from_quarters_rejects_bad_input():
    with pytest.raises(ValueError):
        windows_from_quarters({"Q1": "N" * 24}, 2026)
    with pytest.raises(ValueError):
        windows_from_quarters({q: "X" * 24 for q in ("Q1", "Q2", "Q3", "Q4")}, 2026)


def test_default_windows():  # docs/01 §7
    ws = default_windows(2027)
    validate_windows(ws)
    assert day_stages(ws, date(2027, 7, 7)) == "NNNNNSSSSSSHHSSSSHHSSSSN"
    assert day_stages(ws, date(2026, 7, 7)) == "S" * 24


def test_window_dict_roundtrip():  # docs/02 §3.4
    w = _w("N", date(2026, 1, 1), date(2026, 3, 31), 23, 5)
    assert w.to_dict() == {
        "stufe": "N",
        "von": "2026-01-01",
        "bis": "2026-03-31",
        "stunde_von": 23,
        "stunde_bis": 5,
    }
    assert TariffWindow.from_dict(w.to_dict()) == w
    for bad in (
        {},
        {"stufe": "N"},
        {**w.to_dict(), "von": "kein-datum"},
        {**w.to_dict(), "stunde_von": "x"},
    ):
        with pytest.raises(ValueError):
            TariffWindow.from_dict(bad)


def test_slots_normal_day(params, windows):  # AK-3
    result = slots(datetime(2026, 10, 10, 9, 5, tzinfo=BERLIN), params, windows)
    assert len(result) == 48
    assert result[0].start == datetime(2026, 10, 10, 0, 0, tzinfo=BERLIN)
    assert result[-1].end == datetime(2026, 10, 12, 0, 0, tzinfo=BERLIN)
    assert result[0].stage == "N"
    assert result[11].stage == "H"
    assert all(a.end == b.start for a, b in itertools.pairwise(result))


def test_slots_spring_forward_has_23_hours(params, windows):  # AK-3
    result = slots(datetime(2026, 3, 29, 8, 0, tzinfo=BERLIN), params, windows)
    assert len(result) == 47


def test_slots_fall_back_has_25_hours(params, windows):  # AK-3
    result = slots(datetime(2026, 10, 25, 8, 0, tzinfo=BERLIN), params, windows)
    assert len(result) == 49


def test_slots_window_changes_at_local_midnight(params):  # AK-3
    windows = [
        _w("H", *Q1, 0, 24),
        _w("N", date(2026, 4, 1), date(2026, 6, 30), 0, 24),
    ]
    result = slots(datetime(2026, 3, 31, 12, 0, tzinfo=BERLIN), params, windows)
    assert {s.stage for s in result if s.start.day == 31} == {"H"}
    assert {s.stage for s in result if s.start.month == 4} == {"N"}


def test_slot_at_matches_series(params, windows):  # AK-3
    now = datetime(2026, 10, 10, 17, 44, tzinfo=BERLIN)
    current = slot_at(now, params, windows)
    assert current.stage == "H"
    assert current.start.hour == 17
    assert current in slots(now, params, windows)


def test_slots_requires_timezone(params, windows):
    with pytest.raises(ValueError):
        slots(datetime(2026, 1, 1, 12, 0), params, windows)


def test_from_ui_converts_units(params: Params):
    assert params.fixed == pytest.approx(0.341)
    assert params.vat == pytest.approx(1.19)
    assert params.eta_rt == pytest.approx(0.88)
    assert params.rebate == pytest.approx(162.91)
    assert params.flex_kwh == pytest.approx(13.5)
