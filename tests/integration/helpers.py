from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netzentgelt_rechner.const import DOMAIN

ENTRY_ID = "test_entry"
IMPORT_ID = "sensor.meter_import"
EXPORT_ID = "sensor.meter_export"
PRICE_ID = "sensor.spot_price"


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def unique_entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{ENTRY_ID}_{key}")
    assert entity_id, f"{platform}/{key} not registered"
    return entity_id


def stored(results: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """A hass_storage payload for the hub."""
    data: dict[str, Any] = {
        "params": {},
        "windows": {},
        "results": results,
        "status": "fertig" if results else "nicht_berechnet",
        "error": None,
    }
    data.update(extra)
    return {"version": 1, "minor_version": 1, "key": f"{DOMAIN}.{ENTRY_ID}", "data": data}
