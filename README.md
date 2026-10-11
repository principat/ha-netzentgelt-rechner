# Netzentgelt-Rechner (Home Assistant)

[Deutsch](#deutsch)

A Home Assistant custom integration for a PV system with battery storage. From your own long-term
statistics it calculates how much **§14a EnWG module 3** (time-variable grid fees), a **dynamic
electricity tariff**, their **combination** and a **storage extension** would save per year, and it
provides the quarterly grid fee as **one sensor** with attributes (e.g. as input for HAEO).

All figures are calculated locally from your data. No network access, no cloud, no extra dependencies.
Tariff values, levies and time windows are **editable assumptions** that you check against your own
grid operator's price sheet.

## Installation

1. HACS → three-dot menu → *Custom repositories* → add `https://github.com/principat/ha-netzentgelt-rechner`
   as category *Integration*.
2. Install *Netzentgelt-Rechner*, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Netzentgelt-Rechner*; pick your import meter,
   export meter and spot price sensor.
4. Adjust the assumptions on the device and press *Neu berechnen* (recalculate). The result appears in
   the *Wirtschaftlichkeit* (profitability) sensor; the current grid fee in the *Netzentgelt* sensor.

Requires Home Assistant 2026.2.0 or newer and at least 200 complete days of statistics.

Dashboard example: [`examples/en/dashboard.yaml`](examples/en/dashboard.yaml).

## Development

(German only.) Specification: `docs/01-fachliche-spezifikation.md`, technical: `docs/02-technische-spezifikation.md`,
tests: `docs/03-teststrategie.md`, release: `docs/04-release-workflow.md`, working agreement: `CLAUDE.md`.
Run tests with `python -m pytest`.

---

## Deutsch

Eine Home-Assistant-Custom-Integration für eine PV-Anlage mit Speicher. Sie berechnet aus Ihren
Langzeitstatistiken, wie sehr sich **§14a-EnWG-Modul 3** (zeitvariable Netzentgelte), ein **dynamischer
Stromtarif**, deren **Kombination** und eine **Speichererweiterung** pro Jahr lohnen, und stellt das
quartalsweise Netzentgelt als **einen Sensor** mit Attributen bereit (z. B. für HAEO).

Alles wird lokal aus Ihren Daten gerechnet: keine Netzwerkzugriffe, keine Cloud, keine zusätzlichen
Abhängigkeiten. Tarifwerte, Umlagen und Zeitfenster sind **editierbare Annahmen**, die Sie anhand des
Preisblatts Ihres Netzbetreibers prüfen.

### Installation

1. HACS → Menü (drei Punkte) → *Benutzerdefinierte Repositories* → `https://github.com/principat/ha-netzentgelt-rechner`
   als Kategorie *Integration* hinzufügen.
2. *Netzentgelt-Rechner* installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Netzentgelt-Rechner*; Bezugszähler,
   Einspeisezähler und Börsenpreis-Sensor wählen.
4. Annahmen am Gerät anpassen und *Neu berechnen* drücken. Das Ergebnis steht im Sensor
   *Wirtschaftlichkeit*, das aktuelle Netzentgelt im Sensor *Netzentgelt*.

Voraussetzung: Home Assistant 2026.2.0 oder neuer und mindestens 200 vollständige Tage Statistik.

Dashboard-Beispiel: [`examples/de/dashboard.yaml`](examples/de/dashboard.yaml).

### Entwicklung

Spezifikation: `docs/01-fachliche-spezifikation.md`, technisch: `docs/02-technische-spezifikation.md`,
Tests: `docs/03-teststrategie.md`, Release: `docs/04-release-workflow.md`, Arbeitsweise: `CLAUDE.md`.
Tests mit `python -m pytest`.
