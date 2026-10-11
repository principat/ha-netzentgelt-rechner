# 01 Fachliche Spezifikation

Stand: 10.10.2026 · Status: Entwurf zur Umsetzung · Sprache: Deutsch

## 1 Zweck

Betreiber einer PV-Anlage mit Batteriespeicher in Deutschland wollen entscheiden:

1. Lohnt §14a EnWG **Modul 3** (zeitvariable Netzentgelte, nur zusammen mit Modul 1)?
2. Lohnt ein **dynamischer Stromtarif** (Börsenpreis, Day-Ahead)?
3. Lohnt die **Kombination** aus beidem?
4. Lohnt eine **Speichererweiterung** (zusätzliche nutzbare Kapazität zu frei wählbaren Kosten) – jeweils unter 1–3?

Die Integration beantwortet das **aus den eigenen gemessenen Daten** des Nutzers (Langzeitstatistik von
Netzbezug und Einspeisung) und zeigt die Antwort dauerhaft im Dashboard. Alle Tarif- und Anlagenwerte sind
**Eingaben des Nutzers** und im Dashboard editierbar; die Integration enthält keine verbindlichen Tarifdaten
eines bestimmten Netzbetreibers. Zusätzlich liefert sie das **Netzentgelt Modul 3 als zeitlichen Verlauf**
(ein Sensor, Attribute), z. B. als Eingang für Energiemanagementsysteme.

## 2 Nutzer und Kontext

Ein Privathaushalt mit Home Assistant (inkl. Energie-Dashboard bzw. Langzeitstatistiken) und
- einer **PV-Anlage** (Einspeisung ins Netz, ggf. mit Einspeisevergütung),
- mindestens einem **Batteriespeicher**; ein Teil davon, der aus dem Netz laden und ins Haus entladen darf,
  gilt als „verschiebbar“ (§3),
- einem **Netzbezugs- und einem Einspeisezähler**, deren Energiewerte als Langzeitstatistik vorliegen,
- optional einem Sensor mit dem **Börsenpreis** (Day-Ahead, netto) für die Szenarien mit dynamischem Tarif.

Weitere Verbraucher (E-Auto, Wärmepumpe usw.) sind nicht gesondert modelliert; sie gehen über das
gemessene Verbrauchsprofil ein. Ein intelligentes Messsystem (iMSys) ist Voraussetzung für Modul 3 in der
Praxis, wird aber von der Integration nicht geprüft.

Die Standardwerte der Eingaben (§8) und die Zeitfenster (§7) sind **Beispielwerte** und müssen vom Nutzer
anhand des Preisblatts des eigenen Netzbetreibers und des eigenen Tarifs angepasst werden. Messwerte und
Hintergründe der Referenzanlage des Autors: `05-vorwissen-und-fakten.md`.

## 3 Begriffe

| Begriff | Bedeutung |
|---|---|
| Modul 1 | Pauschale Netzentgeltreduzierung für steuerbare Verbrauchseinrichtungen (§14a), € pro Jahr |
| Modul 3 | Zeitvariable Netzentgelte in drei Stufen, nur zusammen mit Modul 1, braucht iMSys |
| NT / ST / HT | Niedertarif / Standardstufe / Hochtarif (Arbeitspreis des Netzentgelts, ct/kWh) |
| Tarifzeit | Eintrag der Liste in §7: Stufe (HT oder NT), Start- und Enddatum, Start- und Endstunde. Alle Zeiten ohne Eintrag sind Standardstufe |
| Dynamischer Tarif | Energiepreis = Börsenpreis (Day-Ahead) + Aufschlag; Netzentgelt, Umlagen, Steuern kommen dazu |
| Börsenpreis (Spot) | Netto, €/kWh, Quelle `sensor.epex_preis_verlauf` (Langzeitstatistik, stündlich gemittelt) |
| Verschiebbarer Speicher | Speicherkapazität, die aus dem Netz laden und ins Haus entladen darf |
| Passiv | Nur der Tarif ändert sich; das Verbrauchsprofil bleibt wie im Basiszeitraum |
| Optimiert | Zusätzlich fährt der verschiebbare Speicher täglich preisoptimal |

## 4 Szenarien

Alle Ergebnisse sind **Ersparnis in € pro Jahr gegenüber dem heutigen Festpreis** (positiv = spart).

