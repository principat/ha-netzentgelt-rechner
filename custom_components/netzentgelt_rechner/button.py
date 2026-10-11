"""Button "Neu berechnen" (AK-6)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NetzentgeltConfigEntry
from .entity import NetzentgeltEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetzentgeltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RecalculateButton(entry.runtime_data, entry, "neu_berechnen")])


class RecalculateButton(NetzentgeltEntity, ButtonEntity):
    async def async_press(self) -> None:
        self.hub.async_request_calculation()
