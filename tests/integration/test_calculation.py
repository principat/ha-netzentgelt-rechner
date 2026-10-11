from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from data_gen import Series, synthetic_year
from helpers import EXPORT_ID, IMPORT_ID, PRICE_ID, setup_entry, stored, unique_entity_id
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.netzentgelt_rechner.const import DOMAIN
from custom_components.netzentgelt_rechner.data import async_load_statistics as load_statistics
from custom_components.netzentgelt_rechner.data import period
from custom_components.netzentgelt_rechner.hub import Hub

BERLIN = ZoneInfo("Europe/Berlin")
pytestmark = pytest.mark.usefixtures("berlin")


def _meter_meta(statistic_id: str) -> dict:
    return {
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": None,
        "source": "recorder",
        "statistic_id": statistic_id,
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }


async def import_year(hass: HomeAssistant) -> None:
    """Import 12 full local months of synthetic statistics for the current period."""
    start, end, _, _ = period(dt_util.now().date(), BERLIN)
    imp, exp, spot = synthetic_year(start, (end - start).days, BERLIN)

    def meter_rows(series: Series) -> list[dict]:
        total = 0.0
        rows = []
        for ts in sorted(series):
            total += series[ts]
            rows.append({"start": ts, "state": total, "sum": total})
        return rows

    async_import_statistics(hass, _meter_meta(IMPORT_ID), meter_rows(imp))  # type: ignore[arg-type]
    async_import_statistics(hass, _meter_meta(EXPORT_ID), meter_rows(exp))  # type: ignore[arg-type]
    price_meta = {
        "has_sum": False,
        "mean_type": StatisticMeanType.ARITHMETIC,
        "name": None,
        "source": "recorder",
        "statistic_id": PRICE_ID,
        "unit_class": None,
        "unit_of_measurement": "EUR/kWh",
    }
    async_import_statistics(
        hass,
        price_meta,  # type: ignore[arg-type]
        [{"start": ts, "mean": v, "min": v, "max": v} for ts, v in sorted(spot.items())],
    )
    await async_wait_recording_done(hass)


async def test_missing_statistics_give_error_status(hass: HomeAssistant, entry, caplog):  # AK-8
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    await hub.async_calculate()
    assert hub.status == "fehler"
    assert "Keine Langzeitstatistik" in (hub.error or "")
    state = hass.states.get(unique_entity_id(hass, "sensor", "wirtschaftlichkeit"))
    assert state.state == "fehler"
    assert state.attributes["fehler"] == hub.error
    assert "Traceback" not in caplog.text


async def test_too_few_days_give_error_status(hass: HomeAssistant, entry, caplog):  # AK-8
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    with patch(
        "custom_components.netzentgelt_rechner.hub.async_load_statistics",
        return_value=({}, {}, {}),
    ):
        await hub.async_calculate()
    assert hub.status == "fehler"
    assert "nötig sind 200" in (hub.error or "")
    assert "Traceback" not in caplog.text


async def test_unexpected_error_is_contained(hass: HomeAssistant, entry, caplog):  # AK-8
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    with patch(
        "custom_components.netzentgelt_rechner.hub.async_load_statistics",
        side_effect=RuntimeError("boom"),
    ):
        await hub.async_calculate()
    assert hub.status == "fehler"
    assert hub.error == "Interner Fehler, siehe Log"
    assert "Unerwarteter Fehler" in caplog.text


async def test_full_calculation_and_event_loop_latency(hass: HomeAssistant, entry):  # AK-5/7/10
    await import_year(hass)
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data

    worst = 0.0
    spikes: list[tuple[float, float]] = []
    done = asyncio.Event()
    loaded = asyncio.Event()
    t0 = time.monotonic()
    real_load = load_statistics

    async def tracked_load(*args, **kwargs):
        result = await real_load(*args, **kwargs)
        loaded.set()  # the calculation phase starts here
        return result

    async def watchdog() -> None:
        nonlocal worst
        await loaded.wait()
        while not done.is_set():
            before = time.monotonic()
            await asyncio.sleep(0.01)
            delay = time.monotonic() - before - 0.01
            worst = max(worst, delay)
            if delay > 0.03:
                spikes.append((round(before - t0, 2), round(delay, 3)))

    task = hass.async_create_task(watchdog())
    with patch("custom_components.netzentgelt_rechner.hub.async_load_statistics", tracked_load):
        await hub.async_calculate()
    done.set()
    await task

    assert hub.status == "fertig", hub.error
    assert worst < 0.1, spikes  # AK-7: <50 ms target, CI tolerance 100 ms
    attrs = hass.states.get(unique_entity_id(hass, "sensor", "wirtschaftlichkeit")).attributes
    assert attrs["basis"]["tage"] in (365, 366)
    assert set(attrs["szenarien"]) == {"modul1", "modul3", "dynamisch", "kombination"}
    assert attrs["szenarien"]["modul1"] == {"passiv": 162.91}
    assert attrs["annahmen"]["nt"] == 4.41
    assert attrs["fehler"] is None
    assert attrs["dauer_s"] > 0

    # AK-10: reload keeps the results
    results = hub.results
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.results == results
    assert entry.runtime_data.status == "fertig"


