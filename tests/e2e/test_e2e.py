"""End-to-end scenarios against a real Home Assistant (docs/03 §4).

The tests run in file order and share one instance: E2E-4 first (too little data), then the
happy path, input changes, load and log hygiene.
"""

from __future__ import annotations

import os
import statistics
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from data_gen import synthetic_year
from ha_client import HA

from custom_components.netzentgelt_rechner.calc import Params, build_days, evaluate
from custom_components.netzentgelt_rechner.const import DOMAIN, NUMBER_PARAMS

pytestmark = pytest.mark.e2e

BERLIN = ZoneInfo("Europe/Berlin")
IMPORT_ID, EXPORT_ID, PRICE_ID = "sensor.e2e_import", "sensor.e2e_export", "sensor.e2e_price"
EXPECTED_WARNING = "Berechnung nicht möglich"


@pytest.fixture(scope="module")
def ha() -> HA:
    url, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not url or not token:
        pytest.skip("HA_URL / HA_TOKEN not set (use scripts/e2e.sh)")
    client = HA(url, token)
    client.wait_until(lambda: client.request("GET", "/api/config"), 180, "Home Assistant start")
    return client


# ------------------------------------------------------------------ helpers


def _period() -> tuple[Any, Any]:
    today = datetime.now(BERLIN).date()
    end = today.replace(day=1)
    return end.replace(year=end.year - 1), end


def _meter(series: dict[datetime, float]) -> list[dict[str, Any]]:
    total, rows = 0.0, []
    for ts in sorted(series):
        total += series[ts]
        rows.append({"start": ts.isoformat(), "state": total, "sum": total})
    return rows


def import_statistics(ha: HA, days: int | None) -> dict[str, dict[datetime, float]]:
    """Import synthetic hourly statistics for the last 12 full months (or the first ``days``)."""
    start, end = _period()
    count = (end - start).days if days is None else days
    imp, exp, spot = synthetic_year(start, count, BERLIN)
    commands: list[dict[str, Any]] = []
    kinds = (
        (IMPORT_ID, _meter(imp), True),
        (EXPORT_ID, _meter(exp), True),
        (PRICE_ID, [{"start": t.isoformat(), "mean": v} for t, v in sorted(spot.items())], False),
    )
    for statistic_id, rows, is_meter in kinds:
        metadata = {
            "has_mean": not is_meter,
            "mean_type": 0 if is_meter else 1,
            "has_sum": is_meter,
            "name": None,
            "source": "recorder",
            "statistic_id": statistic_id,
            "unit_of_measurement": "kWh" if is_meter else "EUR/kWh",
            "unit_class": "energy" if is_meter else None,
        }
        for i in range(0, len(rows), 2000):
            commands.append(
                {
                    "type": "recorder/import_statistics",
                    "metadata": metadata,
                    "stats": rows[i : i + 2000],
                }
            )
    ha.ws_commands(commands)
    last = max(spot)
    for statistic_id in (IMPORT_ID, EXPORT_ID, PRICE_ID):
        # the import is queued to the recorder thread: wait until the last hour is readable
        ha.wait_until(
            lambda sid=statistic_id: ha.ws_commands(
                [
                    {
                        "type": "recorder/statistics_during_period",
                        "start_time": last.isoformat(),
                        "statistic_ids": [sid],
                        "period": "hour",
                        "types": ["change" if sid != PRICE_ID else "mean"],
                    }
                ]
            )[0].get(sid),
            60,
            f"imported statistics {statistic_id}",
        )
    return {"imp": imp, "exp": exp, "spot": spot}


def setup_integration(ha: HA) -> dict[str, str]:
    flow = ha.request("POST", "/api/config/config_entries/flow", {"handler": DOMAIN})
    done = ha.request(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {"import_entity": IMPORT_ID, "export_entity": EXPORT_ID, "price_entity": PRICE_ID},
    )
    assert done["type"] == "create_entry", done
    return ha.wait_until(lambda: ha.entity_ids(DOMAIN) or None, 30, "entities")


def wait_for_result(ha: HA, entity: str, timeout: float = 180) -> dict[str, Any]:
    def check() -> dict[str, Any] | None:
        state = ha.state(entity)
        return state if state["state"] in ("fertig", "fehler") else None

    return ha.wait_until(check, timeout, "calculation result")  # type: ignore[no-any-return]


def press_and_wait(ha: HA, ids: dict[str, str]) -> dict[str, Any]:
    ha.call("button", "press", entity_id=ids["neu_berechnen"])
    time.sleep(1)
    return wait_for_result(ha, ids["wirtschaftlichkeit"])


def ui_params(ha: HA, ids: dict[str, str]) -> dict[str, float]:
    return {key: float(ha.state(ids[key])["state"]) for key in NUMBER_PARAMS}


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
    assert len(ours) == 2 + len(NUMBER_PARAMS) + 4 + 1
    assert len({e["device_id"] for e in ours}) == 1
    assert [d["name"] for d in devices if d["id"] == ours[0]["device_id"]] == [
        "Netzentgelt-Rechner"
    ]

    # AK-5: equals the pure calculation on the same data
    days = build_days(data["imp"], data["exp"], data["spot"], BERLIN)
    windows = {
        key.upper()[-2:]: ha.state(ids[key])["state"]
        for key in ids
        if key.startswith("zeitfenster_")
    }
    expected = evaluate(days, Params.from_ui(ui_params(ha, ids)), windows).to_dict()
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
    ha.call("text", "set_value", entity_id=ids["zeitfenster_q4"], value="N" * 24)
    fee = ha.state(ids["netzentgelt"])
    assert fee["attributes"]["preise"]["nt"] == 2.5
    assert fee["attributes"]["zeitplan"]["Q4"] == "N" * 24
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
