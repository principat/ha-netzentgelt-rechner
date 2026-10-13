# 03 Teststrategie

Ziel: Jede Akzeptanzkriterium (AK-1..AK-12, siehe Fachspezifikation §11) ist durch mindestens einen
automatisierten Test belegt. Tests referenzieren das AK im Kommentar (`# AK-4`).

## 1 Testpyramide

| Ebene | Ort | Werkzeug | Läuft | Zweck |
|---|---|---|---|---|
| Unit | `tests/unit` | pytest, hypothesis | jeder Commit, < 30 s | reiner Rechenkern `calc/` |
| Integration | `tests/integration` | pytest-homeassistant-custom-component | jeder Commit, < 3 min | Setup, Entitäten, Config/Options Flow, Recorder-Zugriff, Persistenz |
| E2E | `tests/e2e` | echter HA-Container + REST/WebSocket | PR nach `main`, Release | Gesamtsystem inkl. echtem Recorder, Neustart, Last |

## 2 Unit-Tests (`calc/`)
- **Brute-Force-Äquivalenz (AK-4):** Property-Test mit hypothesis (≥ 1000 Fälle): Tages-DP == Vollenumeration
  für kleine Fälle (`tests/unit/test_dp_bruteforce.py`).
- **Preisformeln:** je Szenario S0–S4 und Quartal Beispielwerte von Hand gerechnet (Brutto/Netto, MwSt).
- **Tarifzeiten (AK-3, AK-14, AK-15, AK-16):** Datumsgrenzen (inklusive), Sommer-/Winterzeitumstellung
  (23/25-Stunden-Tage), Fenster über Mitternacht, ganztägig, nur N, nur H, Überschneidung/Fehlercodes,
  `project_day` (29.02.), `windows_from_quarters` (Golden bleibt identisch).
- **Invarianten:** Optimiert ≤ unoptimiert; mehr Speicher nie schlechter; Wirkungsgrad 100 % → Energieerhaltung;
  Einspeisung bei negativem Preis = 0 ct.
- **Golden-Test (AK-5):** festes synthetisches Jahr (Seed fest) → JSON in `tests/unit/golden/`. Änderung
  nur bewusst per `--update-golden` mit Begründung im PR.
- **Randfälle:** leere Tage, fehlende Stunden (< 200 vollständige Tage → Fehler, AK-8), NaN, Nullverbrauch.
- Abdeckung `calc/` ≥ 95 % Zweige (`--cov-branch`, Gate in CI).

## 3 Integrationstests (HA-Testharness)
- **Setup/Unload/Reload (AK-1):** Entitäten vorhanden, Gerät „Netzentgelt-Rechner“, `runtime_data` gesetzt.
- **Eingaben (AK-2):** `number.set_value` außerhalb des Bereichs → Fehler; Änderung einer Zahl aktualisiert den Sensor
  `netzentgelt` sofort ohne Recorder-Lauf. **Tarifzeiten (AK-13, AK-14, AK-17):** Optionsdialog hinzufügen/
  bearbeiten/löschen, Fehler am Feld, Wirkung auf Sensor, Persistenz, Übernahme alter Quartals-Fenster.
- **Sensor `netzentgelt` (AK-3):** Zeit einfrieren (`freezer`), pro Viertelstunde/Quartal richtiger Wert und
  Attribute (`stufe`, `quartal`, `preise`, `zeitplan` (Tarifzeiten), `data`).
- **Single-Flight (AK-6):** zwei gleichzeitige `button.press` → ein Lauf; Folgeauslöser ignoriert.
- **Recorder-Zugriff:** Recorder-Instanz im Testharness, Statistiken per `async_import_statistics` einspielen;
  Berechnung liefert Ergebnis; fehlende Statistik → Status `fehler` mit Klartext (AK-8).
