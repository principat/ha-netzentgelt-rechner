"""Konstanten des Netzentgelt-Rechners."""

from __future__ import annotations

DOMAIN = "netzentgelt_rechner"

CONF_IMPORT = "import_entity"
CONF_EXPORT = "export_entity"
CONF_PRICE = "price_entity"

DEFAULT_IMPORT = "sensor.watt_wachter_zahlerstand_bezug"
DEFAULT_EXPORT = "sensor.watt_wachter_zahlerstand_einspeisung"
DEFAULT_PRICE = "sensor.epex_preis_verlauf"

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
    "flex_kwh": ("Vorhandener verschiebbarer Speicher (nutzbar)", "kWh", 0, 200, 0.1, 13.5),
    "extra_kwh": ("Speichererweiterung (nutzbar)", "kWh", 0, 200, 0.1, 14.4),
    "c_rate": ("Speicherleistung (C-Rate)", "1/h", 0.1, 3, 0.05, 0.5),
    "wear": ("Verschleißkosten Speicher", "ct/kWh", 0, 20, 0.01, 0.0),
    "invest": ("Kosten der Speichererweiterung", "€", 0, 100000, 10, 1500.0),
}

# Zeitfenster je Quartal: ein Zeichen je Stunde 0-23: N Niedertarif, S Standard, H Hochtarif
DEFAULT_WINDOW = "NNNNNSSSSSSHHSSSSHHSSSSN"
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
WINDOW_PATTERN = r"^[NSH]{24}$"

STAGE_NAMES = {"N": "Niedertarif", "S": "Standard", "H": "Hochtarif"}

STATUS_NONE = "nicht_berechnet"
STATUS_RUNNING = "rechnet"
STATUS_DONE = "fertig"
STATUS_ERROR = "fehler"
STATUSES = (STATUS_NONE, STATUS_RUNNING, STATUS_DONE, STATUS_ERROR)
