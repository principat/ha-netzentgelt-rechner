"""Several instances side by side (AK-20, AK-21)."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from helpers import EXPORT_ID, IMPORT_ID, PRICE_ID, setup_entry
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netzentgelt_rechner.calc import TariffWindow
from custom_components.netzentgelt_rechner.const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DOMAIN,
    NUMBER_PARAMS,
)
from custom_components.netzentgelt_rechner.hub import Hub

pytestmark = pytest.mark.usefixtures("berlin")


@pytest.fixture
def entry_b(hass: HomeAssistant) -> MockConfigEntry:
    config = MockConfigEntry(
        domain=DOMAIN,
        entry_id="second_entry",
        title="Standort B",
        data={CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: PRICE_ID},
    )
    config.add_to_hass(hass)
    return config


def entity(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert found, f"{entry.title}: {platform}/{key} not registered"
    return found


async def _setup_both(hass: HomeAssistant, entry, entry_b) -> tuple[Hub, Hub]:
    await setup_entry(hass, entry)  # sets up every entry of the domain
    assert entry.state is entry_b.state is ConfigEntryState.LOADED
    return entry.runtime_data, entry_b.runtime_data


async def test_instances_have_own_devices_and_entities(hass, entry, entry_b):  # AK-20
    await _setup_both(hass, entry, entry_b)
    registry = er.async_get(hass)
    for config, name in ((entry, "Netzentgelt-Rechner"), (entry_b, "Standort B")):
        items = er.async_entries_for_config_entry(registry, config.entry_id)
        assert len(items) == 2 + len(NUMBER_PARAMS) + 1
        devices = dr.async_entries_for_config_entry(dr.async_get(hass), config.entry_id)
        assert [d.name for d in devices] == [name]
        assert {e.device_id for e in items} == {devices[0].id}
    ids_a = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    ids_b = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry_b.entry_id)}
    assert not ids_a & ids_b
    assert all("standort_b" in i for i in ids_b)  # the instance name is part of the entity id


async def test_instances_are_independent(hass, entry, entry_b):  # AK-20
    hub_a, hub_b = await _setup_both(hass, entry, entry_b)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity(hass, entry, "number", "nt"), "value": 5.5},
        blocking=True,
    )
    hub_a.async_set_windows([TariffWindow("H", date(2026, 1, 1), date(2026, 12, 31), 0, 24)])
    await hass.async_block_till_done()
    assert hub_a.params["nt"] == 5.5 and hub_b.params["nt"] == 4.41
    assert len(hub_a.windows) == 1 and len(hub_b.windows) == 3
    state_b = hass.states.get(entity(hass, entry_b, "number", "nt"))
    assert float(state_b.state) == pytest.approx(4.41)

    # removing one instance leaves the other untouched and working
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity(hass, entry_b, "sensor", "netzentgelt")) is not None
    hub_b.async_set_windows([])
    await hass.async_block_till_done()
    assert hass.states.get(entity(hass, entry_b, "sensor", "netzentgelt")).attributes["stufe"] == (
        "Standard"
    )


async def test_runs_of_two_instances_never_overlap(hass, entry, entry_b):  # AK-21
    hub_a, hub_b = await _setup_both(hass, entry, entry_b)
    running = peak = 0
    runs: list[str] = []
    gate = asyncio.Event()

    def slow(name: str):
        async def run(_started: float) -> dict:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            runs.append(name)
            await gate.wait()
            running -= 1
            return {"basis": {}, "szenarien": {}}

        return run

    hub_a._run = slow("a")  # type: ignore[method-assign]
    hub_b._run = slow("b")  # type: ignore[method-assign]
    task_a = hass.async_create_task(hub_a.async_calculate())
    task_b = hass.async_create_task(hub_b.async_calculate())
    hass.async_create_task(hub_b.async_calculate())  # a second trigger for b is ignored (AK-6)
    await asyncio.sleep(0.05)
    assert hub_a.status == "rechnet" and hub_b.status == "rechnet"  # b waits its turn
    assert runs == ["a"] and peak == 1
    gate.set()
    await asyncio.gather(task_a, task_b)
    await hass.async_block_till_done()
    assert runs == ["a", "b"] and peak == 1  # b rechnet genau einmal, danach
    assert hub_a.status == "fertig" and hub_b.status == "fertig"


async def test_a_failing_run_does_not_block_the_next_instance(hass, entry, entry_b):  # AK-21
    hub_a, hub_b = await _setup_both(hass, entry, entry_b)

    async def boom(_started: float) -> dict:
        raise RuntimeError("boom")

    async def fine(_started: float) -> dict:
        return {"basis": {}, "szenarien": {}}

    hub_a._run = boom  # type: ignore[method-assign]
    hub_b._run = fine  # type: ignore[method-assign]
    await asyncio.gather(hub_a.async_calculate(), hub_b.async_calculate())
    assert hub_a.status == "fehler" and hub_b.status == "fertig"
