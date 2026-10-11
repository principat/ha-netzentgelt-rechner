"""Pure calculation core (no Home Assistant imports)."""

from .engine import SCENARIOS, build_days, dp_day, evaluate, import_price
from .fees import QUARTERS, price, quarter_of, slot_at, slots, stage, validate_windows
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
    "build_days",
    "dp_day",
    "evaluate",
    "import_price",
    "price",
    "quarter_of",
    "slot_at",
    "slots",
    "stage",
    "validate_windows",
]
