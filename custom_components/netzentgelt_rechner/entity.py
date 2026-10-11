"""Base class of all entities: device, naming and update signal."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .hub import Hub


class NetzentgeltEntity(Entity):
    """Thin entity: reads from the hub and refreshes on the dispatcher signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: Hub, entry: ConfigEntry, key: str) -> None:
        self.hub = hub
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._on_update))

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()
