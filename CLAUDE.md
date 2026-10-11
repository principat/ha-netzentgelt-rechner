# CLAUDE.md – Netzentgelt-Rechner

Home-Assistant-Custom-Integration (`netzentgelt_rechner`), die für eine PV-Anlage mit Speicher
berechnet, wie sehr sich §14a-EnWG-Modul-3 (zeitvariable Netzentgelte), ein dynamischer
Stromtarif, deren Kombination und eine Speichererweiterung lohnen. Sie stellt außerdem das
quartalsweise Netzentgelt als **einen** Sensor mit Attributen bereit.

Lies zuerst, in dieser Reihenfolge:
1. `docs/01-fachliche-spezifikation.md` (WAS und WARUM, Akzeptanzkriterien)
2. `docs/02-technische-spezifikation.md` (WIE)
3. `docs/03-teststrategie.md` und `docs/04-release-workflow.md`
4. `docs/05-vorwissen-und-fakten.md` (geprüfte Fakten über die Zielumgebung und Stolpersteine)
5. `reference/` – lauffähiger, gegen Brute-Force geprüfter Prototyp der Rechenlogik

## Arbeitsweise (verbindlich)
- **Spec zuerst.** Jede Verhaltensänderung beginnt mit einer Änderung in `docs/01`/`02` und einem
  fehlschlagenden Test. Danach Code. Akzeptanzkriterien (AK-n) werden in Tests namentlich referenziert
  (`# AK-7`).
- **Kleine Schritte, grüne Pipeline.** Trunk-basiert: kurzlebige Branches `feat/…`, `fix/…`, PR nach
  `main`, Squash-Merge, Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`).
- **Definition of Done** je PR: ruff + mypy grün, Unit- und Integrationstests grün, Abdeckung der
  Rechenlogik `calc/` ≥ 95 % Zweige, hassfest und HACS-Validierung grün, Specs und CHANGELOG-relevante
  Texte aktualisiert, keine neuen Warnungen im HA-Log im E2E-Lauf.
- Sprache: Doku, UI-Texte, Entitätsnamen **Deutsch** (Übersetzungen `de`, Fallback `en`);
  Code, Bezeichner, Commit-Messages **Englisch**.

## Harte Randbedingungen
- **Den Event-Loop nie blockieren.** Alle Datenbank- und Rechenarbeit in Executor-Threads;
  Rechenschleifen geben regelmäßig die CPU ab (siehe Tech-Spec §6). Berechnung nie beim HA-Start
  sofort, immer verzögert.
- **Ein Berechnungslauf zur Zeit** (Single-Flight). Fehler dürfen HA nie beeinträchtigen: abfangen,
  loggen, Status „fehler“ setzen.
- Keine Netzwerkzugriffe, keine zusätzlichen Python-Abhängigkeiten (nur HA-Bordmittel).
- Rechenkern `calc/` ist **rein** (keine HA-Importe, deterministisch, voll getestet).
- Große Attribute (`data`, `zeitplan`) gehören in `_unrecorded_attributes`.
- Mindestversion HA: 2026.2.0 (CI-Matrix auch gegen aktuelles 2026.10.x); Python ≥ 3.13.
- Niemals Zugangsdaten, Tokens oder echte Verbrauchsdaten committen. E2E-Fixtures sind synthetisch
  oder anonymisiert.

## Übersetzungen
- `strings.json`, `translations/de.json`, `translations/en.json` bleiben schlüsselgleich
  (`tests/unit/test_translations.py`). Sie sind ICU MessageFormat: literale `{`/`}` mit
  Quote-Spans (`'{'`) maskieren, nicht verdoppeln; kein Markdown in Klartextfeldern.
- Config-Flow-Eingaben serverseitig validieren, Fehler lokalisiert am richtigen Feld; fehlerhafte
  Nutzereingaben dürfen die Integration nie abstürzen lassen.
- Tests immer als `python -m pytest` (bzw. `uv run pytest`) starten.

## Befehle (Soll, in `pyproject.toml`/`scripts/` anlegen)
- `uv run pytest tests/unit tests/integration` – schnelle Tests
- `uv run ruff check . && uv run ruff format --check . && uv run mypy custom_components`
- `scripts/e2e.sh` – startet HA im Container, spielt Fixtures ein, führt `tests/e2e` aus
- `scripts/dev-ha.sh` – lokales HA mit eingehängter Integration für Handtests

## Umgang mit Unsicherheit
Die fachlichen Annahmen (Tarifwerte, Umlagen, Zeitfenster) sind in der Fachspezifikation §8 mit
Status `verifiziert`/`Annahme` markiert. Annahmen **nie stillschweigend ändern**; sie sind
Eingabewerte des Nutzers. Offene Fragen stehen in §12. Bei Zweifeln: Frage stellen, nicht raten.
