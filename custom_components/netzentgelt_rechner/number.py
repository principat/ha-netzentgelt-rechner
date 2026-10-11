"""Number entities for all numeric inputs (AK-2)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NetzentgeltConfigEntry
from .const import NUMBER_PARAMS
from .entity import NetzentgeltEntity
from .hub import Hub

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetzentgeltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    async_add_entities([ParamNumber(hub, entry, key) for key in NUMBER_PARAMS])


class ParamNumber(NetzentgeltEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, hub: Hub, entry: NetzentgeltConfigEntry, key: str) -> None:
        super().__init__(hub, entry, key)
        self._key = key
        _, unit, low, high, step, _ = NUMBER_PARAMS[key]
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._decimals = len(f"{step:.6f}".rstrip("0").partition(".")[2])

    @property
    def native_value(self) -> float:
        return round(self.hub.params[self._key], self._decimals)

    async def async_set_native_value(self, value: float) -> None:
        self.hub.async_set_param(self._key, value)
