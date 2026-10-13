"""Shared helpers of the end-to-end tests: synthetic statistics, setup, options flow."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from data_gen import synthetic_year
from ha_client import HA

from custom_components.netzentgelt_rechner.calc import TariffWindow
from custom_components.netzentgelt_rechner.const import DOMAIN, NUMBER_PARAMS

BERLIN = ZoneInfo("Europe/Berlin")
IMPORT_ID, EXPORT_ID, PRICE_ID = "sensor.e2e_import", "sensor.e2e_export", "sensor.e2e_price"
EXPECTED_WARNING = "Berechnung nicht möglich"


def _period() -> tuple[Any, Any]:
    today = datetime.now(BERLIN).date()
    end = today.replace(day=1)
    return end.replace(year=end.year - 1), end


def windows_of(ha: HA, ids: dict[str, str]) -> list[TariffWindow]:
    """The tariff windows as the integration reports them on the grid-fee sensor."""
    letters = {"Niedertarif": "N", "Hochtarif": "H"}
    return [
        TariffWindow(
            letters[w["stufe"]],
            date.fromisoformat(w["von"]),
            date.fromisoformat(w["bis"]),
            w["stunde_von"],
            w["stunde_bis"],
        )
        for w in ha.state(ids["netzentgelt"])["attributes"]["zeitplan"]
    ]


def add_window(ha: HA, stage: str, start: str, end: str, from_hour: int, to_hour: int) -> None:
    """Add a tariff window through the options flow REST API; clears overlapping defaults first."""
    (entries,) = ha.ws_commands([{"type": "config_entries/get", "domain": DOMAIN}])
    flow = ha.request(
        "POST", "/api/config/config_entries/options/flow", {"handler": entries[0]["entry_id"]}
    )
    base = f"/api/config/config_entries/options/flow/{flow['flow_id']}"
    delete = ha.request("POST", base, {"next_step_id": "window_delete"})
    field = delete["data_schema"][0]
    options = [o["value"] for o in field["selector"]["select"]["options"]]
    ha.request("POST", base, {"windows": options})  # back at the menu
    form = ha.request("POST", base, {"next_step_id": "window_add"})
    assert form["type"] == "form", form
    result = ha.request(
        "POST",
        base,
        {
            "stage": stage,
            "start_date": start,
            "end_date": end,
            "from_hour": from_hour,
            "to_hour": to_hour,
        },
    )
    assert result["type"] == "menu", result  # saved, back at the list
    ha.request("DELETE", base)  # close the dialog


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
    if existing := ha.entity_ids(DOMAIN):  # re-runs against the same instance
        return existing
    flow = ha.request("POST", "/api/config/config_entries/flow", {"handler": DOMAIN})
    done = ha.request(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {
            "name": "Netzentgelt-Rechner",
            "import_entity": IMPORT_ID,
            "export_entity": EXPORT_ID,
            "price_entity": PRICE_ID,
        },
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
