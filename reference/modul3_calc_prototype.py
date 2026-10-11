#!/usr/bin/env python3
"""Wirtschaftlichkeit: Modul 3, dynamischer Tarif, Kombination und Speichererweiterung.

Liest aus Home Assistant die stuendlichen Netzbezugs-/Einspeise-Statistiken und die
Boersenpreise (sensor.epex_preis_verlauf), rechnet die Szenarien durch und schreibt die
Ergebnisse in input_number-Helfer, die das Dashboard "Strompreis" anzeigt.

Aufruf in der HA-Konsole:   python3 modul3_calc.py            (rechnen + schreiben)
                             python3 modul3_calc.py --no-write (nur rechnen und anzeigen)
Alle Annahmen stehen in PARAMS und lassen sich per --set name=wert aendern, z. B.
                             python3 modul3_calc.py --set feedin=0.0786 --set markup=0.015

Modell (vereinfacht, bewusst nachvollziehbar):
 * Basis sind die letzten 12 vollen Monate des tatsaechlichen Netzbezugs und der Einspeisung
   (Ist-Zustand inkl. Ihres vorhandenen Speicherbetriebs).
 * "Passiv": gleiches Verbrauchsprofil, nur der Tarif aendert sich.
 * "Optimiert": ein zusaetzlich verschiebbarer Speicher wird je Tag mit Dynamischer
   Programmierung optimal gefahren (Preise des Tages bekannt = Day-Ahead). Laden aus
   Netz oder aus Ueberschuss, Entladen zuerst gegen Netzbezug.
 * Mehrwert der Erweiterung = Optimiert(vorhanden + Erweiterung) minus Optimiert(vorhanden).
"""
import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

PARAMS = dict(
    fixed=0.341,        # aktueller Arbeitspreis brutto EUR/kWh (alles inklusive)
    st=0.1106,          # Netzentgelt Standardstufe brutto (Annahme: = heutiges Netzentgelt)
    nt=0.0441,          # Niedertarif 23-5 Uhr brutto
    ht=0.1607,          # Hochtarif 11-13 und 17-19 Uhr brutto
    levies=0.088,       # Umlagen, Konzessionsabgabe, Stromsteuer brutto (Schaetzung)
    vat=1.19,
    markup=0.020,       # Aufschlag dynamischer Anbieter netto EUR/kWh auf den Boersenpreis
    dyn_base=40.0,      # Mehr-Grundgebuehr dynamischer Tarif brutto EUR/Jahr
    rebate=162.91,      # Modul 1 Pauschale brutto EUR/Jahr
    m3_base_delta=0.0,  # Zusatz-Grundpreis Modul 3 EUR/Jahr (unbekannt, Standard 0)
    feedin=0.0629,      # Einspeiseverguetung EUR/kWh (0 bei negativem Boersenpreis)
    eta_rt=0.88,        # Wirkungsgrad Laden+Entladen zusammen
    flex_kwh=13.5,      # nutzbarer, verschiebbarer vorhandener Speicher (Felicity ~15 kWh * 0,9)
    extra_kwh=14.4,     # nutzbarer Zusatzspeicher (16 kWh * 0,9)
    c_rate=0.5,         # max. Leistung = c_rate * Kapazitaet
    wear=0.0,           # Verschleisskosten EUR je kWh Durchsatz
    invest=1500.0,      # Kosten der Erweiterung EUR
    step=1.0,           # Rasterung der Speicherfuellung in kWh
)

ENT_IMP = "sensor.watt_wachter_zahlerstand_bezug"
ENT_EXP = "sensor.watt_wachter_zahlerstand_einspeisung"
ENT_PRICE = "sensor.epex_preis_verlauf"

# ---------------------------------------------------------------- Zeit (ohne tzdata)


def _last_sunday(year, month):
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def local_dt(utc_ms):
    u = datetime.fromtimestamp(utc_ms / 1000, timezone.utc).replace(tzinfo=None)
    start = datetime.combine(_last_sunday(u.year, 3), datetime.min.time()) + timedelta(hours=1)
    end = datetime.combine(_last_sunday(u.year, 10), datetime.min.time()) + timedelta(hours=1)
    return u + timedelta(hours=2 if start <= u < end else 1)


def band(h):
    if h >= 23 or h < 5:
        return "nt"
    if 11 <= h < 13 or 17 <= h < 19:
        return "ht"
    return "st"


# ---------------------------------------------------------------- Preise je Szenario


def make_prices(p):
    e_fixed = p["fixed"] - p["st"] - p["levies"]

    def m3(h, spot):
        return e_fixed + p[band(h)] + p["levies"]

    def dyn(h, spot):
        return (spot + p["markup"]) * p["vat"] + p["st"] + p["levies"]

    def kom(h, spot):
        return (spot + p["markup"]) * p["vat"] + p[band(h)] + p["levies"]

    return {"m3": m3, "dyn": dyn, "kom": kom}


