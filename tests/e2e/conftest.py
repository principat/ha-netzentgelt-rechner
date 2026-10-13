"""Fixtures shared by the end-to-end suites."""

from __future__ import annotations

import os

import pytest
from ha_client import HA


@pytest.fixture(scope="module")
def ha() -> HA:
    url, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not url or not token:
        pytest.skip("HA_URL / HA_TOKEN not set (use scripts/e2e.sh)")
    client = HA(url, token)
    client.wait_until(lambda: client.request("GET", "/api/config"), 180, "Home Assistant start")
    return client