| Nr | Szenario | Strompreis je kWh Netzbezug |
|---|---|---|
| S0 | Heute (Referenz) | `fixed` |
| S1 | Modul 1 allein | `fixed`, plus Pauschale `rebate` |
| S2 | Modul 3 (inkl. Modul 1) | `e_fix + netz(Quartal, Stunde) + umlagen`, plus `rebate`, minus `m3_base_delta` |
| S3 | Dynamischer Tarif | `(spot + markup)·(1+MwSt) + st + umlagen`, minus `dyn_base` |
| S4 | Kombination | `(spot + markup)·(1+MwSt) + netz(Quartal, Stunde) + umlagen`, plus `rebate`, minus `dyn_base`, minus `m3_base_delta` |

mit `e_fix = fixed − st − umlagen` (Energieanteil des heutigen Festpreises, brutto).

Jedes der Szenarien S2–S4 wird in **drei Varianten** gerechnet:

- **passiv**: gleiches Profil, nur Tarifänderung.
- **mit Speicher**: plus tägliche Optimierung mit `flex_kwh` verschiebbarem Speicher.
- **mit Erweiterung**: Optimierung mit `flex_kwh + extra_kwh`.

Abgeleitet: **Mehrwert der Erweiterung** = (mit Erweiterung) − (mit Speicher) und
**Amortisation** = `invest / Mehrwert` in Jahren (nur wenn Mehrwert > 1 €/Jahr, sonst „lohnt nicht“).

## 5 Preismodell (Einheiten und Formeln)

- Intern €/kWh; Eingaben des Nutzers in **ct/kWh** (Netzentgelt, Arbeitspreis, Umlagen, Aufschlag,
  Verschleiß) bzw. €/Jahr; Umrechnung zentral.
- `netz(q, h)` = `nt`, `st` oder `ht` je nach Zeichen `zeitfenster[q][h]` (`N`, `S`, `H`).
- `umlagen` = Konzessionsabgabe + KWKG + §19-Umlage + Offshore + Stromsteuer, **brutto**, ein Wert.
- Mehrwertsteuer nur auf `(spot + markup)`; Netzentgelt, Umlagen, `fixed` sind bereits brutto.
- Negative Börsenpreise werden an den Kunden durchgereicht (Energieanteil kann negativ werden;
  Netzentgelt und Umlagen bleiben positiv).
- Einspeisevergütung `feedin` (€/kWh) gilt nur bei Börsenpreis ≥ 0; bei negativem Börsenpreis 0
  (Annahme: Anlage ab 25.02.2025, Solarspitzengesetz).
- Jahreswerte: Summe über die **letzten 12 vollen Monate**, auf 365 Tage skaliert, wenn weniger
  vollständige Tage vorliegen.

## 6 Speicheroptimierung (fachliche Regeln)

Je Tag und je Szenario mit bekannten Tagespreisen (Day-Ahead) und dem **tatsächlichen**
Bezugs-/Einspeiseprofil des Tages als Rest nach dem vorhandenen System:

1. Der Speicher startet jeden Tag **leer**, der Endstand wird nicht bewertet.
2. **Laden** darf aus Überschuss (zuerst, Opportunitätskosten = Einspeisevergütung der Stunde) und
   aus dem Netz (Kosten = Bezugspreis der Stunde). **Entladen** ersetzt zuerst Netzbezug; Rest geht
   ins Netz (Vergütung der Stunde).
3. Wirkungsgrad `eta_rt` (Laden × Entladen), je Richtung `√eta_rt`.
4. Leistung ≤ `c_rate · Kapazität` je Stunde; Füllstandsraster 1 kWh; Verschleißkosten je kWh Durchsatz.
5. Tage mit Netzbezug ≤ 0,5 kWh werden nicht optimiert (kein Nutzen, spart Rechenzeit).
6. Das Ergebnis je Tag ist das **exakte Optimum** (Dynamische Programmierung); das Verfahren muss
   gegen eine Vollenumeration für kleine Fälle identisch sein (AK-4).

Bewusste Vereinfachungen (müssen im Dashboard sichtbar benannt sein): Preise des Tages sind im Voraus
bekannt; keine Prognosefehler; vorhandener Speicherbetrieb ist im Basisprofil enthalten (der
verschiebbare Speicher wird „oben drauf“ gerechnet); keine iMSys-/Steuerboxkosten.

