"""Diagnostics: parameters, status and basis data (no consumption series)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import NetzentgeltConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NetzentgeltConfigEntry
) -> dict[str, Any]:
    hub = entry.runtime_data
    results = hub.results or {}
    return {
        "sources": list(hub.sources),
        "params": hub.params,
        "windows": hub.windows,
        "status": hub.status,
        "error": hub.error,
        "basis": results.get("basis"),
    }
