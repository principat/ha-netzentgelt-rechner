from __future__ import annotations

import itertools
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.netzentgelt_rechner.calc import (
    Params,
    price,
    quarter_of,
    slot_at,
    slots,
    stage,
    validate_windows,
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


def test_stage_and_price(params, windows):  # AK-3
    assert stage(windows, "Q1", 0) == "N"
    assert stage(windows, "Q1", 5) == "S"
    assert stage(windows, "Q1", 11) == "H"
    assert price("N", "Q1", params) == pytest.approx(0.0441)
    assert price("S", "Q2", params) == pytest.approx(0.1106)
    assert price("H", "Q3", params) == pytest.approx(0.1607)


def test_stage_rejects_bad_input(windows, params):
    with pytest.raises(ValueError):
        stage(windows, "Q1", 24)
    with pytest.raises(ValueError):
        stage(windows, "Q1", -1)
    with pytest.raises(ValueError):
        price("X", "Q1", params)


def test_uniform_windows(params):  # AK-3: only N / only H
    only_n = {q: "N" * 24 for q in ("Q1", "Q2", "Q3", "Q4")}
    only_h = {q: "H" * 24 for q in ("Q1", "Q2", "Q3", "Q4")}
    now = datetime(2026, 5, 5, 12, 30, tzinfo=BERLIN)
    assert {s.stage for s in slots(now, params, only_n)} == {"N"}
    assert {s.price_per_kwh for s in slots(now, params, only_h)} == {params.ht}


def test_validate_windows(windows):  # AK-2
    validate_windows(windows)
    for bad in ("N" * 23, "N" * 25, "X" * 24, "n" * 24):
        with pytest.raises(ValueError):
            validate_windows({**windows, "Q2": bad})
    with pytest.raises(ValueError):
        validate_windows({"Q1": "N" * 24})


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


def test_slots_quarter_changes_at_local_midnight(params):  # AK-3
    windows = {
        "Q1": "H" * 24,
        "Q2": "N" * 24,
        "Q3": "S" * 24,
        "Q4": "S" * 24,
    }
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
