"""Netzentgelt-Rechner: Netzentgelt-Szenarien aus Langzeitstatistiken."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import LEGACY_ENTITIES
from .hub import Hub

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BUTTON]

type NetzentgeltConfigEntry = ConfigEntry[Hub]


async def async_setup_entry(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    _remove_legacy_entities(hass, entry)
    hub = Hub(hass, entry)
    await hub.async_load()
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hub.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_flush()
    return unloaded


def _remove_legacy_entities(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> None:
    """Drop entities of older versions: quarterly window texts (AK-17), C-rate (AK-22)."""
    registry = er.async_get(hass)
    legacy = {(domain, f"{entry.entry_id}_{key}") for domain, key in LEGACY_ENTITIES}
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (item.domain, item.unique_id) in legacy:
            registry.async_remove(item.entity_id)
