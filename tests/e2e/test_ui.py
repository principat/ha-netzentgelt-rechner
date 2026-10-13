"""Visual end-to-end tests: the real Home Assistant frontend in a real browser (docs/03 §4).

Drives the options dialogs of the integration with Playwright, asserts what the user sees (collapsed
help block, readable Markdown, no stray editor widgets) and saves screenshots to
``tests/e2e/screenshots``. Run with ``scripts/e2e-ui.sh``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from ha_client import HA
from helpers import DOMAIN, NUMBER_PARAMS, import_statistics, press_and_wait, setup_integration
from playwright.sync_api import Browser, Page, sync_playwright

pytestmark = [pytest.mark.e2e, pytest.mark.ui]

SHOTS = Path(__file__).parent / "screenshots"
TRANSLATIONS = Path(__file__).parents[2] / "custom_components" / DOMAIN / "translations"
# labels of Home Assistant itself (not ours)
HA_TEXT = {
    "de": {"configure": "Konfigurieren", "submit": "OK", "add": "Dienst hinzufügen"},
    "en": {"configure": "Configure", "submit": "Submit", "add": "Add service"},
}
LANGS = ("de", "en")


def tr(lang: str, path: str) -> str:
    node: Any = json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))
    for part in path.split("."):
        node = node[part]
    assert isinstance(node, str)
    return node


@pytest.fixture(scope="module")
def ui_ids(ha: HA) -> dict[str, str]:
    """A calculated instance with a full synthetic year (the screenshots show real numbers)."""
    import_statistics(ha, days=None)
    ids = setup_integration(ha)
    state = press_and_wait(ha, ids)
    assert state["state"] == "fertig", state["attributes"].get("fehler")
    return ids


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as pw:
        chromium = pw.chromium.launch()
        yield chromium
        chromium.close()


def open_page(browser: Browser, lang: str, path: str) -> Page:
    """A logged-in page: the long-lived token is injected as the frontend's session."""
    url, token = os.environ["HA_URL"], os.environ["HA_TOKEN"]
    session = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": url,
        "clientId": url + "/",
        "expires": 9999999999999,
        "refresh_token": "e2e",
    }
    context = browser.new_context(viewport={"width": 1280, "height": 1000}, locale=f"{lang}-DE")
    context.add_init_script(
        f"localStorage.setItem('hassTokens', JSON.stringify({json.dumps(session)}));"
        f"localStorage.setItem('selectedLanguage', JSON.stringify('{lang}'));"
    )
    page = context.new_page()
    page.goto(url + path)
    page.wait_for_load_state("networkidle")
    return page


def shot(page: Page, name: str, lang: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}-{lang}.png"))


def open_options_menu(page: Page, lang: str) -> None:
    page.get_by_label(HA_TEXT[lang]["configure"]).first.click()
    page.get_by_text(tr(lang, "options.step.init.menu_options.inputs")).wait_for()


@pytest.mark.parametrize("lang", LANGS)
def test_ui_1_options_menu_lists_tariff_windows(browser, ui_ids, lang):  # AK-13
    page = open_page(browser, lang, f"/config/integrations/integration/{DOMAIN}")
    open_options_menu(page, lang)
    for entry in ("inputs", "window_add", "window_edit", "window_delete", "sources"):
        assert page.get_by_text(tr(lang, f"options.step.init.menu_options.{entry}")).is_visible()
    assert page.get_by_text(re.compile(r"NT 01\.01\.\d{4}.+23:00.+05:00")).is_visible()
    shot(page, "01-options-menu", lang)
    page.context.close()


@pytest.mark.parametrize("lang", LANGS)
def test_ui_2_inputs_dialog_has_collapsed_readable_help(browser, ui_ids, lang):  # AK-18
    page = open_page(browser, lang, f"/config/integrations/integration/{DOMAIN}")
    open_options_menu(page, lang)
    page.get_by_text(tr(lang, "options.step.init.menu_options.inputs")).click()
    help_title = tr(lang, "options.step.inputs.sections.hilfe.name")
    page.get_by_text(help_title).wait_for()

    why = page.get_by_text(re.compile(r"(Wozu|Why):")).first
    assert not why.is_visible(), "the help block must start collapsed"
    group = tr(lang, "options.step.inputs.sections.netzentgelt.name")
    assert page.get_by_role("heading", name=group).first.is_visible()
    shot(page, "02-inputs-collapsed", lang)

    page.get_by_text(help_title).click()
    why.wait_for(state="visible")
    # readable Markdown (bold labels, headings) and no template editor widget or raw markup
    assert page.locator("ha-code-editor").count() == 0
    assert "{{" not in page.inner_text("body") and "**" not in page.inner_text("body")
    for key, (_, _, _, _, _, _) in NUMBER_PARAMS.items():
        label = next(
            tr(lang, f"options.step.inputs.sections.{sec}.data.{key}")
            for sec in ("netzentgelt", "tarife", "speicher", "anschluss")
            if _has(lang, sec, key)
        )
        assert page.locator("strong", has_text=label).count() >= 1, (lang, key)
    shot(page, "03-inputs-help-open", lang)
    page.context.close()


