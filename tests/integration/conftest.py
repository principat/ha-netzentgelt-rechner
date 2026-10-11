from __future__ import annotations

from collections.abc import Generator

import pytest
from helpers import ENTRY_ID, EXPORT_ID, IMPORT_ID, PRICE_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netzentgelt_rechner.const import (
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_PRICE,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(
    recorder_mock: object, enable_custom_integrations: None
) -> Generator[None]:
    yield


@pytest.fixture
async def berlin(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config = MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        data={CONF_IMPORT: IMPORT_ID, CONF_EXPORT: EXPORT_ID, CONF_PRICE: PRICE_ID},
    )
    config.add_to_hass(hass)
    return config
