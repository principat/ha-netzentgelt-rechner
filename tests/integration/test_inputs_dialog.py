"""The 'Eingaben bearbeiten' dialog with a collapsed help block (AK-18)."""

from __future__ import annotations

import pytest
from helpers import setup_entry, unique_entity_id
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import ServiceValidationError

from custom_components.netzentgelt_rechner.const import NUMBER_PARAMS

pytestmark = pytest.mark.usefixtures("berlin")

GROUPS = {
    "netzentgelt": ["st", "nt", "ht", "rebate", "m3_base_delta"],
    "tarife": ["fixed", "levies", "vat", "markup", "dyn_base", "feedin"],
    "speicher": ["flex_kwh", "extra_kwh", "invest", "eta_rt", "c_rate", "wear"],
    "anschluss": ["grid_import_kw", "grid_export_kw"],
}


async def _open_inputs(hass: HomeAssistant, entry) -> dict:
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "inputs"}
    )


async def test_form_has_collapsed_help_first_and_all_groups(hass: HomeAssistant, entry):  # AK-18
    await setup_entry(hass, entry)
    form = await _open_inputs(hass, entry)
    assert form["type"] is FlowResultType.FORM and form["step_id"] == "inputs"
    schema = form["data_schema"].schema
    sections = {key.schema: value for key, value in schema.items()}
    assert list(sections) == ["hilfe", *GROUPS]  # help comes first
    assert sections["hilfe"].options == {"collapsed": True}
    assert all(sections[g].options == {"collapsed": False} for g in GROUPS)
    assert set(_fields(sections["hilfe"])) == {f"help_{g}" for g in GROUPS}
    covered = {key for g in GROUPS for key in _fields(sections[g])}
    assert covered == set(NUMBER_PARAMS)  # every number input is reachable in the dialog
    nt = next(k for k in sections["netzentgelt"].schema.schema if k.schema == "nt")
    assert nt.default() == 4.41  # the current value is the default


def _fields(sec) -> list[str]:
    return [key.schema for key in sec.schema.schema]


async def test_saving_changes_values_without_recalculation(hass: HomeAssistant, entry):  # AK-18
    await setup_entry(hass, entry)
    hub = entry.runtime_data
    form = await _open_inputs(hass, entry)
    values = {g: {k: NUMBER_PARAMS[k][5] for k in keys} for g, keys in GROUPS.items()}
    values["netzentgelt"]["nt"] = 5.5
    values["anschluss"]["grid_import_kw"] = 24.0
    values["hilfe"] = {"help_netzentgelt": "ignored display field"}
    done = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert done["type"] is FlowResultType.MENU  # back to the menu
    await hass.async_block_till_done()
    assert hub.params["nt"] == 5.5 and hub.params["grid_import_kw"] == 24.0
    assert hub.status == "nicht_berechnet" and hub.results is None
    fee = hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt"))
    assert fee.attributes["preise"]["nt"] == 5.5
    assert float(hass.states.get(unique_entity_id(hass, "number", "nt")).state) == 5.5
    assert not any("help" in key for key in hub.params)  # display fields are never stored


async def test_values_out_of_range_are_blocked_by_the_form(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    form = await _open_inputs(hass, entry)
    values = {g: {k: NUMBER_PARAMS[k][5] for k in keys} for g, keys in GROUPS.items()}
    values["netzentgelt"]["nt"] = 999
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert entry.runtime_data.params["nt"] == 4.41


async def test_hub_sets_all_or_nothing(hass: HomeAssistant, entry):  # AK-2
    await setup_entry(hass, entry)
    hub = entry.runtime_data
    with pytest.raises(ServiceValidationError):
        hub.async_set_params({"nt": 5.0, "ht": 9999})
    with pytest.raises(ServiceValidationError):
        hub.async_set_params({"nope": 1})
    assert hub.params["nt"] == 4.41  # nothing applied
