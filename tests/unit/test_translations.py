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
        assert "{" not in stripped and "}" not in stripped, path
        assert "**" not in text and "](" not in text, path


def test_flow_error_keys_are_translated():  # AK-11
    source = (DIR / "config_flow.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(entity_not_found)"', source))
    de = _flatten(_load("translations/de.json"))
    for key in keys:
        assert f"config.error.{key}" in de and f"options.error.{key}" in de
