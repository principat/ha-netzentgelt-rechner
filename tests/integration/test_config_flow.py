from __future__ import annotations

from helpers import EXPORT_ID, IMPORT_ID, PRICE_ID
from homeassistant import config_entries
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
        {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: PRICE_ID},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PRICE] == PRICE_ID


async def test_unknown_entity_is_rejected(hass: HomeAssistant):  # AK-11
    _states(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: "sensor.nope", CONF_PRICE: PRICE_ID},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_EXPORT: "entity_not_found"}


async def test_single_instance(hass: HomeAssistant):  # AK-11
    MockConfigEntry(domain=DOMAIN, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_changes_sources(hass: HomeAssistant, entry):  # AK-11
    hass.states.async_set("sensor.other_price", "0.1")
    _states(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: "sensor.missing"},
    )
    assert bad["errors"] == {CONF_PRICE: "entity_not_found"}
    done = await hass.config_entries.options.async_configure(
        bad["flow_id"],
        {CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: "sensor.other_price"},
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.sources[2] == "sensor.other_price"
