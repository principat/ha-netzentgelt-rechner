# 02 Technische Spezifikation

Bezug: `01-fachliche-spezifikation.md` (AK-n). Zielplattform: Home Assistant Core 2026.10.x
(Python 3.14), Mindestversion 2026.2.0, Referenzumgebung des Autors: HAOS auf Raspberry Pi 5 (aarch64) mit MariaDB-Recorder. Die Integration ist
**datenbankunabhängig** (Zugriff nur über die Recorder-API; getestet mit SQLite) und verlangt kein bestimmtes
Recorder-Backend.

## 1 Architektur

```
                       ┌────────────────────────── Home Assistant ──────────────────────────┐
 Dashboard ─ UI ──────▶│ number/text/button Entitäten ─▶ Hub (runtime_data) ◀─ Zeitplaner     │
                       │      ▲ dispatcher                 │  │   │                          │
                       │      │                            │  │   └─ Store (.storage)        │
 sensor.netzentgelt ◀──┼──────┘   calc.fees (rein)  ◀──────┘  │                              │
 sensor.wirtschaft. ◀──┼───────── Ergebnis/Status             ▼ Executor-Thread              │
                       │                               Recorder.statistics_during_period     │
                       │                               calc.engine (rein, DP)                 │
                       └──────────────────────────────────────────────────────────────────────┘
```

- `Hub` (ein Objekt je Config-Entry, `entry.runtime_data`) hält Parameter, Zeitfenster, Ergebnisse,
  Status; ist die einzige Schnittstelle der Entitäten zum Zustand.
- Entitäten sind dünn: lesen aus dem Hub, schreiben über Hub-Methoden, aktualisieren sich über
  einen Dispatcher-Signal `netzentgelt_rechner_update`.
- `calc/` ist reines Python ohne HA-Abhängigkeit.

## 2 Repository-Layout

```
custom_components/netzentgelt_rechner/
  __init__.py        setup/unload, Plattformen, Hub anlegen, Zeitplaner
  hub.py             Hub: Parameter, Store, Single-Flight-Berechnung, Zeitplan, Dispatcher
  calc/
    __init__.py
    fees.py          Stufen, Quartal, Preise, Verlaufs-Slots (pur)
    engine.py        build_days, evaluate, dp_day (pur)
    models.py        dataclasses/TypedDicts: Params, Day, Result
  data.py            Recorder-Zugriff (Statistiken laden, _ts-Normalisierung, Zeitraum)
  entity.py          Basisklasse der Entitäten (Gerät, Dispatcher)
  diagnostics.py     Diagnostics-Platform
  config_flow.py     ConfigFlow + OptionsFlow (Quellsensoren, Tarifzeiten-Liste)
  sensor.py          NetzentgeltSensor, WirtschaftlichkeitSensor
  number.py  button.py
  const.py  manifest.json  strings/translations (de.json, en.json)  icons.json
tests/unit/ tests/integration/ tests/e2e/ fixtures/
docs/  scripts/  .github/workflows/  hacs.json  pyproject.toml  CHANGELOG.md
examples/{de,en}/dashboard.yaml
```

## 3 Datenmodell

### 3.1 Parameter
`const.NUMBER_PARAMS` (siehe Seed `custom_components/netzentgelt_rechner/const.py`, Name, Einheit,
Min/Max/Schritt/Standard). Intern wird in `calc.models.Params` auf SI-nahe Einheiten umgerechnet:
€/kWh, Anteil statt %, `vat` als Faktor `1 + p/100`, `eta_rt` als Anteil.

### 3.2 Tarifzeiten
`calc.fees.TariffWindow` (frozen dataclass): `stage` (`"N"`|`"H"`), `start`/`end` (`date`, beide inklusive),
`from_hour` 0–23, `to_hour` 1–24 (exklusiv; `to_hour < from_hour` = über Mitternacht, `==` verboten).
`windows: list[TariffWindow]` im Hub. `validate_windows(windows)` wirft `WindowError(code, index, other)`
mit `code` ∈ `stage | date_order | hour_range | hours_equal | overlap`.
- `stage(windows, day, hour) -> 'N'|'S'|'H'` (Standard `S`); `day_stages(windows, day) -> list[str]` (24 Zeichen,
  für Schleifen). `project_day(day, year)`: gleiche Tag/Monat im `year`, 29.02. → 28.02.
- `windows_from_quarters(quarters: Mapping[str,str], year)`: Umwandlung der alten 24-Zeichen-Fenster je Quartal
  (zusammenhängende N-/H-Läufe, Lauf über Mitternacht zusammengeführt) – für die Übernahme aus v1.0.0 und Tests.
- `default_windows(year)`: NT 23–5, HT 11–13, HT 17–19, jeweils 01.01.–31.12. des Jahres.

