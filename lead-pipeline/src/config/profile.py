"""Industry Profile — configuration object that makes the pipeline industry-agnostic."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SupplementarySource:
    """Profile-specific additional data source (e.g. legacy Excel files).
    Only defined in profiles that have pre-existing data — most profiles won't have this.
    """
    type: str                          # "excel_sheets"
    path: str                          # relative to project root
    ingest_sheets: list[str]           # sheet names to load and re-classify
    dedup_sheets: list[str]            # sheets used as already-approached references
    city_region_sheet: str = ""        # sheet with city→region+preposition mapping (optional)


@dataclass
class DiscoveryConfig:
    wlw_search_terms: list[str]
    wlw_base_url: str = "https://www.wer-liefert-was.de"


@dataclass
class FilterConfig:
    ma_min: int = 5
    ma_max: int = 100
    nace_exclude: list[str] = field(default_factory=list)
    name_exclude_keywords: list[str] = field(default_factory=list)


@dataclass
class ClassificationExample:
    domain: str
    full_name: str
    klass: str
    services_score: int
    service_flag: bool
    distributor_flag: bool
    ssb_flag: bool
    leistung_text: str
    reasoning: str
    scraped_text_excerpt: str = ""


@dataclass
class ClassificationConfig:
    target_description: str
    class_definitions: dict[str, str]
    examples: list[ClassificationExample] = field(default_factory=list)


@dataclass
class OwnershipConfig:
    hard_disqualify_subsidiary_threshold_pct: float = 75.0
    hard_disqualify_pe_backed: bool = True


@dataclass
class ExportConfig:
    format: str = "serienbriefe"
    region_prepositions: dict[str, str] = field(default_factory=dict)


@dataclass
class IndustryProfile:
    id: str
    name: str
    description: str
    geography: dict[str, str]
    discovery: DiscoveryConfig
    filters: FilterConfig
    classification: ClassificationConfig
    ownership: OwnershipConfig
    export: ExportConfig
    supplementary_sources: list[SupplementarySource] = field(default_factory=list)


def load_profile(path: Path) -> IndustryProfile:
    """Load and validate an IndustryProfile from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    discovery = DiscoveryConfig(**data["discovery"])

    filter_data = data.get("filters", {})
    filters = FilterConfig(
        ma_min=filter_data.get("ma_min", 5),
        ma_max=filter_data.get("ma_max", 100),
        nace_exclude=filter_data.get("nace_exclude", []),
        name_exclude_keywords=filter_data.get("name_exclude_keywords", []),
    )

    cls_data = data["classification"]
    examples = [ClassificationExample(**e) for e in cls_data.get("examples", [])]
    classification = ClassificationConfig(
        target_description=cls_data["target_description"],
        class_definitions=cls_data["class_definitions"],
        examples=examples,
    )

    ownership_data = data.get("ownership", {})
    ownership = OwnershipConfig(
        hard_disqualify_subsidiary_threshold_pct=ownership_data.get(
            "hard_disqualify_subsidiary_threshold_pct", 75.0
        ),
        hard_disqualify_pe_backed=ownership_data.get("hard_disqualify_pe_backed", True),
    )

    export_data = data.get("export", {})
    export = ExportConfig(
        format=export_data.get("format", "serienbriefe"),
        region_prepositions=export_data.get("region_prepositions", {}),
    )

    supplementary_sources = [
        SupplementarySource(
            type=s["type"],
            path=s["path"],
            ingest_sheets=s["ingest_sheets"],
            dedup_sheets=s.get("dedup_sheets", s.get("dedup_sheet", [])),
            city_region_sheet=s.get("city_region_sheet", ""),
        )
        for s in data.get("supplementary_sources", [])
    ]

    return IndustryProfile(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        geography=data["geography"],
        discovery=discovery,
        filters=filters,
        classification=classification,
        ownership=ownership,
        export=export,
        supplementary_sources=supplementary_sources,
    )
