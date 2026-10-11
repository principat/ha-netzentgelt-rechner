"""Netzentgelt-Rechner: Netzentgelt-Szenarien aus Langzeitstatistiken."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .hub import Hub

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.TEXT, Platform.BUTTON]

type NetzentgeltConfigEntry = ConfigEntry[Hub]


async def async_setup_entry(hass: HomeAssistant, entry: NetzentgeltConfigEntry) -> bool:
    """Set up the integration from a config entry."""
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
