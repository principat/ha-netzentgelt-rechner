"""AK-5: fixed synthetic year -> golden results (update only deliberately with --update-golden)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from data_gen import synthetic_year

from custom_components.netzentgelt_rechner.calc import build_days, evaluate

GOLDEN = Path(__file__).parent / "golden" / "year.json"
BERLIN = ZoneInfo("Europe/Berlin")


def _flatten(node: dict, prefix: str = "") -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def test_golden_year(request, params, windows):  # AK-5
    imp, exp, spot = synthetic_year(date(2025, 10, 1), 365, BERLIN)
    days = build_days(imp, exp, spot, BERLIN)
    assert len(days) == 365
    actual = evaluate(days, params, windows).to_dict()
    if request.config.getoption("--update-golden"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip("golden file rewritten")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    flat_actual, flat_expected = _flatten(actual), _flatten(expected)
    assert flat_actual.keys() == flat_expected.keys()
    for key, value in flat_expected.items():
        if value is None:
            assert flat_actual[key] is None, key
        else:
            assert flat_actual[key] == pytest.approx(value, abs=0.01), key
