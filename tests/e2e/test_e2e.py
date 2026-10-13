"""End-to-end scenarios against a real Home Assistant (docs/03 §4).

The tests run in file order and share one instance: E2E-4 first (too little data), then the
happy path, input changes, load and log hygiene.
"""

from __future__ import annotations

import statistics
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from ha_client import HA
from helpers import (
    BERLIN,
    DOMAIN,
    EXPECTED_WARNING,
    NUMBER_PARAMS,
    add_window,
    import_statistics,
    press_and_wait,
    setup_integration,
    ui_params,
    wait_for_result,
    windows_of,
)

from custom_components.netzentgelt_rechner.calc import Params, build_days, evaluate

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def ids(ha: HA) -> dict[str, str]:
    import_statistics(ha, days=5)  # enough for the flow validation, too little to calculate
    return setup_integration(ha)


# ------------------------------------------------------------------ scenarios


def test_e2e_4_errors_keep_ha_usable(ha: HA, ids: dict[str, str]):  # AK-8
    state = press_and_wait(ha, ids)
    assert state["state"] == "fehler"
    assert "nötig sind 200" in state["attributes"]["fehler"]
    # HA stays operable: API answers and the fee sensor still works
    assert ha.request("GET", "/api/config")["state"] == "RUNNING"
    assert float(ha.state(ids["netzentgelt"])["state"]) > 0


def test_e2e_1_happy_path_and_restart(ha: HA, ids: dict[str, str]):  # AK-1, AK-5, AK-10
    data = import_statistics(ha, days=None)
    state = press_and_wait(ha, ids)
    assert state["state"] == "fertig", state["attributes"].get("fehler")

    # AK-1: all entities exist under one device
    registry, devices = ha.ws_commands(
        [{"type": "config/entity_registry/list"}, {"type": "config/device_registry/list"}]
    )
    ours = [e for e in registry if e["platform"] == DOMAIN]
    assert len(ours) == 2 + len(NUMBER_PARAMS) + 1
    assert len({e["device_id"] for e in ours}) == 1
    assert [d["name"] for d in devices if d["id"] == ours[0]["device_id"]] == [
        "Netzentgelt-Rechner"
    ]

    # AK-5: equals the pure calculation on the same data
    days = build_days(data["imp"], data["exp"], data["spot"], BERLIN)
    windows = windows_of(ha, ids)
    expected = evaluate(
        days,
        Params.from_ui(ui_params(ha, ids)),
        windows,
        ref_year=datetime.now(BERLIN).year,
    ).to_dict()
    attrs = state["attributes"]
    assert attrs["basis"]["tage"] == expected["basis"]["tage"]
    for scenario, values in expected["szenarien"].items():
        for key, value in values.items():
            actual = attrs["szenarien"][scenario][key]
            if value is None:
                assert actual is None, (scenario, key)
            else:
                assert actual == pytest.approx(value, abs=0.01), (scenario, key)

    # AK-10: results survive a restart
    before = attrs
    ha.call("homeassistant", "restart")
    time.sleep(3)
    ha.wait_until(lambda: ha.request("GET", "/api/config")["state"] == "RUNNING", 180, "restart")
    after = ha.wait_until(lambda: ha.state(ids["wirtschaftlichkeit"]), 60, "state after restart")
    assert after["state"] == "fertig"
    for key in ("berechnet_am", "basis", "szenarien", "annahmen"):
        assert after["attributes"][key] == before[key]


def test_e2e_2_change_input(ha: HA, ids: dict[str, str]):  # AK-2
    before = ha.state(ids["wirtschaftlichkeit"])
    ha.call("number", "set_value", entity_id=ids["rebate"], value=300)
    ha.call("number", "set_value", entity_id=ids["nt"], value=2.5)
    add_window(ha, "nt", "2026-01-01", "2026-12-31", 0, 24)  # AK-13, via the options dialog
    fee = ha.state(ids["netzentgelt"])
    assert fee["attributes"]["preise"]["nt"] == 2.5
    assert any(
        w["stufe"] == "Niedertarif" and (w["stunde_von"], w["stunde_bis"]) == (0, 24)
        for w in fee["attributes"]["zeitplan"]
    )
    unchanged = ha.state(ids["wirtschaftlichkeit"])
    assert unchanged["attributes"]["berechnet_am"] == before["attributes"]["berechnet_am"]
    with pytest.raises(urllib.error.HTTPError):
        ha.call("number", "set_value", entity_id=ids["nt"], value=999)

    after = press_and_wait(ha, ids)
    assert after["state"] == "fertig"
    assert after["attributes"]["szenarien"]["modul1"]["passiv"] == 300
    assert after["attributes"]["annahmen"]["nt"] == 2.5


def test_e2e_3_load_does_not_block(ha: HA, ids: dict[str, str]):  # AK-7
    ha.call("button", "press", entity_id=ids["neu_berechnen"])
    latencies: list[float] = []
    stop = threading.Event()

    def probe(_: int) -> None:
        while not stop.is_set():
            t0 = time.monotonic()
            ha.state(ids["netzentgelt"])
            latencies.append(time.monotonic() - t0)
            time.sleep(0.02)

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(probe, i) for i in range(50)]
        time.sleep(1)
        wait_for_result(ha, ids["wirtschaftlichkeit"])
        stop.set()
        for f in futures:
            f.result()
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    assert statistics.median(latencies) < 0.25
    assert p99 < 0.25, f"p99={p99:.3f}s over {len(latencies)} requests"


def test_e2e_5_log_hygiene(ha: HA):
    log = ha.request("GET", "/api/error_log", timeout=60)
    assert "Detected blocking call" not in log
    assert "is taking over" not in log
    bad = [
        line
        for line in log.splitlines()
        if f"[custom_components.{DOMAIN}"
        in line  # our own logger; HA's custom-integration notice is expected
        and (" WARNING " in line or " ERROR " in line)
        and EXPECTED_WARNING not in line
    ]
    assert not bad, bad
