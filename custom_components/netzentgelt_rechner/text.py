"""Text entities for the time windows Q1..Q4 (AK-2)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NetzentgeltConfigEntry
from .const import QUARTERS, WINDOW_PATTERN
from .entity import NetzentgeltEntity
from .hub import Hub

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetzentgeltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    async_add_entities([WindowText(hub, entry, q) for q in QUARTERS])


class WindowText(NetzentgeltEntity, TextEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 24
    _attr_native_max = 24
    _attr_pattern = WINDOW_PATTERN

    def __init__(self, hub: Hub, entry: NetzentgeltConfigEntry, quarter: str) -> None:
        super().__init__(hub, entry, f"zeitfenster_{quarter.lower()}")
        self._quarter = quarter

    @property
    def native_value(self) -> str:
        return self.hub.windows[self._quarter]

    async def async_set_value(self, value: str) -> None:
        self.hub.async_set_window(self._quarter, value)