async def test_single_flight(hass: HomeAssistant, entry):  # AK-6
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    calls = 0
    release = asyncio.Event()

    async def slow_run(_started: float) -> dict:
        nonlocal calls
        calls += 1
        await release.wait()
        return {"basis": {}, "szenarien": {}}

    with patch.object(hub, "_run", slow_run):
        button = unique_entity_id(hass, "button", "neu_berechnen")
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        await asyncio.sleep(0)
        assert hub.status == "rechnet"
        assert hass.states.get(unique_entity_id(hass, "sensor", "wirtschaftlichkeit")).state == (
            "rechnet"
        )
        release.set()
        await hass.async_block_till_done()
    assert calls == 1
    assert hub.status == "fertig"


async def test_first_run_is_delayed_and_only_without_results(hass, entry, freezer):  # AK-9
    with patch.object(Hub, "async_calculate") as calculate:
        await setup_entry(hass, entry)
        assert calculate.call_count == 0  # never directly at start
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=299))
        await hass.async_block_till_done()
        assert calculate.call_count == 0
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=301))
        await hass.async_block_till_done()
        assert calculate.call_count == 1


async def test_no_delayed_run_when_results_exist(hass, entry, hass_storage):  # AK-9
    hass_storage[f"{DOMAIN}.test_entry"] = stored({"basis": {}, "szenarien": {}})
    with patch.object(Hub, "async_calculate") as calculate:
        await setup_entry(hass, entry)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=400))
        await hass.async_block_till_done()
        assert calculate.call_count == 0


async def test_monthly_run_only_on_first_day(hass, entry, hass_storage):  # AK-9
    hass_storage[f"{DOMAIN}.test_entry"] = stored({"basis": {}, "szenarien": {}})
    with patch.object(Hub, "async_calculate") as calculate:
        await setup_entry(hass, entry)
        async_fire_time_changed(hass, datetime(2027, 3, 1, 3, 30, 0, tzinfo=BERLIN))
        await hass.async_block_till_done()
        assert calculate.call_count == 1
        async_fire_time_changed(hass, datetime(2027, 3, 2, 3, 30, 0, tzinfo=BERLIN))
        await hass.async_block_till_done()
        assert calculate.call_count == 1  # not on other days


async def test_persistence_of_inputs_and_results(hass, entry, hass_storage):  # AK-10
    results = {"basis": {"tage": 300}, "szenarien": {}, "berechnet_am": "2026-10-01T03:30:00"}
    hass_storage[f"{DOMAIN}.test_entry"] = stored(
        results,
        params={"nt": 5.0, "bogus": 1, "ht": "x"},
        windows={"Q2": "H" * 24, "Q3": "bad", "Q9": "N" * 24},
        status="rechnet",  # HA was stopped during a run
    )
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    assert hub.params["nt"] == 5.0
    assert hub.params["ht"] == 16.07  # invalid stored value ignored
    assert hub.windows["Q2"] == "H" * 24
    assert hub.windows["Q3"] == "NNNNNSSSSSSHHSSSSHHSSSSN"
    assert hub.status == "fertig"
    state = hass.states.get(unique_entity_id(hass, "sensor", "wirtschaftlichkeit"))
    assert state.state == "fertig"
    assert state.attributes["basis"] == {"tage": 300}


async def test_changed_inputs_are_saved(hass, entry, hass_storage, freezer):  # AK-2
    await setup_entry(hass, entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": unique_entity_id(hass, "number", "rebate"), "value": 200},
        blocking=True,
    )
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[f"{DOMAIN}.test_entry"]["data"]["params"]["rebate"] == 200


async def test_diagnostics(hass, entry, hass_client):
    from custom_components.netzentgelt_rechner.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await setup_entry(hass, entry)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["sources"] == [IMPORT_ID, EXPORT_ID, PRICE_ID]
    assert data["status"] == "nicht_berechnet"
    assert data["params"]["nt"] == 4.41
