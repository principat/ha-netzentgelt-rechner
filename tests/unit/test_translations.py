"""Translations stay in sync (AK-12)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DIR = Path(__file__).parents[2] / "custom_components" / "netzentgelt_rechner"
FILES = ["strings.json", "translations/de.json", "translations/en.json"]


def _load(name: str) -> dict:
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def _flatten(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def test_de_en_strings_have_identical_keys():  # AK-12
    de = _flatten(_load("translations/de.json"))
    assert de.keys() == _flatten(_load("translations/en.json")).keys()
    assert de.keys() == _flatten(_load("strings.json")).keys()


@pytest.mark.parametrize("name", FILES)
def test_no_unquoted_braces_or_markdown_in_plain_text(name):  # AK-12
    for path, text in _flatten(_load(name)).items():
        stripped = re.sub(r"'[{}]'", "", text)  # ICU: literal braces are quote-escaped
        stripped = re.sub(r"\{[a-z_]+\}", "", stripped)  # real placeholders, e.g. {windows}
        assert "{" not in stripped and "}" not in stripped, path
        if ".sections.hilfe.data_description." in path:  # the help blocks are Markdown by design
            continue
        assert "**" not in text and "](" not in text, path


def test_flow_error_keys_are_translated():  # AK-11, AK-14, AK-20
    source = (DIR / "config_flow.py").read_text(encoding="utf-8")
    keys = set(
        re.findall(
            r'"(entity_not_found|name_empty|name_exists'
            r'|window_(?:stage|date_order|hour_range|hours_equal|overlap))"',
            source,
        )
    )
    assert {"entity_not_found", "name_exists", "name_empty", "window_overlap"} <= keys
    for name in FILES:
        texts = _flatten(_load(name))
        for key in keys:
            section = "config" if key.startswith(("name_", "entity_")) else "options"
            assert f"{section}.error.{key}" in texts, (name, key)
        assert "options.error.entity_not_found" in texts


SECTIONS = ("netzentgelt", "tarife", "speicher", "anschluss")


@pytest.mark.parametrize("name", FILES)
def test_every_number_input_has_a_label_and_help(name):  # AK-18
    from custom_components.netzentgelt_rechner.const import NUMBER_PARAMS

    texts = _flatten(_load(name))
    prefix = "options.step.inputs.sections."
    labelled = {
        key: texts[f"{prefix}{sec}.data.{key}"]
        for sec in SECTIONS
        for key in NUMBER_PARAMS
        if f"{prefix}{sec}.data.{key}" in texts
    }
    assert labelled.keys() == NUMBER_PARAMS.keys()  # each field is in exactly one section
    help_text = "\n".join(
        v for k, v in texts.items() if k.startswith(prefix + "hilfe.data_description.")
    )
    for key, label in labelled.items():
        line = next((x for x in help_text.splitlines() if x.startswith(f"**{label}** \u2013 ")), "")
        assert len(line.split(": ")) >= 4, (name, key)  # why / enter / source all present
    for sec in ("hilfe", *SECTIONS):
        assert texts[f"{prefix}{sec}.name"], (name, sec)


@pytest.mark.parametrize("name", FILES)
def test_sources_and_window_fields_have_descriptions(name):  # AK-18
    texts = _flatten(_load(name))
    for step in ("config.step.user", "options.step.sources"):
        for field in ("import_entity", "export_entity", "price_entity"):
            assert texts[f"{step}.data_description.{field}"], (name, step, field)
    for step in ("window_add", "window_edit_form"):
        for field in ("stage", "start_date", "end_date", "from_hour", "to_hour"):
            assert texts[f"options.step.{step}.data_description.{field}"], (name, step, field)