### 3.3 Erweiterbarkeit Quartalspreise (F-2)
`fees.price(stage, quarter, params)` ist die **einzige** Stelle, die einen Stufenpreis ermittelt;
heute ignoriert sie `quarter`. Quartalspreise später = neue Number-Entitäten `nt_q1…` ohne
Änderung der Aufrufer.

### 3.4 Persistenz
`homeassistant.helpers.storage.Store`, Schlüssel `netzentgelt_rechner.<entry_id>`, Version 1:
`{"params": {...}, "windows": [...], "results": {...}|null, "status": "...", "error": null}`.
Verzögertes Speichern (`async_delay_save`, 5 s) bei Parameteränderung, sofortiges nach Berechnung.
`windows` ist eine Liste von `{stufe, von, bis, stunde_von, stunde_bis}` (ISO-Daten). Ein `windows`-Dict
(Quartals-Zeitfenster aus v1.0.0) wird beim Laden mit `windows_from_quarters(…, aktuelles Jahr)` umgewandelt.
Migration: `version`-Feld; unbekannte Schlüssel ignorieren, fehlende mit Standard füllen.

## 4 Entitäten

Gerät: `DeviceInfo(identifiers={(DOMAIN, entry_id)}, name=entry.title, entry_type=SERVICE)`; der Titel ist der vom Nutzer vergebene Instanzname (§9a).
Alle `has_entity_name=True`, `unique_id = f"{entry_id}_{key}"`.

| Plattform | key | Name | Einheit | Kategorie | Hinweis |
|---|---|---|---|---|---|
| sensor | `netzentgelt` | Netzentgelt Modul 3 | ct/kWh | – | state_class measurement; siehe 4.1 |
| sensor | `wirtschaftlichkeit` | Wirtschaftlichkeit | – | – | device_class enum; siehe 4.2 |
| number | je `NUMBER_PARAMS`-Schlüssel | Namen laut Const | laut Const | config | `mode=box`, Änderung → Hub |
| button | `neu_berechnen` | Neu berechnen | – | – | startet `hub.async_calculate()` als Hintergrund-Task |

Empfehlung: nach Installation Entity-IDs über die Registry auf kurze Namen setzen
(`sensor.netzentgelt_modul3`, `sensor.wirtschaftlichkeit`) – nicht Teil des Codes, aber im README
beschreiben und im E2E-Test **nicht** voraussetzen (Suche über `unique_id`).

### 4.1 Attribute `sensor.netzentgelt`

```json
{
  "stufe": "Hochtarif",
  "quartal": "Q4",
  "preise": {"nt": 4.41, "st": 11.06, "ht": 16.07},
  "zeitplan": [{"stufe": "Niedertarif", "von": "2026-01-01", "bis": "2026-12-31", "stunde_von": 23, "stunde_bis": 5}],
  "data": [
    {"start_time": "2026-10-10T00:00:00+02:00", "end_time": "2026-10-10T01:00:00+02:00",
     "stufe": "N", "price_per_kwh": 0.0441}
  ]
}
```
- `price_per_kwh` in **€/kWh brutto** (kompatibel zu den EPEX-Sensoren), Zustand in **ct/kWh**.
- `data`: heute 00:00 bis übermorgen 00:00 lokal (48, an Umstellungstagen 47/49 Slots).
- `_unrecorded_attributes = frozenset({"data", "zeitplan"})`.
- Aktualisierung: bei jeder Viertelstunde (`async_track_time_change`, Sekunde 2) und bei
  Parameter-/Tarifzeitenänderung.

### 4.2 Attribute `sensor.wirtschaftlichkeit`

Zustände: `nicht_berechnet` | `rechnet` | `fertig` | `fehler`.

```json
{
  "berechnet_am": "2026-10-11T03:30:12+02:00",
  "dauer_s": 7.4,
  "basis": {"von": "2025-10-01", "bis": "2026-09-30", "tage": 365,
            "bezug_kwh": 5312.3, "einspeisung_kwh": 10234.0, "boersenmittel_ct": 11.2},
  "szenarien": {
    "modul1":      {"passiv": 162.9},
    "modul3":      {"passiv": 0, "speicher": 0, "erweiterung": 0, "mehrwert": 0, "amortisation_jahre": null},
    "dynamisch":   {"…": 0},
    "kombination": {"…": 0}
  },
  "annahmen": {"fixed": 34.1, "…": "…"},
  "fehler": null
}
```
Werte auf 2 Nachkommastellen; `amortisation_jahre = null` wenn Mehrwert ≤ 1 €/Jahr.

## 5 Datenzugriff (Recorder)

