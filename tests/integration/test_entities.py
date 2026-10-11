from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from helpers import setup_entry, unique_entity_id
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.netzentgelt_rechner.const import NUMBER_PARAMS

BERLIN = ZoneInfo("Europe/Berlin")
pytestmark = pytest.mark.usefixtures("berlin")


async def test_setup_creates_all_entities_under_one_device(hass: HomeAssistant, entry):  # AK-1
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    by_platform: dict[str, int] = {}
    for item in entities:
        by_platform[item.domain] = by_platform.get(item.domain, 0) + 1
    assert by_platform == {
        "sensor": 2,
        "number": len(NUMBER_PARAMS),
        "text": 4,
        "button": 1,
    }
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [d.name for d in devices] == ["Netzentgelt-Rechner"]
    assert {e.device_id for e in entities} == {devices[0].id}
    assert entry.runtime_data.status == "nicht_berechnet"


async def test_unload_and_reload(hass: HomeAssistant, entry):  # AK-1
    await setup_entry(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt"))


async def test_number_range_is_validated(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    entity_id = unique_entity_id(hass, "number", "nt")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": 99}, blocking=True
        )
    assert float(hass.states.get(entity_id).state) == pytest.approx(4.41)


async def test_text_pattern_is_validated(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    entity_id = unique_entity_id(hass, "text", "zeitfenster_q1")
    for bad in ("N" * 23, "X" * 24, "n" * 24):
        with pytest.raises((HomeAssistantError, ValueError)):
            await hass.services.async_call(
                "text", "set_value", {"entity_id": entity_id, "value": bad}, blocking=True
            )
    assert hass.states.get(entity_id).state == "NNNNNSSSSSSHHSSSSHHSSSSN"


async def test_input_updates_fee_sensor_without_recalculation(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    fee = unique_entity_id(hass, "sensor", "netzentgelt")
    hub = entry.runtime_data
    before_status = hub.status
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": unique_entity_id(hass, "number", "nt"), "value": 5.5},
        blocking=True,
    )
    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": unique_entity_id(hass, "text", "zeitfenster_q4"), "value": "N" * 24},
        blocking=True,
    )
    await hass.async_block_till_done()
    attrs = hass.states.get(fee).attributes
    assert attrs["preise"]["nt"] == 5.5
    assert attrs["zeitplan"]["Q4"] == "N" * 24
    assert hub.status == before_status  # no automatic recalculation
    assert hub.results is None


@pytest.mark.parametrize(
    ("when", "state", "stage", "quarter"),
    [
        (datetime(2026, 10, 10, 2, 0, tzinfo=BERLIN), "4.41", "Niedertarif", "Q4"),
        (datetime(2026, 10, 10, 9, 59, tzinfo=BERLIN), "11.06", "Standard", "Q4"),
        (datetime(2026, 10, 10, 11, 15, tzinfo=BERLIN), "16.07", "Hochtarif", "Q4"),
        (datetime(2026, 3, 31, 23, 45, tzinfo=BERLIN), "4.41", "Niedertarif", "Q1"),
        (datetime(2026, 4, 1, 12, 0, tzinfo=BERLIN), "16.07", "Hochtarif", "Q2"),
    ],
)
async def test_fee_sensor_follows_time(  # AK-3
    hass: HomeAssistant, entry, freezer, when, state, stage, quarter
):
    freezer.move_to(when)
    await setup_entry(hass, entry)
    current = hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt"))
    assert float(current.state) == pytest.approx(float(state))
    assert current.attributes["stufe"] == stage
    assert current.attributes["quartal"] == quarter
    assert current.attributes["unit_of_measurement"] == "ct/kWh"


async def test_fee_sensor_series_and_quarter_hour_update(
    hass: HomeAssistant, entry, freezer
):  # AK-3
    freezer.move_to(datetime(2026, 10, 10, 10, 59, 30, tzinfo=BERLIN))
    await setup_entry(hass, entry)
    fee = unique_entity_id(hass, "sensor", "netzentgelt")
    attrs = hass.states.get(fee).attributes
    assert len(attrs["data"]) == 48
    assert attrs["data"][0]["start_time"] == "2026-10-10T00:00:00+02:00"
    assert attrs["data"][11]["stufe"] == "H"
    assert attrs["data"][11]["price_per_kwh"] == pytest.approx(0.1607)
    assert hass.states.get(fee).state == "11.06"

    freezer.move_to(datetime(2026, 10, 10, 11, 0, 2, tzinfo=BERLIN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(fee).state == "16.07"


@pytest.mark.parametrize(("day", "hours"), [((2026, 3, 29), 47), ((2026, 10, 25), 49)])
async def test_fee_series_on_dst_days(hass: HomeAssistant, entry, freezer, day, hours):  # AK-3
    freezer.move_to(datetime(*day, 12, 0, tzinfo=BERLIN))
    await setup_entry(hass, entry)
    attrs = hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt")).attributes
    assert len(attrs["data"]) == hours


async def test_large_attributes_are_not_recorded(hass: HomeAssistant, entry):
    await setup_entry(hass, entry)
    state_entity = hass.data["sensor"].get_entity(unique_entity_id(hass, "sensor", "netzentgelt"))
    assert {"data", "zeitplan"} <= state_entity._unrecorded_attributes