# ---------------------------------------------------------------- Tages-DP


def dp_day(cbuy, fi, imp, exp, cap, p):
    """Minimale Zusatzkosten (<= 0 = Gewinn) fuer einen Tag mit Speicher 'cap' kWh."""
    q = p["step"]
    n = int(cap / q + 1e-9)
    if n <= 0:
        return 0.0
    eta = math.sqrt(p["eta_rt"])
    pmax = p["c_rate"] * cap
    kc = max(1, int(pmax * eta / q))      # max. Ladeschritte je Stunde (gespeicherte Energie)
    kd = max(1, int(pmax / (eta * q)))    # max. Entladeschritte je Stunde
    H = len(cbuy)
    # Stundenkosten je Schritt k (k>0 laden, k<0 entladen)
    costs = []
    for h in range(H):
        row = {}
        for k in range(1, kc + 1):
            bus = k * q / eta
            ab = min(exp[h], bus)
            row[k] = (bus - ab) * cbuy[h] + ab * fi[h] + p["wear"] * k * q
        for k in range(1, kd + 1):
            d = k * q * eta
            use = min(d, imp[h])
            row[-k] = -use * cbuy[h] - (d - use) * fi[h] + p["wear"] * k * q
        row[0] = 0.0
        costs.append(row)
    V = [0.0] * (n + 1)
    for h in range(H - 1, -1, -1):
        row = costs[h]
        nv = [0.0] * (n + 1)
        for e in range(n + 1):
            best = None
            for k in range(-min(kd, e), min(kc, n - e) + 1):
                v = row[k] + V[e + k]
                if best is None or v < best:
                    best = v
            nv[e] = best
        V = nv
    return V[0]


# ---------------------------------------------------------------- Daten


def build_days(imp_rows, exp_rows, price_rows):
    """-> dict datum -> Liste je Stunde (lokal) mit imp, exp, spot; nur vollstaendige Tage."""
    imp = {r["start"]: r.get("change") or 0.0 for r in imp_rows}
    exp = {r["start"]: r.get("change") or 0.0 for r in exp_rows}
    spot = {r["start"]: r.get("mean") for r in price_rows}
    days = defaultdict(list)
    for ts in sorted(spot):
        if spot[ts] is None:
            continue
        ld = local_dt(ts)
        days[ld.date()].append({"h": ld.hour, "imp": max(0.0, imp.get(ts, 0.0)),
                                "exp": max(0.0, exp.get(ts, 0.0)), "spot": spot[ts]})
    return {d: v for d, v in days.items() if len(v) in (23, 24, 25)}


def evaluate(days, p):
    prices = make_prices(p)
    res = defaultdict(float)
    n_days = len(days)
    for d, hrs in days.items():
        imp = [x["imp"] for x in hrs]
        exp = [x["exp"] for x in hrs]
        res["imp"] += sum(imp)
        res["exp"] += sum(exp)
        fi = [p["feedin"] if x["spot"] >= 0 else 0.0 for x in hrs]
        for s, f in prices.items():
            cb = [f(x["h"], x["spot"]) for x in hrs]
            res[s + "_pass"] += sum(i * (p["fixed"] - c) for i, c in zip(imp, cb))
            if sum(imp) > 0.5:
                g0 = -dp_day(cb, fi, imp, exp, p["flex_kwh"], p)
                g1 = -dp_day(cb, fi, imp, exp, p["flex_kwh"] + p["extra_kwh"], p)
                res[s + "_gain_flex"] += g0
                res[s + "_gain_ext"] += g1
        res["spot_sum"] += sum(x["spot"] for x in hrs)
        res["spot_n"] += len(hrs)
    scale = 365.0 / n_days
    out = {"days": n_days, "imp": res["imp"] * scale, "exp": res["exp"] * scale,
           "spot_avg": res["spot_sum"] / res["spot_n"]}
    base = {"m3": p["rebate"] - p["m3_base_delta"],
            "dyn": -p["dyn_base"],
            "kom": p["rebate"] - p["dyn_base"] - p["m3_base_delta"]}
    out["m1"] = p["rebate"]
    for s in prices:
        passive = res[s + "_pass"] * scale + base[s]
        out[s + "_pass"] = passive
        out[s + "_opt"] = passive + res[s + "_gain_flex"] * scale
        out[s + "_opt16"] = passive + res[s + "_gain_ext"] * scale
        out[s + "_mehr16"] = (res[s + "_gain_ext"] - res[s + "_gain_flex"]) * scale
    return out


# ---------------------------------------------------------------- HA-Zugriff


async def ha_call(ws, mid, payload):
    await ws.send(json.dumps(dict(payload, id=mid)))
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == mid:
            if not m.get("success", True):
                raise RuntimeError(m)
            return m.get("result")


