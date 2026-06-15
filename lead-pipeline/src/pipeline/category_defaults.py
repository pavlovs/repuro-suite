"""Category-driven default values for lead-pipeline outreach fields."""

from __future__ import annotations

CATEGORY_DEFAULTS: dict[str, dict[str, str]] = {
    "DEA": {
        "leistung_text": "Experten für Medizinprodukte",
        "leistung_absatz_2": "Unternehmen im Bereich Medizintechnik und -produkte",
        "mehrwerte": "neuen Wachstumsinitiativen, bei der Digitalisierung und im Einkauf durch Volumenbündelung",
    },
    "INT": {
        "leistung_text": "Medizintechnik-Experten",
        "leistung_absatz_2": "Unternehmen im Bereich Medizintechnik und -produkte",
        "mehrwerte": "neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und im Einkauf",
    },
    "SER_PLA_1": {
        "leistung_text": "Spezialisten für Praxis- und Klinikplanung",
        "leistung_absatz_2": "Unternehmen im Gesundheitswesen",
        "mehrwerte": "neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Fachkräftemangel",
    },
    "SER_PLA_2": {
        "leistung_text": "Medizintechnik-Experten",
        "leistung_absatz_2": "Experten für Medizintechnik und -ausstattung",
        "mehrwerte": "neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Qualitätsmanagement",
    },
    "SER_MAI": {
        "leistung_text": "Medizintechnik-Experten",
        "leistung_absatz_2": "Medizintechnik-Dienstleistern",
        "mehrwerte": "neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Qualitätsmanagement",
    },
    "SER_ITS": {
        "leistung_text": "IT-Experten im Gesundheitswesen",
        "leistung_absatz_2": "Medizintechnik- und IT-Experten im Gesundheitswesen",
        "mehrwerte": "neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Fachkräftemangel",
    },
}

_SHARED_DEFAULTS: dict[str, str] = {
    "gruppe_1": "Handels- und Servicespezialisten",
    "gruppe_2": "Komplettangebot mit deutschlandweitem Service-Netzwerk aus einer Hand",
}

TARGET_CATEGORIES: set[str] = {
    "DEA",
    "INT",
    "SER_PLA_1",
    "SER_PLA_2",
    "SER_MAI",
    "SER_ITS",
}

NON_TARGET_CATEGORIES: set[str] = {"OEM", "HEC", "OOS", "OTH", "B2C", "N/A"}


def apply_category_defaults(record: dict, category: str) -> dict:
    """Fill outreach fields from category mapping. Only fills empty/None fields."""
    defaults = CATEGORY_DEFAULTS.get(category)
    if defaults is None:
        return record

    for field, value in {**defaults, **_SHARED_DEFAULTS}.items():
        if not record.get(field):
            record[field] = value

    return record


def get_gesellschafter_field(anrede: str | None) -> str:
    """Derive gendered Gesellschafter label from Anrede."""
    if anrede == "Frau":
        return "Gesellschafterin"
    return "Gesellschafter"


def get_default_prio(category: str) -> str:
    """Return default prio: 'Prio 1' for target categories, 'Prio 2 (other)' otherwise."""
    if category in TARGET_CATEGORIES:
        return "Prio 1"
    return "Prio 2 (other)"
