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

# Options-menu topics: number inputs and the source sensors that belong to them (AK-18).
# The help block of each topic lists its fields in the same order.
TOPICS = {
    "netzentgelt": ("st", "nt", "ht", "rebate", "m3_base_delta"),
    "tarife": ("fixed", "levies", "vat", "markup", "dyn_base", "feedin"),
    "speicher": ("flex_kwh", "extra_kwh", "power_kw", "extra_power_kw", "invest", "eta_rt", "wear"),
    "anschluss": ("grid_import_kw", "grid_export_kw"),
}
TOPIC_SOURCES = {"tarife": (CONF_PRICE,), "anschluss": (CONF_IMPORT, CONF_EXPORT)}

# stage <-> selector option (translation keys must be lowercase, hassfest)
_STAGE_OPTION = {"N": "nt", "H": "ht"}
_OPTION_STAGE = {v: k for k, v in _STAGE_OPTION.items()}

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
    for key in (k for k in _FIELDS if k in user_input):
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


def format_ct(value: float, language: str) -> str:
    """'4,41 ct/kWh' (German) or '4.41 ct/kWh'."""
    text = f"{value:.2f}"
    return (text.replace(".", ",") if language.startswith("de") else text) + " ct/kWh"


def _window_schema(defaults: dict[str, Any]) -> vol.Schema:
    def hours(low: int, high: int) -> NumberSelector:
        return NumberSelector(
            NumberSelectorConfig(min=low, max=high, step=1, mode=NumberSelectorMode.BOX)
        )

    year = dt_util.now().year
    return vol.Schema(
        {
            vol.Required("stage", default=defaults.get("stage", "ht")): SelectSelector(
                SelectSelectorConfig(
                    options=list(_OPTION_STAGE),
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


def _topic_schema(
    topic: str,
    params: dict[str, float] | None,
    sources: dict[str, Any],
    help_expanded: bool = False,
) -> vol.Schema:
    """A topic form: help block, the topic's sensors, then its number inputs."""

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

    # the switch "show help expanded next time" (AK-23) carries the help Markdown as its description
    help_block = section(
        vol.Schema({vol.Optional("help", default=help_expanded): BooleanSelector()}),
        {"collapsed": not help_expanded},
    )
    fields: dict[Any, Any] = {vol.Optional("hilfe"): help_block}
    sensor = EntitySelector(EntitySelectorConfig(domain="sensor"))
    for key in TOPIC_SOURCES.get(topic, ()):
        fields[vol.Required(key, default=sources[key])] = sensor
    if params is not None:  # without a loaded instance only the sensors can be changed
        for key in TOPICS[topic]:
            fields[vol.Required(key, default=params[key])] = number(key)
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
        if hub is None:  # instance not loaded: only the sensors can be fixed
            return self.async_show_menu(
                step_id="init",
                menu_options=list(TOPIC_SOURCES),
                description_placeholders={"windows": "\u2013", "standard": "\u2013"},
            )
        language = self.hass.config.language
        menu = [*TOPICS, "window_add"]
        shown = "\u2013"
        if hub.windows:
            menu += ["window_edit", "window_delete"]
            price = {"N": hub.params["nt"], "H": hub.params["ht"]}
            shown = "\n".join(
                f"- {describe_window(w)}: {format_ct(price[w.stage], language)}"
                for w in hub.windows
            )
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={
                "windows": shown,
                "standard": format_ct(hub.params["st"], language),
            },
        )

    async def async_step_netzentgelt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._topic("netzentgelt", user_input)

    async def async_step_tarife(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._topic("tarife", user_input)

    async def async_step_speicher(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._topic("speicher", user_input)

    async def async_step_anschluss(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._topic("anschluss", user_input)

    async def _topic(self, topic: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        """Edit one topic: number inputs (no recalculation) and its sensors (reload on change)."""
        hub = self._hub
        sources = {k: v for k, v in {**self.config_entry.data, **self.config_entry.options}.items()}
        errors: dict[str, str] = {}
        if user_input is not None:  # the help block ("hilfe") is display-only and never stored
            chosen = {k: user_input[k] for k in TOPIC_SOURCES.get(topic, ())}
            errors = await _validate(self.hass, chosen)
            if not errors:
                if hub is not None:
                    hub.async_set_params({k: float(user_input[k]) for k in TOPICS[topic]})
                    shown = user_input.get("hilfe", {}).get("help", hub.help_expanded)
                    hub.async_set_help_expanded(bool(shown))
                if any(sources.get(k) != v for k, v in chosen.items()):
                    # new sensors: store them as options; the entry reloads (data saved on unload)
                    return self.async_create_entry(
                        data={k: sources[k] for k in _FIELDS if k in sources} | chosen
                    )
                return await self.async_step_init()
            sources |= chosen
        params = None if hub is None else {**hub.params, **(user_input or {})}
        return self.async_show_form(
            step_id=topic,
            data_schema=_topic_schema(
                topic, params, sources, hub.help_expanded if hub is not None else False
            ),
            errors=errors,
        )

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
                "stage": _STAGE_OPTION[w.stage],
                "start_date": w.start.isoformat(),
                "end_date": w.end.isoformat(),
                "from_hour": w.from_hour,
                "to_hour": w.to_hour,
            }
        if user_input is not None:
            window = calc.TariffWindow(
                _OPTION_STAGE.get(user_input["stage"], user_input["stage"]),
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
