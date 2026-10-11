"""Config flow and options flow (docs/02 §8, AK-11)."""

from __future__ import annotations

from datetime import date
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
from homeassistant.helpers.selector import (
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from . import calc
from .const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DEFAULT_EXPORT,
    DEFAULT_IMPORT,
    DEFAULT_PRICE,
    DOMAIN,
)
from .hub import Hub

# WindowError.code -> (form field, error key); keys live in strings.json under options.error
_WINDOW_ERRORS = {
    "stage": ("stage", "window_stage"),
    "date_order": ("end_date", "window_date_order"),
    "hour_range": ("to_hour", "window_hour_range"),
    "hours_equal": ("to_hour", "window_hours_equal"),
    "overlap": ("start_date", "window_overlap"),
}

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


def describe_window(w: calc.TariffWindow) -> str:
    """Language-neutral one-line description: 'NT 01.01.2026-31.12.2026, 23:00-05:00'."""
    label = "NT" if w.stage == "N" else "HT"
    return (
        f"{label} {w.start:%d.%m.%Y}\u2013{w.end:%d.%m.%Y}, "
        f"{w.from_hour:02d}:00\u2013{w.to_hour:02d}:00"
    )


def _window_schema(defaults: dict[str, Any]) -> vol.Schema:
    def hours(low: int, high: int) -> NumberSelector:
        return NumberSelector(
            NumberSelectorConfig(min=low, max=high, step=1, mode=NumberSelectorMode.BOX)
        )

    year = dt_util.now().year
    return vol.Schema(
        {
            vol.Required("stage", default=defaults.get("stage", "H")): SelectSelector(
                SelectSelectorConfig(
                    options=["N", "H"],
                    mode=SelectSelectorMode.LIST,
                    translation_key="stage",
                )
            ),
            vol.Required("start_date", default=defaults.get("start_date", f"{year}-01-01")): (
                DateSelector()
            ),
            vol.Required("end_date", default=defaults.get("end_date", f"{year}-12-31")): (
                DateSelector()
            ),
            vol.Required("from_hour", default=defaults.get("from_hour", 0)): hours(0, 23),
            vol.Required("to_hour", default=defaults.get("to_hour", 24)): hours(1, 24),
        }
    )


class NetzentgeltOptionsFlow(OptionsFlowWithReload):
    """Source sensors (reloads the entry) and the list of tariff windows (AK-13, AK-14)."""

    def __init__(self) -> None:
        self._edit_index = 0

    @property
    def _hub(self) -> Hub | None:
        return getattr(self.config_entry, "runtime_data", None)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        hub = self._hub
        menu = ["sources"]
        shown = "\u2013"
        if hub is not None:
            menu.append("window_add")
            if hub.windows:
                menu += ["window_edit", "window_delete"]
                shown = "\n".join(f"- {describe_window(w)}" for w in hub.windows)
        return self.async_show_menu(
            step_id="init", menu_options=menu, description_placeholders={"windows": shown}
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id="sources", data_schema=_schema(current), errors=errors)

    # ---------------------------------------------------------------- tariff windows

    async def async_step_window_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._window_form("window_add", user_input, None)

    async def async_step_window_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        hub = self._hub
        if hub is None or not hub.windows:
            return await self.async_step_init()
        if user_input is not None:
            self._edit_index = int(user_input["window"])
            return await self.async_step_window_edit_form()
        return self.async_show_form(
            step_id="window_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("window"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=str(i), label=describe_window(w))
                                for i, w in enumerate(hub.windows)
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_window_edit_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._window_form("window_edit_form", user_input, self._edit_index)

    async def async_step_window_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        hub = self._hub
        if hub is None or not hub.windows:
            return await self.async_step_init()
        if user_input is not None:
            drop = {int(i) for i in user_input["windows"]}
            hub.async_set_windows([w for i, w in enumerate(hub.windows) if i not in drop])
            return await self.async_step_init()
        return self.async_show_form(
            step_id="window_delete",
            data_schema=vol.Schema(
                {
                    vol.Required("windows"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=str(i), label=describe_window(w))
                                for i, w in enumerate(hub.windows)
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _window_form(
        self, step_id: str, user_input: dict[str, Any] | None, index: int | None
    ) -> ConfigFlowResult:
        """Add (``index`` None) or edit one tariff window with server-side validation."""
        hub = self._hub
        if hub is None:
            return await self.async_step_init()
        errors: dict[str, str] = {}
        placeholders = {"conflict": ""}
        defaults: dict[str, Any] = dict(user_input or {})
        if user_input is None and index is not None:
            w = hub.windows[index]
            defaults = {
                "stage": w.stage,
                "start_date": w.start.isoformat(),
                "end_date": w.end.isoformat(),
                "from_hour": w.from_hour,
                "to_hour": w.to_hour,
            }
        if user_input is not None:
            window = calc.TariffWindow(
                user_input["stage"],
                date.fromisoformat(user_input["start_date"]),
                date.fromisoformat(user_input["end_date"]),
                int(user_input["from_hour"]),
                int(user_input["to_hour"]),
            )
            # the edited window goes last, so an error always refers to it
            others = [w for i, w in enumerate(hub.windows) if i != index]
            try:
                calc.validate_windows([*others, window])
            except calc.WindowError as err:
                field, key = _WINDOW_ERRORS[err.code]
                errors[field] = key
                if err.other is not None:
                    placeholders["conflict"] = describe_window(others[err.other])
            else:
                hub.async_set_windows(
                    sorted([*others, window], key=lambda w: (w.start, w.from_hour, w.stage))
                )
                return await self.async_step_init()
        return self.async_show_form(
            step_id=step_id,
            data_schema=_window_schema(defaults),
            errors=errors,
            description_placeholders=placeholders,
        )
