"""Data model of the calculation core (pure Python, no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

# UI keys whose unit is ct/kWh (converted to EUR/kWh internally)
_CT_KEYS = ("fixed", "st", "nt", "ht", "levies", "markup", "feedin", "wear")


@dataclass(frozen=True, slots=True)
class Params:
    """Calculation parameters in internal units (EUR, kWh, fractions)."""

    fixed: float  # EUR/kWh brutto
    st: float
    nt: float
    ht: float
    levies: float
    vat: float  # factor, e.g. 1.19
    markup: float  # EUR/kWh netto
    dyn_base: float  # EUR/year
    rebate: float  # EUR/year
    m3_base_delta: float  # EUR/year
    feedin: float  # EUR/kWh
    eta_rt: float  # fraction (round trip)
    flex_kwh: float
    extra_kwh: float
    power_kw: float  # charge/discharge power of the existing storage
    extra_power_kw: float  # additional power of the extension
    wear: float  # EUR/kWh throughput
    invest: float  # EUR
    grid_import_kw: float = 0.0  # connection limit, 0 = unlimited
    grid_export_kw: float = 0.0  # connection limit, 0 = unlimited
    step: float = 1.0  # fill level grid in kWh

    @classmethod
    def from_ui(cls, values: Mapping[str, float]) -> Params:
        """Convert user inputs (ct/kWh, %, EUR/year, kWh) to internal units."""
        v: dict[str, Any] = dict(values)
        for key in _CT_KEYS:
            v[key] = v[key] / 100.0
        v["vat"] = 1.0 + v["vat"] / 100.0
        v["eta_rt"] = v["eta_rt"] / 100.0
        return cls(**{name: float(v[name]) for name in cls.__dataclass_fields__ if name in v})


class Hour(NamedTuple):
    """One local hour of a day: energy in kWh, spot price in EUR/kWh netto."""

    h: int
    imp: float
    exp: float
    spot: float


class Slot(NamedTuple):
    """One hourly slot of the grid-fee series."""

    start: datetime
    end: datetime
    stage: str  # 'N' | 'S' | 'H'
    price_per_kwh: float  # EUR/kWh brutto


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Savings in EUR/year against today's fixed price."""

    passiv: float
    speicher: float
    erweiterung: float
    mehrwert: float
    amortisation_jahre: float | None


@dataclass(frozen=True, slots=True)
class Result:
    """Result of one calculation run."""

    tage: int
    bezug_kwh: float
    einspeisung_kwh: float
    boersenmittel: float  # EUR/kWh netto
    modul1: float
    szenarien: dict[str, ScenarioResult]

    def to_dict(self) -> dict[str, Any]:
        """Attribute representation (2 decimals), see docs/02 §4.2."""
        scenarios: dict[str, Any] = {"modul1": {"passiv": round(self.modul1, 2)}}
        for name, s in self.szenarien.items():
            scenarios[name] = {
                "passiv": round(s.passiv, 2),
                "speicher": round(s.speicher, 2),
                "erweiterung": round(s.erweiterung, 2),
                "mehrwert": round(s.mehrwert, 2),
                "amortisation_jahre": (
                    None if s.amortisation_jahre is None else round(s.amortisation_jahre, 2)
                ),
            }
        return {
            "basis": {
                "tage": self.tage,
                "bezug_kwh": round(self.bezug_kwh, 1),
                "einspeisung_kwh": round(self.einspeisung_kwh, 1),
                "boersenmittel_ct": round(self.boersenmittel * 100.0, 2),
            },
            "szenarien": scenarios,
        }


class CalcError(Exception):
    """Expected calculation failure with a user-readable message (AK-8)."""
