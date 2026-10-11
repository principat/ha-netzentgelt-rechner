"""Hub: parameters, persistence, single-flight calculation and schedule (docs/02 §1, §3, §6)."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import calc
from .const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DEFAULT_EXPORT,
    DEFAULT_IMPORT,
    DEFAULT_PRICE,
    DEFAULT_WINDOW,
    DOMAIN,
    NUMBER_PARAMS,
    SIGNAL_UPDATE,
    STAGE_NAMES,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_NONE,
    STATUS_RUNNING,
)
from .data import async_load_statistics, period

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
SAVE_DELAY = 5
START_DELAY = 300
TIMEOUT_S = 120
PAUSE_S = 0.002


class CalcCancelled(Exception):
    """Raised inside the executor thread when the run is cancelled (timeout)."""


class Hub:
    """One per config entry; the only interface of the entities to the state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.params: dict[str, float] = {k: v[5] for k, v in NUMBER_PARAMS.items()}
        self.windows: list[calc.TariffWindow] = calc.default_windows(dt_util.now().year)
        self.results: dict[str, Any] | None = None
        self.status = STATUS_NONE
        self.error: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ configuration

    @property
    def sources(self) -> tuple[str, str, str]:
        conf = {**self.entry.data, **self.entry.options}
        return (
            conf.get(CONF_IMPORT, DEFAULT_IMPORT),
            conf.get(CONF_EXPORT, DEFAULT_EXPORT),
            conf.get(CONF_PRICE, DEFAULT_PRICE),
        )

    @property
    def calc_params(self) -> calc.Params:
        return calc.Params.from_ui(self.params)

    # ------------------------------------------------------------------ persistence

    async def async_load(self) -> None:
        """Load stored state; unknown keys are ignored, missing ones keep the default."""
        stored = await self._store.async_load()
        if not stored:
            return
        for key, value in (stored.get("params") or {}).items():
            if key in self.params and isinstance(value, int | float):
                self.params[key] = float(value)
        windows = self._parse_windows(stored.get("windows"))
        if windows is not None:
            self.windows = windows
        self.results = stored.get("results")
        self.error = stored.get("error")
        status = stored.get("status", STATUS_NONE)
        if status == STATUS_RUNNING:  # HA stopped during a run
            status = STATUS_DONE if self.results else STATUS_NONE
        self.status = status

    @staticmethod
    def _parse_windows(raw: Any) -> list[calc.TariffWindow] | None:
        """Stored windows (list) or v1.0.0 quarterly windows (dict, AK-17); None if unusable."""
        try:
            if isinstance(raw, dict):
                quarters: dict[str, str] = {}
                for q in calc.QUARTERS:
                    text = raw.get(q)
                    ok = isinstance(text, str) and len(text) == 24 and set(text) <= set("NSH")
                    quarters[q] = text if isinstance(text, str) and ok else DEFAULT_WINDOW
                windows = calc.windows_from_quarters(quarters, dt_util.now().year)
            elif isinstance(raw, list):
                windows = [calc.TariffWindow.from_dict(w) for w in raw]
            else:
                return None
            calc.validate_windows(windows)
        except ValueError:  # includes WindowError
            return None
        return windows

    def _snapshot(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "windows": [w.to_dict() for w in self.windows],
            "results": self.results,
            "status": self.status,
            "error": self.error,
        }

    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._snapshot, SAVE_DELAY)

    async def async_flush(self) -> None:
        await self._store.async_save(self._snapshot())

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # ------------------------------------------------------------------ inputs (AK-2)

    @callback
    def async_set_param(self, key: str, value: float) -> None:
        """Set a parameter; no recalculation is triggered (AK-2)."""
        if key not in NUMBER_PARAMS:
            raise ServiceValidationError(f"Unbekannter Parameter: {key}")
        _, _, low, high, _, _ = NUMBER_PARAMS[key]
        if not low <= value <= high:
            raise ServiceValidationError(f"{key}: Wert {value} außerhalb {low}..{high}")
        self.params[key] = float(value)
        self._schedule_save()
        self._notify()

    @callback
    def async_set_windows(self, windows: list[calc.TariffWindow]) -> None:
        """Replace the tariff windows (AK-13); raises calc.WindowError if invalid (AK-14).

        Updates the grid-fee sensor immediately; no recalculation is triggered.
        """
        calc.validate_windows(windows)
        self.windows = list(windows)
        self._schedule_save()
        self._notify()

    # ------------------------------------------------------------------ grid fee series

    def current_slot(self, now: datetime | None = None) -> calc.Slot:
        return calc.slot_at(now or dt_util.now(), self.calc_params, self.windows)

    def fee_attributes(self, now: datetime | None = None) -> dict[str, Any]:
        """Attributes of the grid-fee sensor (docs/02 §4.1)."""
        now = now or dt_util.now()
        p = self.calc_params
        slot = calc.slot_at(now, p, self.windows)
        return {
            "stufe": STAGE_NAMES[slot.stage],
            "quartal": calc.quarter_of(now.date()),
            "preise": {
                "nt": self.params["nt"],
                "st": self.params["st"],
                "ht": self.params["ht"],
            },
            "zeitplan": [{**w.to_dict(), "stufe": STAGE_NAMES[w.stage]} for w in self.windows],
            "data": [
                {
                    "start_time": s.start.isoformat(),
                    "end_time": s.end.isoformat(),
                    "stufe": s.stage,
                    "price_per_kwh": round(s.price_per_kwh, 6),
                }
                for s in calc.slots(now, p, self.windows)
            ],
        }

    # ------------------------------------------------------------------ calculation (AK-6/7/8)

    async def async_calculate(self) -> None:
        """Run one calculation; a run in progress makes this a no-op (single flight)."""
        if self._lock.locked():
            return
        async with self._lock:
            started = time.monotonic()
            self.status = STATUS_RUNNING
            self.error = None
            self._notify()
            try:
                self.results = await self._run(started)
                self.status = STATUS_DONE
            except calc.CalcError as err:
                self.status, self.error = STATUS_ERROR, str(err)
                _LOGGER.warning("Berechnung nicht möglich: %s", err)
            except TimeoutError:
                self.status = STATUS_ERROR
                self.error = f"Zeitüberschreitung nach {TIMEOUT_S} s."
                _LOGGER.warning(self.error)
            except Exception:
                self.status, self.error = STATUS_ERROR, "Interner Fehler, siehe Log"
                _LOGGER.exception("Unerwarteter Fehler bei der Berechnung")
            finally:
                try:
                    await self.async_flush()
                except Exception:
                    _LOGGER.exception("Speichern der Ergebnisse fehlgeschlagen")
                self._notify()

    async def _run(self, started: float) -> dict[str, Any]:
        tz = dt_util.get_default_time_zone()
        today = dt_util.now().date()
        start, end, start_utc, end_utc = period(today, tz)
        import_id, export_id, price_id = self.sources
        params_ui = dict(self.params)
        params = calc.Params.from_ui(params_ui)
        windows = list(self.windows)
        ref_year = today.year
        imp, exp, spot = await async_load_statistics(
            self.hass, import_id, export_id, price_id, start_utc, end_utc
        )
        _LOGGER.debug("Statistik geladen: %d/%d/%d Zeilen", len(imp), len(exp), len(spot))
        cancel = threading.Event()

        def pause() -> None:
            if cancel.is_set():
                raise CalcCancelled
            time.sleep(PAUSE_S)

        def work() -> calc.Result:
            days = calc.build_days(imp, exp, spot, tz)
            return calc.evaluate(days, params, windows, ref_year=ref_year, pause=pause)

        try:
            async with asyncio.timeout(TIMEOUT_S):
                result = await self.hass.async_add_executor_job(work)
        except TimeoutError:
            cancel.set()
            raise
        attrs = result.to_dict()
        attrs["basis"].update(von=start.isoformat(), bis=(end - timedelta(days=1)).isoformat())
        attrs.update(
            berechnet_am=dt_util.now().isoformat(),
            dauer_s=round(time.monotonic() - started, 1),
            annahmen=params_ui,
            tarifzeiten=[w.to_dict() for w in windows],
        )
        _LOGGER.debug("Berechnung fertig in %.1f s (%d Tage)", attrs["dauer_s"], result.tage)
        return attrs

    # ------------------------------------------------------------------ schedule (AK-9)

    @callback
    def async_start(self) -> None:
        """Register the delayed first run and the monthly run."""
        cancel_delay: CALLBACK_TYPE | None = None

        @callback
        def _delayed(_now: datetime) -> None:
            if self.results is None:
                self._spawn("netzentgelt_rechner first run")

        @callback
        def _started(_hass: HomeAssistant) -> None:
            nonlocal cancel_delay
            if self.results is None:
                cancel_delay = async_call_later(self.hass, START_DELAY, _delayed)

        @callback
        def _monthly(now: datetime) -> None:
            if dt_util.as_local(now).day == 1:
                self._spawn("netzentgelt_rechner monthly run")

        self.entry.async_on_unload(async_at_started(self.hass, _started))
        self.entry.async_on_unload(
            async_track_time_change(self.hass, _monthly, hour=3, minute=30, second=0)
        )
        self.entry.async_on_unload(lambda: cancel_delay() if cancel_delay else None)

    def _spawn(self, name: str) -> None:
        self.entry.async_create_background_task(self.hass, self.async_calculate(), name)

    @callback
    def async_request_calculation(self) -> None:
        """Start a run in the background (button)."""
        self._spawn("netzentgelt_rechner manual run")