async def main_async(args, p):
    import websockets
    url = args.ha.rstrip("/") + "/api/websocket"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": args.token}))
        if json.loads(await ws.recv())["type"] != "auth_ok":
            raise SystemExit("Auth fehlgeschlagen")
        today = date.today()
        first_this = today.replace(day=1)
        end = first_this
        start = date(end.year - 1, end.month, 1)
        st = datetime.combine(start, datetime.min.time()).isoformat() + "+00:00"
        en = datetime.combine(end, datetime.min.time()).isoformat() + "+00:00"
        mid = 1

        async def stats(ids, types):
            nonlocal mid
            mid += 1
            return await ha_call(ws, mid, {
                "type": "recorder/statistics_during_period", "start_time": st,
                "end_time": en, "statistic_ids": ids, "period": "hour", "types": types})

        r1 = await stats([ENT_IMP, ENT_EXP], ["change"])
        r2 = await stats([ENT_PRICE], ["mean"])
        days = build_days(r1[ENT_IMP], r1[ENT_EXP], r2[ENT_PRICE])
        if len(days) < 200:
            print(f"Achtung: nur {len(days)} vollstaendige Tage gefunden")
        out = evaluate(days, p)
        show(out, p, start, end)
        if args.no_write:
            return
        sets = {
            "m3_ersp_m1": out["m1"],
            "m3_ersp_m3p": out["m3_pass"], "m3_ersp_dynp": out["dyn_pass"],
            "m3_ersp_komp": out["kom_pass"],
            "m3_ersp_m3o": out["m3_opt"], "m3_ersp_dyno": out["dyn_opt"],
            "m3_ersp_komo": out["kom_opt"],
            "m3_ersp_m3o16": out["m3_opt16"], "m3_ersp_dyno16": out["dyn_opt16"],
            "m3_ersp_komo16": out["kom_opt16"],
            "m3_basis_bezug": out["imp"], "m3_basis_einsp": out["exp"],
            "m3_invest": p["invest"], "m3_spot_avg": out["spot_avg"] * 100,
        }
        for k, v in sets.items():
            mid += 1
            await ha_call(ws, mid, {"type": "call_service", "domain": "input_number",
                                    "service": "set_value",
                                    "service_data": {"entity_id": "input_number." + k,
                                                     "value": round(v, 2)}})
        info = (f"Stand {date.today():%d.%m.%Y}, Basis {start:%m/%Y}-{(end - timedelta(days=1)):%m/%Y}, "
                f"{out['days']} Tage, Speicher {p['flex_kwh']:.1f}+{p['extra_kwh']:.1f} kWh, "
                f"Einspeisung {p['feedin'] * 100:.2f} ct")
        mid += 1
        await ha_call(ws, mid, {"type": "call_service", "domain": "input_text",
                                "service": "set_value",
                                "service_data": {"entity_id": "input_text.m3_info",
                                                 "value": info[:255]}})
        print("In Home Assistant geschrieben.")


def show(o, p, start, end):
    print(f"\nBasis: {start} bis {end - timedelta(days=1)}, {o['days']} Tage, "
          f"Bezug {o['imp']:.0f} kWh/a, Einspeisung {o['exp']:.0f} kWh/a, "
          f"Boersenpreis Mittel {o['spot_avg'] * 100:.1f} ct netto")
    print(f"Modul 1 allein (Pauschale): {o['m1']:.0f} EUR/a\n")
    print(f"{'Szenario':<22}{'passiv':>10}{'+Speicher':>12}{'+16 kWh':>10}{'Mehrwert 16':>13}{'Amort. J':>10}")
    for s, name in (("m3", "Modul 3 (+Modul 1)"), ("dyn", "Dynamischer Tarif"), ("kom", "Kombination")):
        mv = o[s + "_mehr16"]
        am = p["invest"] / mv if mv > 1 else float("inf")
        print(f"{name:<22}{o[s + '_pass']:>10.0f}{o[s + '_opt']:>12.0f}{o[s + '_opt16']:>10.0f}"
              f"{mv:>13.0f}{am:>10.1f}")
    print("(alle Werte: Ersparnis in EUR pro Jahr gegenueber heutigem Festpreis)")


def main():
    import os
    in_app = bool(os.environ.get("SUPERVISOR_TOKEN"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--ha", default="ws://supervisor/core" if in_app else "ws://homeassistant.local:8123")
    ap.add_argument("--token", default=os.environ.get("SUPERVISOR_TOKEN"))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="name=wert")
    args = ap.parse_args()
    p = dict(PARAMS)
    for kv in args.set:
        k, v = kv.split("=", 1)
        if k not in p:
            raise SystemExit(f"unbekannter Parameter {k}: {sorted(p)}")
        p[k] = float(v)
    if not args.token:
        raise SystemExit("Kein Token: --token angeben")
    asyncio.run(main_async(args, p))


if __name__ == "__main__":
    main()
