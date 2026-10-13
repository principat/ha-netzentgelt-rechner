from __future__ import annotations

try:
    import probatio as vol  # HA >= 2026.10
except ImportError:  # older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]
from helpers import EXPORT_ID, IMPORT_ID, PRICE_ID
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netzentgelt_rechner.const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DOMAIN,
)


def _states(hass: HomeAssistant) -> None:
    for entity_id in (IMPORT_ID, EXPORT_ID, PRICE_ID):
        hass.states.async_set(entity_id, "1")


async def test_user_flow_creates_entry(hass: HomeAssistant):  # AK-11
    _states(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Standort A",
            CONF_IMPORT: IMPORT_ID,
            CONF_EXPORT: EXPORT_ID,
            CONF_PRICE: PRICE_ID,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Standort A"  # AK-20
    assert result["data"] == {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: PRICE_ID}


async def test_unknown_entity_is_rejected(hass: HomeAssistant):  # AK-11
    _states(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Standort A",
            CONF_IMPORT: IMPORT_ID,
            CONF_EXPORT: "sensor.nope",
            CONF_PRICE: PRICE_ID,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_EXPORT: "entity_not_found"}


async def test_default_name_is_proposed_and_counts_up(hass: HomeAssistant):  # AK-20
    _states(hass)
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert _default_name(first) == "Netzentgelt-Rechner"
    MockConfigEntry(domain=DOMAIN, title="Netzentgelt-Rechner", data={}).add_to_hass(hass)
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert _default_name(second) == "Netzentgelt-Rechner 2"


def _default_name(result) -> str:
    return next(k.default() for k in result["data_schema"].schema if k.schema == CONF_NAME)


async def test_second_instance_needs_a_unique_name(hass: HomeAssistant):  # AK-20
    _states(hass)
    MockConfigEntry(domain=DOMAIN, title="Standort A", data={}).add_to_hass(hass)
    base = {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: PRICE_ID}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM  # no single-instance abort any more
    for name in ("Standort A", "  standort a ", "   "):
        again = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: name, **base}
        )
        assert again["type"] is FlowResultType.FORM
        assert again["errors"] == {CONF_NAME: "name_exists" if name.strip() else "name_empty"}
    done = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Standort B", **base}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["title"] == "Standort B"


async def test_topic_changes_sensor_and_reloads(hass: HomeAssistant, entry):  # AK-11, AK-18
    hass.states.async_set("sensor.other_price", "0.1")
    _states(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "tarife"}
    )
    assert form["type"] is FlowResultType.FORM
    values = {k.schema: k.default() for k in form["data_schema"].schema if k.schema != "hilfe"}
    assert values[CONF_PRICE] == PRICE_ID  # the current sensor is preselected
    bad = await hass.config_entries.options.async_configure(
        form["flow_id"], {**values, CONF_PRICE: "sensor.missing", "fixed": 39.4}
    )
    assert bad["errors"] == {CONF_PRICE: "entity_not_found"}
    assert entry.runtime_data.params["fixed"] == 34.1  # nothing saved on error
    done = await hass.config_entries.options.async_configure(
        bad["flow_id"], {**values, CONF_PRICE: "sensor.other_price", "fixed": 39.4}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY  # sensor changed -> entry reloads
    await hass.async_block_till_done()
    assert entry.runtime_data.sources == (IMPORT_ID, EXPORT_ID, "sensor.other_price")
    assert entry.runtime_data.params["fixed"] == 39.4  # survived the reload


async def test_sources_are_not_prefilled(hass: HomeAssistant):  # AK-11
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for key in result["data_schema"].schema:
        if key.schema in (CONF_IMPORT, CONF_EXPORT, CONF_PRICE):
            assert key.default is vol.UNDEFINED, key.schema  # no plant-specific defaults
