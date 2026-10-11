"""Config flow and options flow (docs/02 §8, AK-11)."""

from __future__ import annotations

from typing import Any

try:
    import probatio as vol  # HA >= 2026.10
except ImportError:  # older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]
from homeassistant.components.recorder.statistics import async_list_statistic_ids
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DEFAULT_EXPORT,
    DEFAULT_IMPORT,
    DEFAULT_PRICE,
    DOMAIN,
)

_FIELDS = (
    (CONF_IMPORT, DEFAULT_IMPORT),
    (CONF_EXPORT, DEFAULT_EXPORT),
    (CONF_PRICE, DEFAULT_PRICE),
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    selector = EntitySelector(EntitySelectorConfig(domain="sensor"))
    return vol.Schema(
        {
            vol.Required(key, default=defaults.get(key, default)): selector
            for key, default in _FIELDS
        }
    )


async def _validate(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return field errors; an entity is valid if it has a state or statistics metadata."""
    known = {item["statistic_id"] for item in await async_list_statistic_ids(hass)}
    errors: dict[str, str] = {}
    for key, _ in _FIELDS:
        entity_id = user_input[key]
        if hass.states.get(entity_id) is None and entity_id not in known:
            errors[key] = "entity_not_found"
    return errors


class NetzentgeltConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="Netzentgelt-Rechner", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NetzentgeltOptionsFlow:
        return NetzentgeltOptionsFlow()


class NetzentgeltOptionsFlow(OptionsFlowWithReload):
    """Change the source entities; the entry reloads afterwards."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id="init", data_schema=_schema(current), errors=errors)
