"""Pure calculation core (no Home Assistant imports)."""

from .engine import SCENARIOS, build_days, dp_day, evaluate, import_price
from .fees import (
    QUARTERS,
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
from .models import CalcError, Hour, Params, Result, ScenarioResult, Slot

__all__ = [
    "QUARTERS",
    "SCENARIOS",
    "CalcError",
    "Hour",
    "Params",
    "Result",
    "ScenarioResult",
    "Slot",
    "TariffWindow",
    "WindowError",
    "build_days",
    "day_stages",
    "default_windows",
    "dp_day",
    "evaluate",
    "import_price",
    "price",
    "project_day",
    "quarter_of",
    "slot_at",
    "slots",
    "stage",
    "validate_windows",
    "windows_from_quarters",
]