## 7 Tarifzeiten Netzentgelt

Der Nutzer pflegt eine **Liste von Tarifzeiten**, getrennt nach Hochtarif (HT) und Niedertarif (NT). Alle
Zeiten, die in keiner Tarifzeit liegen, gelten als **Standardstufe** (ST). Ein Eintrag besteht aus:

| Feld | Bedeutung |
|---|---|
| Stufe | Hochtarif oder Niedertarif |
| Startdatum, Enddatum | konkrete Kalendertage inkl. Jahr, beide **einschließlich** (z. B. 01.01.2026 – 31.03.2026) |
| Startstunde | 0–23, volle Stunde, ab der die Tarifzeit täglich gilt |
| Endstunde | 1–24, volle Stunde, bis zu der sie gilt (**ausschließlich**; 17 bis 19 = 17:00–19:00 Uhr) |

- **Über Mitternacht:** Ist die Endstunde kleiner als die Startstunde (z. B. 23 bis 5), gilt die Tarifzeit
  an jedem Tag des Datumsbereichs von der Startstunde bis Mitternacht und von Mitternacht bis zur Endstunde.
  Start- und Endstunde dürfen nicht gleich sein; 0 bis 24 bedeutet ganztägig.
- **Keine Überschneidung:** Zwei Einträge dürfen sich weder im Datumsbereich noch in den Stunden
  überschneiden (egal ob HT oder NT). Sonst wird der Eintrag mit einer verständlichen Meldung am betroffenen
  Feld abgelehnt und nicht gespeichert.
- **Eingabe:** im Optionsdialog der Integration als Liste: Eintrag hinzufügen, bearbeiten, löschen. Der
  Dialog zeigt die aktuelle Liste. Intern wird bei Bedarf eine vollständige Zeittabelle (Datum × Stunde →
  Stufe) aufgebaut; der Nutzer sieht sie nie.
- **Standard:** beim ersten Einrichten steht eine Beispielliste für das laufende Kalenderjahr
  (01.01.–31.12.): NT 23–5 Uhr, HT 11–13 Uhr, HT 17–19 Uhr – **Annahme**, vom Nutzer anzupassen.
- Die Preise `nt`, `st`, `ht` gelten ganzjährig (siehe offene Frage F-2).
- Datum und Stunde richten sich nach der **lokalen** Zeit (Europe/Berlin), Zeitumstellung korrekt
  (23/25-Stunden-Tage).
- **Netzentgelt-Sensor** (heute/morgen): wendet die Tarifzeiten mit **exaktem Datum** an. Liegt ein Tag in
  keiner Tarifzeit (z. B. weil das Jahr nicht gepflegt ist), gilt dort die Standardstufe.
- **Auswertung (Rückblick auf die letzten 12 Monate):** Die Tarifzeiten werden **nur nach Tag und Monat**
  angewendet. Jeder Tag der Statistik wird dazu auf das Jahr der Berechnung abgebildet (29.02. auf 28.02.,
  wenn das Jahr kein Schaltjahr ist) und dort nachgeschlagen. So gilt der aktuelle Tarif für den ganzen
  Zeitraum, ohne dass Vorjahre gepflegt werden müssen.
- Der Sensor liefert: aktuellen Preis, aktuelle Stufe, Quartal, die Preise, die Tarifzeiten und einen
  Verlauf für heute und morgen (stündlich) im selben Format wie die EPEX-Sensoren (`price_per_kwh`),
  damit Diagramme und Energiemanagementsysteme ihn wie einen Preissensor nutzen können.
- **Übernahme aus Version 1.0.0:** Die früheren Quartals-Zeitfenster (24 Zeichen je Quartal) werden beim
  ersten Laden verlustfrei in Tarifzeiten mit den Daten des Quartals im aktuellen Jahr umgewandelt.

## 8 Eingaben (im Dashboard editierbar)

