# 05 Vorwissen und Fakten zur Zielumgebung

Stand 10.10.2026. „verifiziert“ = in der Umgebung geprüft; „Annahme“ = vom Nutzer zu bestätigen.

## 1 Umgebung (verifiziert)
- HA core 2026.10.0, Python 3.14.6, HAOS 18.3 auf Raspberry Pi 5, Recorder MariaDB.
- Add-ons: Advanced SSH & Web Terminal, Studio Code Server, Node-RED, Mosquitto, Home Assistant MCP Server.
- HACS-Frontend-Karten: plotly-graph-card (Kartentyp `custom:plotly-graph`), card-mod, button-card, auto-entities.
- Anlage: PV ca. 23,8 kWp; Sungrow SH20T (~20 kWh) und Felicity (~15 kWh), AC-gekoppelt.
- Netzbetreiber SachsenNetze, PLZ 01465; noch kein intelligentes Messsystem (iMSys).

## 2 Quellsensoren (verifiziert)
- Bezug: `sensor.watt_wachter_zahlerstand_bezug` (kWh, total_increasing)
- Einspeisung: `sensor.watt_wachter_zahlerstand_einspeisung`
- Börsenpreis: `sensor.epex_preis_verlauf` (Template-Helper, EUR/kWh netto, state_class measurement).
  Zustand = SMARD-Wert, sonst Energy-Charts-Wert (`_2`-Entitäten der epex_spot-Integration).
  Langzeitstatistik rückwirkend importiert ab Jan 2025 (stündlich mean/min/max).
- Aktueller Festpreis: `sensor.strompreis_aktueller_netzpreis` = 0,341 €/kWh.

## 3 Messwerte (verifiziert, Orientierung für Plausibilität)
- Bezug 12 Monate ca. 5.300 kWh; monatlich kWh: Okt25 346, Nov 791, Dez 1189, Jan26 1620, Feb 934, Mär 45,
  Apr 47, Mai 19, Jun 15, Jul 22, Aug 155, Sep 130. Einspeisung Mär–Sep ca. 1,2–1,7 MWh/Monat.
- Reale Börsenpreis-Mittel Sep/Okt 2026: ca. 14,5–16,7 ct/kWh (Netto-Spot inkl. nichts; höher als frühere Schätzung).
- Die Mehrwertsteuer ist NICHT die Ursache des Preisanstiegs (alte/neue Quelle stündlich identisch).

## 4 Tarifannahmen
| Größe | Wert | Status |
|---|---|---|
| NT 23–5 Uhr | 4,41 ct/kWh brutto | verifiziert (SachsenNetze 2026) |
| ST | 11,06 ct/kWh brutto | verifiziert, Annahme „= aktuelles Netzentgelt“ |
| HT 11–13 und 17–19 Uhr | 16,07 ct/kWh brutto | verifiziert |
| Modul 1 Pauschale | 162,91 €/a | verifiziert |
| Umlagen/Steuern | 8,8 ct brutto | Annahme |
| Dyn. Aufschlag | 2 ct netto | Annahme |
| Dyn. Grundgebühr | 40 €/a | Annahme |
| Einspeisevergütung | 6,29 ct (0 bei negativem Spot) | verifiziert/Annahme Regel |
| Wirkungsgrad | 88 % | Annahme |
| Flex-Speicher / Erweiterung | 13,5 / 14,4 kWh nutzbar | Annahme |
| C-Rate | 0,5 | Annahme |
| Erweiterungskosten | 1.500 € | Nutzerangabe |
Zeitfenster sind quartalsweise konfigurierbar; Standard `NNNNNSSSSSSHHSSSSHHSSSSN` (Index = Stunde 0–23).
Ob SachsenNetze Fenster je Quartal tatsächlich unterscheidet, ist offen (F-1); daher Quartale als Eingabe.

## 5 Stolpersteine
- **Recorder:** Langzeitstatistik nur mit `state_class`. `statistics_during_period` ist blockierend →
  im Recorder-Executor aufrufen. Kurzzeit-States nur ca. 10 Tage.
- **Attribute > 16 KB** werden verworfen → `_unrecorded_attributes`, Zeitplan kompakt halten.
- **Statistik-Import (E2E):** `recorder/import_statistics` per WebSocket; Metadaten `{has_mean, has_sum, name,
  source:"recorder", statistic_id, unit_of_measurement}`; Zeitstempel volle Stunde, ISO mit Zone.
- **Quellen-Ausfall:** SMARD lieferte zeitweise „no data found“; Energy-Charts als Zweitquelle.
- **Energy-Charts API:** `https://api.energy-charts.info/price?bzn=DE-LU&start=…&end=…`; Rate-Limit (HTTP 429)
  → Backoff; ab 01.10.2025 15-Minuten-Werte, davor stündlich; Preise EUR/MWh.
- **Zeitumstellung:** 23/25-Stunden-Tage; Zeitzone Europe/Berlin; im Rechenkern ohne tzdata testbar
  (Prototyp enthält DST-Funktion).
- **Plotly-Karte:** Typ `custom:plotly-graph`, nicht `plotly-graph-card`.
- **Netzwerk:** Die Entwicklungs-Sandbox darf evtl. keine Energiepreis-APIs erreichen; Tests nutzen nur
  synthetische Daten, die Integration selbst macht keine Netzzugriffe.

## 6 Zwischenstand in HA (zur Ablösung, Tech-Spec §11)
- Helper `input_number.m3_*` und `input_text.m3_info`, Dashboard `dashboard-strompreis` (Ansicht
  „Lohnt es sich?“, Pfad `wirtschaftlichkeit`), Utility-Meter + Select + Automation für Einspeisung bei
  negativen Preisen.
- Prototyp `reference/modul3_calc_prototype.py` (CLI `--no-write`, `--set name=value`) schreibt in die Helper.
  Reale Ergebnisse waren zum Übergabezeitpunkt noch nicht erzeugt.

## 7 Bisherige Einschätzung (Entscheidungshilfe, nicht Teil der Software)
Speichererweiterung (+16 kWh, ca. 1.500 €) noch nicht kaufen: zuerst Anmeldung, iMSys und Modul 3 zum Laufen
bringen und den Winter beobachten; dann mit echten Zahlen aus der Integration entscheiden.