```python
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period

rows = await get_instance(hass).async_add_executor_job(
    statistics_during_period, hass, start_utc, end_utc, {id1, id2}, "hour", None, {"change"}
)
```
- Zeitraum: letzte 12 **volle lokale Monate** (`[1. des Monats vor 12 Monaten, 1. des aktuellen Monats)`).
- Bezug/Einspeisung: Typ `change` (Zähler `total_increasing`), Preis: Typ `mean`. `start` ist je nach
  HA-Version Sekunden (float) – im Test gegen die gepinnte Version prüfen und in **einer** Funktion
  normalisieren (`_ts(row)`).
- `None`-Werte → 0 (Verbrauch) bzw. Stunde überspringen (Preis). Negative `change` (Zählerreset) → 0.
- Tag gilt als vollständig, wenn 23, 24 oder 25 Stunden mit Preis vorliegen (Zeitumstellung).
- Lokale Zeit: `zoneinfo.ZoneInfo(hass.config.time_zone)`.
- **Nie** direkt auf die Datenbank zugreifen (egal ob SQLite, MariaDB oder PostgreSQL; Last, Backend-Unabhängigkeit),
  nur über die Recorder-API.

## 6 Nebenläufigkeit und Last (AK-6, AK-7)

- `Hub.async_calculate()`: `asyncio.Lock` (nicht blockierend: `if lock.locked(): return`), Status
  `rechnet`, danach `fertig`/`fehler`; immer im `finally` speichern und Dispatcher feuern.
- Datenabruf im Recorder-Executor (siehe §5), Rechnung in `hass.async_add_executor_job(calc.evaluate, …)`.
- `calc.evaluate(days, params, *, pause=None)` ruft nach jeder Tagesoptimierung (je Szenario und Speichergröße) und nach jedem Tag `pause()` auf; der Hub übergibt
  `lambda: time.sleep(0.002)`. Dadurch gibt der Thread die GIL regelmäßig frei; Ziel: Event-Loop-
  Verzögerung < 50 ms (E2E-Messung).
- Keine Berechnung unmittelbar beim Start: `async_at_started` + `async_call_later(300)`; nur falls
  `results is None` (AK-9).
- Monatlicher Lauf: `async_track_time_change(hour=3, minute=30, second=0)`, im Callback `day == 1`
  prüfen (lokale Zeit).
- Button und Zeitplaner starten die Berechnung via `entry.async_create_background_task`.
- Timeout-Wächter: Gesamtlauf > 120 s → abbrechen (Flag `cancel` in `pause()`), Status `fehler`.

## 6a Mehrere Instanzen (AK-20, AK-21)

- Alles Zustandsbehaftete hängt am Entry: `Hub` in `entry.runtime_data`, Store `netzentgelt_rechner.<entry_id>`,
  `unique_id = f"{entry_id}_{key}"`, Gerät je Entry. Es gibt keinen modulweiten Zustand außer dem Lock unten.
- **Globales Single-Flight:** `hass.data[DOMAIN]["calc_lock"]` (ein `asyncio.Lock`). `Hub.async_calculate()` bleibt
  je Instanz idempotent (läuft sie schon, ist ein weiterer Auslöser ein No-op, AK-6), erwirbt dann aber das globale Lock
  **vor** Statistik-Abruf und Rechnung; die Zeitmessung (`dauer_s`) und der 120-s-Wächter beginnen erst nach dem Erwerb.
  Wartend ist der Status `rechnet`. Auslöser (Monatslauf 03:30, Start +300 s) feuern bei allen Instanzen gleichzeitig
  und reihen sich über das Lock ein.
- Beim Entladen einer Instanz wird nur ihr eigener Zustand gespeichert/freigegeben; das globale Lock bleibt.

## 7 Rechenkern (`calc/`)

Das Verfahren ist gegen eine Vollenumeration verifiziert (`tests/unit/test_dp_bruteforce.py`). Öffentliche API:

```python
def stage(windows: Sequence[TariffWindow], day: date, hour: int) -> str            # 'N'|'S'|'H'
def import_price(scenario: str, p: Params, windows, day: date, hour: int, spot: float) -> float
def build_days(imp, exp, price, tz) -> dict[date, list[Hour]]                 # nur vollständige Tage
def dp_day(cbuy, fi, imp, exp, cap_kwh, p: Params) -> float                   # ≤ 0 = Gewinn
def evaluate(days, p: Params, windows, *, ref_year: int, pause=None) -> Result   # day → project_day(day, ref_year)
def slots(now_local: datetime, p: Params, windows) -> list[Slot]              # Netzentgelt-Verlauf
```

