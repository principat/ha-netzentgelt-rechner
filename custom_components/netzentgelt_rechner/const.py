"""Konstanten des Netzentgelt-Rechners."""

from __future__ import annotations

DOMAIN = "netzentgelt_rechner"

CONF_IMPORT = "import_entity"
CONF_EXPORT = "export_entity"
CONF_PRICE = "price_entity"


SIGNAL_UPDATE = f"{DOMAIN}_update"

# Eingabeparameter: Schluessel -> (Name, Einheit, min, max, Schritt, Standard)
NUMBER_PARAMS: dict[str, tuple[str, str, float, float, float, float]] = {
    "fixed": ("Arbeitspreis heute (brutto)", "ct/kWh", 0, 100, 0.01, 34.1),
    "st": ("Netzentgelt Standardstufe (brutto)", "ct/kWh", 0, 50, 0.01, 11.06),
    "nt": ("Netzentgelt Niedertarif (brutto)", "ct/kWh", 0, 50, 0.01, 4.41),
    "ht": ("Netzentgelt Hochtarif (brutto)", "ct/kWh", 0, 50, 0.01, 16.07),
    "levies": ("Umlagen und Steuern (brutto)", "ct/kWh", 0, 30, 0.01, 8.8),
    "vat": ("Mehrwertsteuer", "%", 0, 30, 0.1, 19.0),
    "markup": ("Aufschlag dynamischer Tarif (netto)", "ct/kWh", -5, 20, 0.01, 2.0),
    "dyn_base": ("Mehr-Grundgebuehr dynamischer Tarif", "€/Jahr", -500, 1000, 0.5, 40.0),
    "rebate": ("Modul-1-Pauschale", "€/Jahr", 0, 1000, 0.01, 162.91),
    "m3_base_delta": ("Zusatz-Grundpreis Modul 3", "€/Jahr", -500, 1000, 0.5, 0.0),
    "feedin": ("Einspeisevergütung", "ct/kWh", 0, 30, 0.01, 6.29),
    "eta_rt": ("Wirkungsgrad Speicher (Laden und Entladen)", "%", 50, 100, 0.5, 88.0),
    "flex_kwh": ("Nutzbare Speicherkapazität (vorhanden)", "kWh", 0, 200, 0.1, 13.5),
    "extra_kwh": ("Nutzbare Kapazität der Speichererweiterung", "kWh", 0, 200, 0.1, 14.4),
    "c_rate": ("Speicherleistung (C-Rate)", "1/h", 0.1, 3, 0.05, 0.5),
    "grid_import_kw": (
        "Netzanschluss: maximale Bezugsleistung (0 = unbegrenzt)",
        "kW",
        0,
        1000,
        0.1,
        0.0,
    ),
    "grid_export_kw": (
        "Netzanschluss: maximale Einspeiseleistung (0 = unbegrenzt)",
        "kW",
        0,
        1000,
        0.1,
        0.0,
    ),
    "wear": ("Verschleißkosten Speicher", "ct/kWh", 0, 20, 0.01, 0.0),
    "invest": ("Kosten der Speichererweiterung", "€", 0, 100000, 10, 1500.0),
}

# v1.0.0 stored one 24-character window per quarter (N/S/H per hour); kept for the migration
DEFAULT_WINDOW = "NNNNNSSSSSSHHSSSSHHSSSSN"

STAGE_NAMES = {"N": "Niedertarif", "S": "Standard", "H": "Hochtarif"}

STATUS_NONE = "nicht_berechnet"
STATUS_RUNNING = "rechnet"
STATUS_DONE = "fertig"
STATUS_ERROR = "fehler"
STATUSES = (STATUS_NONE, STATUS_RUNNING, STATUS_DONE, STATUS_ERROR)
