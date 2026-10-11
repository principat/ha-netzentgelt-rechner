"""Sensors: grid fee (module 3) and profitability."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from . import NetzentgeltConfigEntry
from .const import STATUSES
from .entity import NetzentgeltEntity
from .hub import Hub

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NetzentgeltConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    async_add_entities(
        [
            NetzentgeltSensor(hub, entry, "netzentgelt"),
            WirtschaftlichkeitSensor(hub, entry, "wirtschaftlichkeit"),
        ]
    )


class NetzentgeltSensor(NetzentgeltEntity, SensorEntity):
    """Current grid fee in ct/kWh; attributes carry the hourly series (AK-3)."""

    _attr_native_unit_of_measurement = "ct/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"data", "zeitplan"})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._on_tick, minute=(0, 15, 30, 45), second=2)
        )

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self.hub.current_slot().price_per_kwh * 100.0, 4)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.hub.fee_attributes()


class WirtschaftlichkeitSensor(NetzentgeltEntity, SensorEntity):
    """Status of the calculation; results are attributes (docs/02 §4.2)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(STATUSES)  # noqa: RUF012

    def __init__(self, hub: Hub, entry: NetzentgeltConfigEntry, key: str) -> None:
        super().__init__(hub, entry, key)

    @property
    def native_value(self) -> str:
        return self.hub.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        results = self.hub.results or {}
        return {
            "berechnet_am": results.get("berechnet_am"),
            "dauer_s": results.get("dauer_s"),
            "basis": results.get("basis"),
            "szenarien": results.get("szenarien"),
            "annahmen": results.get("annahmen"),
            "fehler": self.hub.error,
        }
