from __future__ import annotations

import pytest

from custom_components.netzentgelt_rechner.calc import Params

# UI units (ct/kWh, %, EUR/year, kWh); mirrors const.NUMBER_PARAMS defaults
UI_DEFAULTS: dict[str, float] = {
    "fixed": 34.1,
    "st": 11.06,
    "nt": 4.41,
    "ht": 16.07,
    "levies": 8.8,
    "vat": 19.0,
    "markup": 2.0,
    "dyn_base": 40.0,
    "rebate": 162.91,
    "m3_base_delta": 0.0,
    "feedin": 6.29,
    "eta_rt": 88.0,
    "flex_kwh": 13.5,
    "extra_kwh": 14.4,
    "c_rate": 0.5,
    "wear": 0.0,
    "invest": 1500.0,
}
WINDOW = "NNNNNSSSSSSHHSSSSHHSSSSN"
WINDOWS = {q: WINDOW for q in ("Q1", "Q2", "Q3", "Q4")}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--update-golden", action="store_true", help="rewrite golden files")


@pytest.fixture
def params() -> Params:
    return Params.from_ui(UI_DEFAULTS)


@pytest.fixture
def windows() -> dict[str, str]:
    return dict(WINDOWS)
