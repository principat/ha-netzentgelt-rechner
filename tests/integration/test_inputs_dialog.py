"""Topic forms of the options menu (AK-18) and the migration from C-rate to kW (AK-22)."""

from __future__ import annotations

import pytest
from helpers import ENTRY_ID, EXPORT_ID, IMPORT_ID, setup_entry, stored, unique_entity_id
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netzentgelt_rechner.config_flow import TOPIC_SOURCES, TOPICS
from custom_components.netzentgelt_rechner.const import DOMAIN, NUMBER_PARAMS

pytestmark = pytest.mark.usefixtures("berlin")


async def _open(hass: HomeAssistant, entry, topic: str) -> dict:
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": topic}
    )


def _defaults(form: dict) -> dict:
    return {k.schema: k.default() for k in form["data_schema"].schema if k.schema != "hilfe"}


def test_topics_cover_every_number_input_once():  # AK-18
    keys = [k for keys in TOPICS.values() for k in keys]
    assert sorted(keys) == sorted(NUMBER_PARAMS)
    assert TOPIC_SOURCES == {
        "tarife": ("price_entity",),
        "anschluss": ("import_entity", "export_entity"),
    }


@pytest.mark.parametrize("topic", list(TOPICS))
async def test_topic_form_has_collapsed_help_first(hass: HomeAssistant, entry, topic):  # AK-18
    await setup_entry(hass, entry)
    form = await _open(hass, entry, topic)
    assert form["type"] is FlowResultType.FORM and form["step_id"] == topic
    keys = [k.schema for k in form["data_schema"].schema]
    assert keys == ["hilfe", *TOPIC_SOURCES.get(topic, ()), *TOPICS[topic]]
    hilfe = next(v for k, v in form["data_schema"].schema.items() if k.schema == "hilfe")
    assert hilfe.options == {"collapsed": True}
    assert [k.schema for k in hilfe.schema.schema] == ["help"]  # display-only carrier
    for key in TOPICS[topic]:
        assert _defaults(form)[key] == entry.runtime_data.params[key]  # current values


async def test_saving_numbers_keeps_the_dialog_open_without_recalculation(hass, entry):  # AK-18
    await setup_entry(hass, entry)
    hub = entry.runtime_data
    form = await _open(hass, entry, "netzentgelt")
    values = _defaults(form) | {"nt": 5.5, "hilfe": {"help": True}}
    done = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert done["type"] is FlowResultType.MENU  # back to the menu, no reload
    await hass.async_block_till_done()
    assert hub.params["nt"] == 5.5 and entry.runtime_data is hub
    assert hub.status == "nicht_berechnet" and hub.results is None
    assert (
        hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt")).attributes["preise"]["nt"]
        == 5.5
    )
    assert not any("help" in key for key in hub.params)


async def test_grid_connection_topic_holds_the_meters(hass, entry):  # AK-18
    for entity_id in (IMPORT_ID, EXPORT_ID):
        hass.states.async_set(entity_id, "1")
    await setup_entry(hass, entry)
    form = await _open(hass, entry, "anschluss")
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], _defaults(form) | {"grid_import_kw": 24.0}
    )
    assert done["type"] is FlowResultType.MENU  # same meters -> no reload
    assert entry.runtime_data.params["grid_import_kw"] == 24.0


async def test_values_out_of_range_are_blocked_by_the_form(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    form = await _open(hass, entry, "netzentgelt")
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"], _defaults(form) | {"nt": 999}
        )
    assert entry.runtime_data.params["nt"] == 4.41


async def test_hub_sets_all_or_nothing(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    hub = entry.runtime_data
    with pytest.raises(ServiceValidationError):
        hub.async_set_params({"nt": 5.0, "ht": 9999})
    with pytest.raises(ServiceValidationError):
        hub.async_set_params({"nope": 1})
    assert hub.params["nt"] == 4.41


async def test_c_rate_is_migrated_to_power(hass, entry: MockConfigEntry, hass_storage):  # AK-22
    registry = er.async_get(hass)
    registry.async_get_or_create("number", DOMAIN, f"{ENTRY_ID}_c_rate", config_entry=entry)
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(
        None, params={"c_rate": 0.5, "flex_kwh": 10.0, "extra_kwh": 20.0}
    )
    await setup_entry(hass, entry)
    hub = entry.runtime_data
    assert hub.params["power_kw"] == 5.0 and hub.params["extra_power_kw"] == 10.0
    assert "c_rate" not in hub.params
    assert registry.async_get_entity_id("number", DOMAIN, f"{ENTRY_ID}_c_rate") is None
    assert float(hass.states.get(unique_entity_id(hass, "number", "power_kw")).state) == 5.0


async def test_c_rate_with_defaults_and_existing_power(hass, entry, hass_storage):  # AK-22
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(None, params={"c_rate": 1.0, "flex_kwh": "x"})
    await setup_entry(hass, entry)
    assert entry.runtime_data.params["power_kw"] == 13.5  # invalid capacity -> default 13.5 kWh
    assert entry.runtime_data.params["extra_power_kw"] == 14.4


async def test_power_already_present_is_kept(hass, entry, hass_storage):  # AK-22
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(None, params={"c_rate": 1.0, "power_kw": 3.0})
    await setup_entry(hass, entry)
    assert entry.runtime_data.params["power_kw"] == 3.0
    assert entry.runtime_data.params["extra_power_kw"] == 7.2  # untouched default