| Schlüssel | Name | Einheit | Standard | Status |
|---|---|---|---|---|
| fixed | Arbeitspreis heute (brutto) | ct/kWh | 34,10 | Beispiel; eigenen Tarif eintragen |
| st | Netzentgelt Standardstufe | ct/kWh | 11,06 | Beispiel (Preisblatt des Netzbetreibers 2026); **Annahme**: gleich heutigem Netzentgelt |
| nt | Netzentgelt Niedertarif | ct/kWh | 4,41 | Beispiel (Preisblatt des Netzbetreibers 2026, brutto) |
| ht | Netzentgelt Hochtarif | ct/kWh | 16,07 | Beispiel (Preisblatt des Netzbetreibers 2026, brutto) |
| levies | Umlagen und Steuern | ct/kWh | 8,8 | **Schätzung** (KA 2,84 + KWKG/§19/Offshore ≈ 3,5 + Stromsteuer 2,44, brutto) |
| vat | Mehrwertsteuer | % | 19 | verifiziert |
| markup | Aufschlag dynamischer Tarif | ct/kWh netto | 2,0 | **Annahme** |
| dyn_base | Mehr-Grundgebühr dynamisch | €/Jahr | 40 | **Annahme** |
| rebate | Modul-1-Pauschale | €/Jahr | 162,91 | Beispiel (Preisblatt des Netzbetreibers 2026, brutto) |
| m3_base_delta | Zusatz-Grundpreis Modul 3 | €/Jahr | 0 | **unbekannt** |
| feedin | Einspeisevergütung | ct/kWh | 6,29 | Beispiel; tatsächlichen anzulegenden Wert bzw. Vergütung eintragen |
| eta_rt | Wirkungsgrad Speicher | % | 88 | Annahme |
| flex_kwh | verschiebbarer Speicher (nutzbar) | kWh | 13,5 | Beispiel: 15 kWh × 0,9 nutzbar |
| extra_kwh | Erweiterung (nutzbar) | kWh | 14,4 | Beispiel: 16 kWh × 0,9 nutzbar |
| c_rate | Leistung | 1/h | 0,5 | Annahme |
| wear | Verschleiß | ct/kWh | 0 | Annahme |
| invest | Kosten Erweiterung | € | 1500 | Beispiel; eigene Kosten eintragen |
| tarifzeiten | Liste der HT-/NT-Tarifzeiten | Liste (Optionsdialog) | siehe §7 | Annahme |

Die Standardwerte stammen aus der Referenzanlage des Autors (Netzbetreiber SachsenNetze, Dresden, Stand 2026)
und sind **Beispielwerte**. Wer einen anderen Netzbetreiber oder Tarif hat, trägt seine eigenen Werte ein.

Datenquellen (konfigurierbar im Einrichtungsdialog): Bezugszähler, Einspeisezähler, Börsenpreis-Sensor.

## 9 Ausgaben

1. **Sensor „Netzentgelt Modul 3“**: Zustand = aktueller Preis (ct/kWh brutto); Attribute `stufe`,
   `quartal`, `preise`, `zeitplan` (Liste der Tarifzeiten), `data` (Verlauf heute+morgen).
2. **Sensor „Wirtschaftlichkeit“**: Zustand = Status (`nicht_berechnet`, `rechnet`, `fertig`, `fehler`);
   Attribute `berechnet_am`, `basis`, `szenarien`, `annahmen`, `fehler`.
3. **Zahlen-Entitäten** für alle Zahleneingaben (§8) und der **Optionsdialog** für die Tarifzeiten (§7), **Button** „Neu berechnen“.
4. Ein mitgeliefertes **Dashboard-Beispiel** (YAML im Repo) mit: Tabelle der Szenarien, Balkendiagramm,
   Eingabekarte, Preisverlauf des Netzentgelts.

## 10 Nicht-Ziele

Keine Steuerung von Geräten (das übernimmt ein Energiemanagementsystem); keine Prognose zukünftiger Preise; keine Berechnung
von iMSys-/Steuerboxkosten; keine Abrechnung; keine Cloud-Zugriffe; keine Mehrsprachigkeit über
Deutsch/Englisch hinaus; keine Mehrfachinstanz.

## 11 Akzeptanzkriterien

- **AK-1** Nach Einrichtung existieren alle Entitäten aus §9 unter einem Gerät „Netzentgelt-Rechner“.
- **AK-2** Zahleneingaben sind im Dashboard änderbar, werden validiert (Bereiche),
  überstehen einen HA-Neustart und lösen **keine** automatische Neuberechnung aus, aktualisieren aber
  den Netzentgelt-Sensor sofort.