- **Zeitplan (AK-9):** `async_fire_time_changed` auf 1. des Monats 03:30; Verzögerungsstart nur ohne Ergebnis.
- **Persistenz (AK-10):** Store füllen, Config-Entry neu laden, Ergebnisse und Status unverändert.
- **Config Flow (AK-11):** nicht vorhandene Entität abgelehnt; Options Flow ändert Quellen; mehrere Instanzen (Name Pflicht/eindeutig, AK-20).
- **Eingaben-Dialog (AK-18):** Menüeintrag `inputs`; Formular hat die Gruppen mit `hilfe` eingeklappt; Speichern ändert
  Parameter und Sensor sofort ohne Neuberechnung und speichert keine Anzeigefelder; Übersetzungstest: jedes
  `NUMBER_PARAMS`-Feld hat in `de`/`en` genau ein Feldlabel und einen Hilfeeintrag (`**Label**`), Quellsensoren und
  Tarifzeiten-Felder haben `data_description`.
- **Mehrere Instanzen (AK-20, AK-21):** zwei Entries mit unterschiedlichen Quellen/Eingaben/Tarifzeiten → eigene
  Entitäten, unabhängige Ergebnisse, Entladen der einen lässt die andere unverändert; Läufe zweier Instanzen
  überlappen nie (Nebenläufigkeits-Zähler), die wartende Instanz rechnet danach genau einmal.
- **Übersetzungen (AK-12):** `de.json` und `en.json` haben identische Schlüssel; kein Text ohne Schlüssel.
- **Event-Loop-Latenz (AK-7):** Watchdog-Task misst Schlafabweichung während eines 12-Monats-Laufs
  (Maximum < 50 ms, in CI-Toleranz 100 ms).

## 4 E2E-Tests
Aufbau (`scripts/e2e.sh`):
1. HA-Container `ghcr.io/home-assistant/home-assistant:<Version>` starten, `custom_components` einhängen,
   Config mit `recorder` (SQLite genügt) und Onboarding-Bypass (vorab erzeugte `.storage`-Dateien in
   `tests/e2e/fixtures/config`).
2. Langzeitstatistiken per WebSocket `recorder/import_statistics` einspielen (Fixtures aus
   `tests/e2e/fixtures/`, synthetisch; Zeitstempel in ISO-8601 mit Zeitzone; Einheiten kWh bzw. EUR/kWh).
3. Integration per REST `config_entries/flow` einrichten.
4. Tests per pytest + `aiohttp`/`websockets` gegen die laufende Instanz.

Szenarien:
- **E2E-1 Happy Path (AK-1, AK-5, AK-10):** einrichten → Berechnung → Ergebnisse == Golden → HA neu starten
  → Ergebnisse noch da.
- **E2E-2 Eingabe ändern (AK-2):** Parameter ändern → Netzentgelt-Sensor sofort aktualisiert, Status unverändert (keine automatische Neuberechnung); „Neu berechnen“ → neues Ergebnis plausibel.
- **E2E-3 Last (AK-7):** während der Berechnung 50 parallele Zustandsabfragen; p99 Latenz < 250 ms,
  keine Warnung „Detected blocking call“ / „Update of … is taking over“ im Log.
- **E2E-4 Fehlerfälle (AK-8):** ohne Statistik → `fehler`; HA bleibt bedienbar.
- **E2E-5 Log-Hygiene:** kein WARNING/ERROR der Domain im Lauf (außer erwartete in E2E-4).
- **E2E-6 Kompatibilität:** Matrix gegen HA `2026.2.x` (Minimum) und `2026.10.x` (aktuell).

## 5 Testdaten
- Nur synthetische Daten (Generator `tests/data_gen.py`, fester Seed); keine echten Zählerwerte.
- Preiszeitreihe: Tagesprofil + saisonaler Anteil + gelegentliche negative Mittagspreise.
- Verbrauchsprofil: Winter hoch, Sommer niedrig (ähnlich der Struktur in `docs/05`, aber erfunden).

## 6 CI-Gates (müssen grün sein zum Merge)
ruff (lint + format), mypy (strict für `calc/`), pytest Unit + Integration mit Coverage-Gate,
hassfest, HACS-Action, E2E (Matrix). Flaky Tests werden repariert, nicht wiederholt.
