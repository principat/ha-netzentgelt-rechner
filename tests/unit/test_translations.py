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


TOPICS = ("netzentgelt", "tarife", "speicher", "anschluss")
SENSORS = {"tarife": ("price_entity",), "anschluss": ("import_entity", "export_entity")}


@pytest.mark.parametrize("name", FILES)
def test_every_input_has_a_label_and_help_in_its_topic(name):  # AK-18
    from custom_components.netzentgelt_rechner.const import NUMBER_PARAMS

    texts = _flatten(_load(name))
    found: dict[str, str] = {}
    for topic in TOPICS:
        step = f"options.step.{topic}"
        keys = [k.rsplit(".", 1)[1] for k in texts if k.startswith(f"{step}.data.")]
        help_text = texts[f"{step}.sections.hilfe.data_description.help"]
        for key in keys:
            assert key not in found, (name, key)  # each field lives in exactly one topic
            found[key] = topic
            label = texts[f"{step}.data.{key}"]
            line = next(
                (x for x in help_text.splitlines() if x.startswith(f"**{label}** \u2013 ")), ""
            )
            assert len(line.split(": ")) >= 4, (name, topic, key)  # why / enter / source
        for sensor in SENSORS.get(topic, ()):
            assert found.get(sensor) == topic, (name, sensor)
            assert texts[f"{step}.data_description.{sensor}"], (name, sensor)
        assert texts[f"{step}.title"] and texts[f"{step}.sections.hilfe.name"]
        assert texts[f"options.step.init.menu_options.{topic}"]
    assert set(NUMBER_PARAMS) | {s for v in SENSORS.values() for s in v} == set(found)


@pytest.mark.parametrize("name", FILES)
def test_sources_and_window_fields_have_descriptions(name):  # AK-18
    texts = _flatten(_load(name))
    for field in ("import_entity", "export_entity", "price_entity"):
        assert texts[f"config.step.user.data_description.{field}"], (name, field)
    for step in ("window_add", "window_edit_form"):
        for field in ("stage", "start_date", "end_date", "from_hour", "to_hour"):
            assert texts[f"options.step.{step}.data_description.{field}"], (name, step, field)


KEY_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")


@pytest.mark.parametrize("name", FILES)
def test_translation_keys_are_valid_for_hassfest(name):  # AK-12
    for path in _flatten(_load(name)):
        for part in path.split("."):
            assert KEY_RE.match(part), (name, path)