- **AK-3** Der Netzentgelt-Sensor liefert zu jeder Viertelstunde den richtigen Preis gemäß Tarifzeiten (Datum,
  Stunde) und Zeitumstellung; `data` enthält 24 (heute) + 24 (morgen) Stundenwerte, an Zeitumstellungstagen 23/25.
- **AK-4** Die Optimierung (Tages-DP) stimmt in 100 % von ≥ 1000 zufälligen kleinen Fällen mit der
  Vollenumeration überein (Property-Test).
- **AK-5** Für ein festes synthetisches Jahr entsprechen alle Szenario-Ergebnisse den Golden-Werten
  (Toleranz ±0,01 €).
- **AK-6** „Neu berechnen“ startet genau einen Lauf; währenddessen weitere Auslöser werden ignoriert;
  Status wechselt `rechnet` → `fertig`/`fehler`.
- **AK-7** Eine Berechnung (12 Monate Stundendaten) blockiert den Event-Loop nie länger als 50 ms am
  Stück und beendet auf einem Raspberry Pi 5 in < 30 s (E2E-Messung auf Referenzgerät, im CI relativ
  zum Prototyp).
- **AK-8** Fehlende Statistik, fehlende Preise oder < 200 vollständige Tage → Status `fehler` mit
  verständlicher Meldung, keine Ausnahme im Log außer einer INFO/WARNING-Zeile.
- **AK-9** Automatische Neuberechnung am 1. jedes Monats um 03:30 Uhr und – falls noch keine
  Ergebnisse vorliegen – 5 Minuten nach HA-Start.
- **AK-10** Ergebnisse überstehen HA-Neustart (persistiert), Zustand bleibt `fertig`.
- **AK-11** Konfigurierbare Quellsensoren; Auswahl nicht vorhandener Entitäten wird abgelehnt.
- **AK-13** Tarifzeiten lassen sich im Optionsdialog hinzufügen, bearbeiten und löschen. Die Änderung wirkt
  sofort auf den Netzentgelt-Sensor, löst **keine** Neuberechnung aus und übersteht einen HA-Neustart.
- **AK-14** Ungültige Tarifzeiten (Enddatum vor Startdatum, Start- gleich Endstunde, Stunden außerhalb des
  Bereichs, Überschneidung mit einem anderen Eintrag) werden mit lokalisierter Meldung am betroffenen Feld
  abgelehnt; nichts wird gespeichert, die Integration bleibt stabil.
- **AK-15** Tarifzeiten über Mitternacht (z. B. 23–5 Uhr) und ganztägige (0–24 Uhr) werden korrekt angewendet;
  alle Zeiten ohne Tarifzeit sind Standardstufe.
- **AK-16** Die Auswertung wendet Tarifzeiten nach Tag/Monat auf das Jahr der Berechnung an (29.02. → 28.02.
  in Nichtschaltjahren); die Ergebnisse mit den früheren Quartals-Zeitfenstern bleiben dabei identisch
  (Golden-Test).
- **AK-17** Gespeicherte Quartals-Zeitfenster aus Version 1.0.0 werden verlustfrei in Tarifzeiten
  umgewandelt; veraltete Zeitfenster-Entitäten werden entfernt.
- **AK-12** Deutsche Oberfläche; alle Texte übersetzbar (`translations/de.json`, `en.json`).

## 12 Offene Fragen (vor/bei Umsetzung klären)

- **F-1** Gelten die HT/NT-Fenster beim eigenen Netzbetreiber ganzjährig gleich? (Standard: ja.)
- **F-2** Variieren auch die Preise je Quartal? Wenn ja: Preise je Quartal als zusätzliche Eingaben
  (Datenmodell ist vorbereitet, siehe Tech-Spec §3.3).
- **F-3** Entspricht die Standardstufe von Modul 3 dem heutigen Arbeitspreis des Netzentgelts?
- **F-4** Höhe der Modul-1-Pauschale netto/brutto und ob sie mit Modul 3 unverändert bleibt.
- **F-5** Gesamthöhe von Umlagen und Steuern 2026 (genaue Werte einsetzen).
- **F-6** Ist `feedin` = 6,29 ct der tatsächliche anzulegende Wert? (Teileinspeisung, 23,8 kWp.)
- **F-7** Soll die Auswertung später auch den **Ist-Betrieb** (Modul 3 aktiv) gegen die Prognose
  vergleichen? (Dann zusätzliche Kennzahlen.)
