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
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
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
    DOMAIN,
    NUMBER_PARAMS,
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

# Number inputs of the "inputs" dialog by topic; the help block lists them in the same order (AK-18)
_INPUT_GROUPS = {
    "netzentgelt": ("st", "nt", "ht", "rebate", "m3_base_delta"),
    "tarife": ("fixed", "levies", "vat", "markup", "dyn_base", "feedin"),
    "speicher": ("flex_kwh", "extra_kwh", "invest", "eta_rt", "c_rate", "wear"),
    "anschluss": ("grid_import_kw", "grid_export_kw"),
}

_FIELDS = (CONF_IMPORT, CONF_EXPORT, CONF_PRICE)


DEFAULT_NAME = "Netzentgelt-Rechner"


def _schema(defaults: dict[str, Any], *, name: str | None = None) -> vol.Schema:
    """Source selectors; ``name`` adds the instance-name field (initial setup only)."""
    selector = EntitySelector(EntitySelectorConfig(domain="sensor"))
    fields: dict[Any, Any] = {}
    if name is not None:
        fields[vol.Required(CONF_NAME, default=name)] = str
    for key in _FIELDS:
        marker = vol.Required(key, default=defaults[key]) if key in defaults else vol.Required(key)
        fields[marker] = selector
    return vol.Schema(fields)


async def _validate(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return field errors; an entity is valid if it has a state or statistics metadata."""
    known = {item["statistic_id"] for item in await async_list_statistic_ids(hass)}
    errors: dict[str, str] = {}
    for key in _FIELDS:
        entity_id = user_input[key]
        if hass.states.get(entity_id) is None and entity_id not in known:
            errors[key] = "entity_not_found"
    return errors


class NetzentgeltConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow; several instances are allowed, each with a unique name (AK-20)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        taken = {e.title.strip().casefold() for e in self._async_current_entries()}
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_empty"
            elif name.casefold() in taken:
                errors[CONF_NAME] = "name_exists"
            errors.update(await _validate(self.hass, user_input))
            if not errors:
                sources = {k: v for k, v in user_input.items() if k != CONF_NAME}
                return self.async_create_entry(title=name, data=sources)
        proposal, count = DEFAULT_NAME, 1
        while proposal.casefold() in taken:
            count += 1
            proposal = f"{DEFAULT_NAME} {count}"
        name = user_input[CONF_NAME] if user_input else proposal
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}, name=name), errors=errors
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


def _inputs_schema(params: dict[str, float]) -> vol.Schema:
    """Number inputs by topic, preceded by a collapsed block that carries the help texts."""

    def number(key: str) -> NumberSelector:
        _, unit, low, high, step, _ = NUMBER_PARAMS[key]
        return NumberSelector(
            NumberSelectorConfig(
                min=low,
                max=high,
                step=step,
                unit_of_measurement=unit,
                mode=NumberSelectorMode.BOX,
            )
        )

    # display-only field: its translated data_description is the help Markdown
    help_block = section(vol.Schema({vol.Optional("help"): BooleanSelector()}), {"collapsed": True})
    fields: dict[Any, Any] = {vol.Optional("hilfe"): help_block}
    for group, keys in _INPUT_GROUPS.items():
        fields[vol.Required(group)] = section(
            vol.Schema({vol.Required(k, default=params[k]): number(k) for k in keys}),
            {"collapsed": False},
        )
    return vol.Schema(fields)


class NetzentgeltOptionsFlow(OptionsFlowWithReload):
    """Source sensors (reloads the entry) and the list of tariff windows (AK-13, AK-14)."""

    def __init__(self) -> None:
        self._edit_index = 0

    @property
    def _hub(self) -> Hub | None:
        return getattr(self.config_entry, "runtime_data", None)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        hub = self._hub
        menu: list[str] = []
        shown = "\u2013"
        if hub is not None:
            menu += ["inputs", "window_add"]
            if hub.windows:
                menu += ["window_edit", "window_delete"]
                shown = "\n".join(f"- {describe_window(w)}" for w in hub.windows)
        menu.append("sources")
        return self.async_show_menu(
            step_id="init", menu_options=menu, description_placeholders={"windows": shown}
        )

    async def async_step_inputs(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit all number inputs with a collapsed help block (AK-18); no recalculation."""
        hub = self._hub
        if hub is None:
            return await self.async_step_init()
        if user_input is not None:
            values = {
                key: float(value)
                for group in _INPUT_GROUPS
                for key, value in user_input[group].items()
            }  # the help block ("hilfe") is display-only and never stored
            hub.async_set_params(values)
            return await self.async_step_init()
        return self.async_show_form(step_id="inputs", data_schema=_inputs_schema(hub.params))

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