def _has(lang: str, sec: str, key: str) -> bool:
    try:
        tr(lang, f"options.step.inputs.sections.{sec}.data.{key}")
    except KeyError:
        return False
    return True


@pytest.mark.parametrize("lang", LANGS)
def test_ui_3_saving_changes_the_values_without_recalculation(  # AK-18, AK-2
    ha, browser, ui_ids, lang
):
    before = ha.state(ui_ids["wirtschaftlichkeit"])["attributes"]["berechnet_am"]
    page = open_page(browser, lang, f"/config/integrations/integration/{DOMAIN}")
    open_options_menu(page, lang)
    page.get_by_text(tr(lang, "options.step.init.menu_options.inputs")).click()
    label = tr(lang, "options.step.inputs.sections.netzentgelt.data.nt")
    field = page.locator("ha-selector-number", has_text=label).locator("input").first
    field.fill("5.5")
    page.mouse.move(640, 500)
    page.mouse.wheel(0, 4000)  # the end of the form: the grid connection group
    page.wait_for_timeout(500)
    shot(page, "04-inputs-bottom", lang)
    page.get_by_text(HA_TEXT[lang]["submit"], exact=True).click()
    page.get_by_text(tr(lang, "options.step.init.menu_options.inputs")).wait_for()  # back at menu
    assert float(ha.state(ui_ids["nt"])["state"]) == 5.5
    assert ha.state(ui_ids["wirtschaftlichkeit"])["attributes"]["berechnet_am"] == before
    ha.call("number", "set_value", entity_id=ui_ids["nt"], value=4.41)
    page.context.close()


@pytest.mark.parametrize("lang", LANGS)
def test_ui_4_overlapping_tariff_window_shows_a_readable_error(browser, ui_ids, lang):  # AK-14
    page = open_page(browser, lang, f"/config/integrations/integration/{DOMAIN}")
    open_options_menu(page, lang)
    page.get_by_text(tr(lang, "options.step.init.menu_options.window_add")).click()
    page.get_by_text(tr(lang, "options.step.window_add.data.to_hour")).wait_for()  # fully rendered
    shot(page, "05-window-add", lang)
    page.get_by_text(
        HA_TEXT[lang]["submit"], exact=True
    ).click()  # defaults: all day, all year -> clashes
    prefix = tr(lang, "options.error.window_overlap").split("{")[0]
    page.get_by_text(re.compile(re.escape(prefix))).wait_for()
    shot(page, "06-window-overlap-error", lang)
    page.context.close()


@pytest.mark.parametrize("lang", LANGS)
def test_ui_5_setup_dialog_asks_for_an_instance_name(browser, ui_ids, lang):  # AK-20
    page = open_page(browser, lang, f"/config/integrations/integration/{DOMAIN}")
    page.get_by_text(HA_TEXT[lang]["add"], exact=True).first.click()
    page.get_by_text(tr(lang, "config.step.user.data.name")).first.wait_for()
    values = page.locator("input").evaluate_all("els => els.map(e => e.value)")
    assert "Netzentgelt-Rechner 2" in values  # the next free name is proposed
    body = page.inner_text("body")  # AK-11: the sources are not prefilled with plant-specific ids
    assert "sensor.watt_wachter" not in body and "sensor.epex" not in body
    assert not re.search(r"Unbekannte Entit|Unknown entity", body)
    shot(page, "07-setup-dialog", lang)
    page.context.close()


def test_ui_6_device_page_shows_inputs_and_sensors(browser, ui_ids, ha):  # AK-1
    (devices,) = ha.ws_commands([{"type": "config/device_registry/list"}])
    device = next(d for d in devices if d["name"] == "Netzentgelt-Rechner")
    page = open_page(browser, "de", f"/config/devices/device/{device['id']}")
    page.get_by_text("Netzentgelt Modul 3").first.wait_for()
    shot(page, "08-device", "de")
    page.context.close()
