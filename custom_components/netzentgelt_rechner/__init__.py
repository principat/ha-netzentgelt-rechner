"""Netzentgelt-Rechner: Netzentgelt-Szenarien aus Langzeitstatistiken."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .hub import Hub

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BUTTON]

type NetzentgeltConfigEntry = ConfigEntry[Hub]


async def async_setup_entry(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    _remove_legacy_window_entities(hass, entry)
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


def _remove_legacy_window_entities(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> None:
    """Drop the text entities of the quarterly windows of v1.0.0 (AK-17)."""
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.domain == "text" and item.unique_id.startswith(f"{entry.entry_id}_zeitfenster_q"):
            registry.async_remove(item.entity_id)
