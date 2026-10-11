"""Tariff-window list in the options flow and its persistence (AK-13, AK-14, AK-17)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from helpers import ENTRY_ID, setup_entry, stored, unique_entity_id
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import entity_registry as er

from custom_components.netzentgelt_rechner.calc import TariffWindow, day_stages
from custom_components.netzentgelt_rechner.const import DOMAIN
from custom_components.netzentgelt_rechner.hub import Hub

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=BERLIN)
pytestmark = pytest.mark.usefixtures("berlin")


@pytest.fixture(autouse=True)
def _frozen(freezer) -> None:
    freezer.move_to(NOW)


def _form(stage="H", start="2026-01-01", end="2026-12-31", from_hour=17, to_hour=19):
    return {
        "stage": stage,
        "start_date": start,
        "end_date": end,
        "from_hour": from_hour,
        "to_hour": to_hour,
    }


async def _open(hass: HomeAssistant, entry, step: str) -> dict:
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )


async def test_menu_lists_current_windows(hass: HomeAssistant, entry):  # AK-13
    await setup_entry(hass, entry)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["menu_options"] == ["sources", "window_add", "window_edit", "window_delete"]
    shown = menu["description_placeholders"]["windows"]
    assert "NT 01.01.2026\u201331.12.2026, 23:00\u201305:00" in shown
    assert shown.count("- ") == 3


async def test_menu_without_windows_hides_edit_and_delete(hass: HomeAssistant, entry):
    await setup_entry(hass, entry)
    entry.runtime_data.async_set_windows([])
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["menu_options"] == ["sources", "window_add"]
    assert menu["description_placeholders"]["windows"] == "\u2013"


@pytest.mark.parametrize("step", ["window_edit", "window_delete"])
async def test_empty_list_sends_edit_and_delete_back_to_menu(hass, entry, step):
    await setup_entry(hass, entry)
    menu = await hass.config_entries.options.async_init(entry.entry_id)  # offered while not empty
    entry.runtime_data.async_set_windows([])
    again = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )
    assert again["type"] is FlowResultType.MENU


async def test_add_window_applies_immediately_without_recalculation(hass, entry):  # AK-13
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    hub.async_set_windows([])
    result = await _open(hass, entry, "window_add")
    assert result["type"] is FlowResultType.FORM
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], _form("H", "2026-10-01", "2026-10-31", 12, 14)
    )
    assert done["type"] is FlowResultType.MENU  # back to the list
    assert hub.windows == [TariffWindow("H", date(2026, 10, 1), date(2026, 10, 31), 12, 14)]
    fee = hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt"))
    assert fee.state == "16.07"  # 12:00 is now high tariff
    assert hub.status == "nicht_berechnet" and hub.results is None
    assert len(hass.states.async_entity_ids("sensor")) >= 2  # entry was not reloaded


async def test_add_window_over_midnight(hass, entry):  # AK-15
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    hub.async_set_windows([])
    result = await _open(hass, entry, "window_add")
    await hass.config_entries.options.async_configure(
        result["flow_id"], _form("N", "2026-01-01", "2026-12-31", 22, 6)
    )
    assert day_stages(hub.windows, date(2026, 5, 5)) == "N" * 6 + "S" * 16 + "N" * 2


@pytest.mark.parametrize(
    ("form", "field", "error"),
    [
        (_form(start="2026-03-01", end="2026-02-01"), "end_date", "window_date_order"),
        (_form(from_hour=5, to_hour=5), "to_hour", "window_hours_equal"),
    ],
)
async def test_invalid_window_is_rejected_at_the_field(hass, entry, form, field, error):  # AK-14
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    before = list(hub.windows)
    result = await _open(hass, entry, "window_add")
    bad = await hass.config_entries.options.async_configure(result["flow_id"], form)
    assert bad["type"] is FlowResultType.FORM
    assert bad["errors"] == {field: error}
    assert hub.windows == before  # nothing saved


@pytest.mark.parametrize("form", [_form(from_hour=3, to_hour=0), _form(from_hour=24, to_hour=5)])
async def test_hours_out_of_range_are_blocked_by_the_form(hass, entry, form):  # AK-14
    await setup_entry(hass, entry)
    before = list(entry.runtime_data.windows)
    result = await _open(hass, entry, "window_add")
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], form)
    assert entry.runtime_data.windows == before


async def test_overlapping_window_is_rejected_with_conflict(hass, entry):  # AK-14
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    result = await _open(hass, entry, "window_add")
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _form("N", "2026-06-01", "2026-06-30", 18, 20),  # clashes with HT 17-19
    )
    assert bad["errors"] == {"start_date": "window_overlap"}
    assert (
        "HT 01.01.2026\u201331.12.2026, 17:00\u201319:00"
        in (bad["description_placeholders"]["conflict"])
    )
    assert len(hub.windows) == 3


async def test_edit_window_prefills_and_saves_sorted(hass, entry):  # AK-13
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    pick = await _open(hass, entry, "window_edit")
    assert pick["type"] is FlowResultType.FORM
    index = next(i for i, w in enumerate(hub.windows) if w.from_hour == 17)
    form = await hass.config_entries.options.async_configure(
        pick["flow_id"], {"window": str(index)}
    )
    assert form["step_id"] == "window_edit_form"
    schema_defaults = {k.schema: k.default() for k in form["data_schema"].schema}
    assert schema_defaults["from_hour"] == 17 and schema_defaults["to_hour"] == 19
    assert schema_defaults["stage"] == "H"
    # keeping the same window is no self-overlap
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], _form("H", "2026-01-01", "2026-12-31", 16, 19)
    )
    assert done["type"] is FlowResultType.MENU
    assert len(hub.windows) == 3
    assert any(w.from_hour == 16 and w.to_hour == 19 for w in hub.windows)
    assert hub.windows == sorted(hub.windows, key=lambda w: (w.start, w.from_hour, w.stage))


async def test_edit_window_conflict_is_reported_for_the_edited_window(hass, entry):  # AK-14
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    pick = await _open(hass, entry, "window_edit")
    index = next(i for i, w in enumerate(hub.windows) if w.from_hour == 17)
    form = await hass.config_entries.options.async_configure(
        pick["flow_id"], {"window": str(index)}
    )
    bad = await hass.config_entries.options.async_configure(
        form["flow_id"],
        _form("H", "2026-01-01", "2026-12-31", 12, 19),  # reaches into HT 11-13
    )
    assert bad["errors"] == {"start_date": "window_overlap"}
    assert "11:00\u201313:00" in bad["description_placeholders"]["conflict"]


async def test_delete_windows(hass, entry):  # AK-13
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    result = await _open(hass, entry, "window_delete")
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], {"windows": ["0", "2"]}
    )
    assert done["type"] is FlowResultType.MENU
    assert len(hub.windows) == 1


async def test_windows_survive_restart(hass, entry, hass_storage):  # AK-13
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    new = [TariffWindow("N", date(2026, 3, 1), date(2026, 8, 31), 22, 6)]
    hub.async_set_windows(new)
    assert await hass.config_entries.async_unload(entry.entry_id)  # flushes the store
    await hass.async_block_till_done()
    saved = hass_storage[f"{DOMAIN}.{ENTRY_ID}"]["data"]["windows"]
    assert saved == [
        {"stufe": "N", "von": "2026-03-01", "bis": "2026-08-31", "stunde_von": 22, "stunde_bis": 6}
    ]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.windows == new


async def test_invalid_windows_cannot_be_set(hass, entry):  # AK-14
    from custom_components.netzentgelt_rechner.calc import WindowError

    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    before = list(hub.windows)
    with pytest.raises(WindowError):
        hub.async_set_windows([*before, before[0]])
    assert hub.windows == before


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "garbage",
        [{"stufe": "N"}],
        [
            {
                "stufe": "X",
                "von": "2026-01-01",
                "bis": "2026-12-31",
                "stunde_von": 1,
                "stunde_bis": 2,
            }
        ],
        [
            {
                "stufe": "H",
                "von": "2026-01-01",
                "bis": "2026-12-31",
                "stunde_von": 1,
                "stunde_bis": 5,
            },
            {
                "stufe": "N",
                "von": "2026-01-01",
                "bis": "2026-12-31",
                "stunde_von": 4,
                "stunde_bis": 6,
            },
        ],
    ],
)
async def test_unusable_stored_windows_fall_back_to_default(hass, entry, hass_storage, raw):
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(None, windows=raw)
    await setup_entry(hass, entry)
    assert day_stages(entry.runtime_data.windows, date(2026, 7, 7)) == "NNNNNSSSSSSHHSSSSHHSSSSN"


async def test_empty_stored_window_list_is_kept(hass, entry, hass_storage):  # AK-13
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(None, windows=[])
    await setup_entry(hass, entry)
    assert entry.runtime_data.windows == []
    fee = hass.states.get(unique_entity_id(hass, "sensor", "netzentgelt"))
    assert fee.attributes["stufe"] == "Standard"


async def test_legacy_quarter_windows_and_text_entities_are_migrated(  # AK-17
    hass, entry, hass_storage
):
    registry = er.async_get(hass)
    entry.add_to_hass(hass)
    for q in ("q1", "q4"):
        registry.async_get_or_create(
            "text", DOMAIN, f"{ENTRY_ID}_zeitfenster_{q}", config_entry=entry
        )
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = stored(
        None,
        windows={"Q1": "H" * 24, "Q2": "S" * 24, "Q3": "S" * 24, "Q4": "NNNNNSSSSSSHHSSSSHHSSSSN"},
    )
    await setup_entry(hass, entry)
    hub: Hub = entry.runtime_data
    assert day_stages(hub.windows, date(2026, 2, 2)) == "H" * 24
    assert day_stages(hub.windows, date(2026, 5, 5)) == "S" * 24
    assert day_stages(hub.windows, date(2026, 12, 24)) == "NNNNNSSSSSSHHSSSSHHSSSSN"
    assert not [
        e for e in er.async_entries_for_config_entry(registry, ENTRY_ID) if e.domain == "text"
    ]