Regeln:
- Preisformeln exakt wie Fach-Spec §4/§5. `netz(q,h)` über `stage` + `fees.price`.
- `dp_day`: Rückwärtsinduktion über Füllstände `0..n` (Raster `step=1 kWh`), Aktionen
  `k ∈ [-kd, kc]`; Kosten je Stunde und Aktion vorab tabellieren; Laden: `bus = k·q/η`,
  `ab = min(exp, bus)`, Kosten `(bus-ab)·cbuy + ab·fi + wear·k·q`; Entladen: `d = |k|·q·η`,
  `use = min(d, imp)`, Kosten `−use·cbuy − (d−use)·fi + wear·|k|·q`. Rückgabe `V[0][0]`.
- `η = √eta_rt`; `kc = max(1, int(c_rate·cap·η/q))`, `kd = max(1, int(c_rate·cap/(η·q)))`.
- `fi = feedin` falls `spot ≥ 0`, sonst 0.
- Tage mit `Σimp ≤ 0.5` überspringen. Skalierung `365/Anzahl_Tage`.
- **Bekannte Eigenschaft**: Ergebnis hängt nur über `imp/exp` vom vorhandenen System ab; kein
  Zustand zwischen Tagen.

## 8 Config Flow

- Mehrfach einrichtbar (kein `single_config_entry`, AK-20), Schritt `user`: Pflichtfeld `name` (Titel des Entries,
  Standard „Netzentgelt-Rechner“, bei Belegung mit Zähler „… 2“; doppelter Name → Fehler `name_exists` am Feld), dazu drei `EntitySelector(domain="sensor")` für
  `import_entity`, `export_entity`, `price_entity` mit Standardwerten aus `const`.
  Validierung: Entität existiert im Zustandsautomaten **oder** in der Statistik-Metadatentabelle
  (`async_list_statistic_ids`) → sonst Fehler `entity_not_found` (AK-11).
- OptionsFlow (`OptionsFlowWithReload`): Menü-Schritt `init` mit der aktuellen Tarifzeiten-Liste im Text
  (`description_placeholders`) und den Einträgen `sources` (die drei Felder; Änderung → Entry neu laden),
  `window_add`, `window_edit` (Auswahl → Formular), `window_delete` (Mehrfachauswahl). Formular: `stage`
  (`SelectSelector` N/H), `start_date`, `end_date` (`DateSelector`), `from_hour` (0–23), `to_hour` (1–24)
  (`NumberSelector`, Box, Schritt 1). Fehler (`WindowError`) → Fehlerschlüssel `window_<code>` am Feld
  (`end_date`, `to_hour`, `from_hour`, bei `overlap` am `start_date` mit Platzhalter `{conflict}`).
  Gespeichert wird über `hub.async_set_windows(...)` (Store, Signal, keine Neuberechnung); die Optionen des
  Entries bleiben unverändert, es folgt kein Neuladen. Listenbeschriftung: `NT|HT · TT.MM.JJJJ–TT.MM.JJJJ · HH–HH Uhr`.
- Beim Setup werden veraltete Entitäten `text.*zeitfenster_q1…q4` aus der Entity-Registry entfernt (AK-17).
- Alle Texte in `translations/{de,en}.json`; Standard Deutsch.

## 9 Fehlerbehandlung und Logging

- Erwartbare Fehler (keine Statistik, < 200 Tage, Preise fehlen) → `fehler` + Klartext in Attribut
  `fehler`, Log WARNING einzeilig, **kein** Traceback.
- Unerwartete Fehler → `_LOGGER.exception`, Status `fehler`, Meldung „Interner Fehler, siehe Log“.
- Logger `custom_components.netzentgelt_rechner`; DEBUG: Dauer je Phase, Anzahl Tage/Zeilen.
- Diagnostics-Platform (`diagnostics.py`): Parameter, Status, Basisdaten (keine Verbrauchsreihen).

## 9a Kompatibilität und Stolpersteine

- Attribut-Größenlimit des Recorders 16 KB → `_unrecorded_attributes` (siehe 4.1).
- `statistics_during_period` ist eine **synchrone** Funktion und gehört in den Recorder-Executor.
- Zeitumstellung: Tage mit 23/25 Stunden; Tarifzeiten-Zuordnung nach lokalem Datum; Auswertung über `project_day`.
- Number-Entitäten mit `mode=box`; Float-Rundung auf Schrittweite im `native_value`.
- Tarifzeiten werden im Options-Flow und zusätzlich im Hub validiert (`calc.validate_windows`).

## 10 Packaging

- `hacs.json`: `{"name": "Netzentgelt-Rechner", "homeassistant": "2026.2.0", "zip_release": true,
  "filename": "netzentgelt_rechner.zip"}`; `manifest.json` Version wird vom Release-Tool gesetzt.
- Auslieferung ausschließlich `custom_components/netzentgelt_rechner/` (Zip-Wurzel = Inhalt dieses Ordners).
- Installation: HACS (Custom Repository) oder manuell nach `/config/custom_components/`.
