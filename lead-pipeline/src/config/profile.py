"""Industry Profile — configuration object that makes the pipeline industry-agnostic."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
    services_score: int = 0
    service_flag: bool = False
    distributor_flag: bool = False
    ssb_flag: bool = False
    leistung_text: str = ""
    reasoning: str = ""
    scraped_text_excerpt: str = ""
    reason_code: str = ""  # M37: OEM profile examples carry their reason code


@dataclass
class ScrapeConfig:
    """M37: per-profile website scrape settings. Defaults = ambulatory behaviour (4 paths, 2,500 chars)."""

    extra_paths: Optional[list[str]] = None  # None = web.extract_page_text defaults
    max_chars: int = 2500
    homepage_max_chars: Optional[int] = None  # None = homepage may fill max_chars
    homepage_min_chars: int = 800  # homepage at least this long = skip extra paths
    path_max_chars: Optional[int] = None  # None = one path may fill the rest
    skip_duplicate_pages: bool = False  # drop soft-404 pages that repeat the homepage
    link_keywords: Optional[list[str]] = None  # homepage links whose path holds a keyword go first
    max_link_pages: int = 4


@dataclass
class ClassificationConfig:
    target_description: str
    class_definitions: dict[str, str]
    examples: list[ClassificationExample] = field(default_factory=list)
    # M37: optional fields, absent in medtech_germany.json (defaults keep the ambulatory path unchanged)
    mode: str = "ambulatory"  # "ambulatory" | "oem"
    max_text_chars: int = 2000
    rule: str = ""
    reason_codes: list[str] = field(default_factory=list)
    examples_per_class: dict[str, int] = field(default_factory=dict)


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
    scrape: ScrapeConfig = field(default_factory=ScrapeConfig)


# M37: short names for --profile. The path form keeps working.
_PROFILE_ALIASES: dict[str, str] = {
    "oem": "profiles/oem_germany.json",
    "oem_germany": "profiles/oem_germany.json",
    "medtech": "profiles/medtech_germany.json",
    "medtech_germany": "profiles/medtech_germany.json",
}


def resolve_profile_path(value: "str | Path") -> Path:
    """Map a --profile value (alias or path) to a profile JSON path."""
    key = str(value).strip()
    alias = _PROFILE_ALIASES.get(key.lower())
    if alias:
        return Path(__file__).resolve().parents[2] / alias
    return Path(key)


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
        mode=cls_data.get("mode", "ambulatory"),
        max_text_chars=cls_data.get("max_text_chars", 2000),
        rule=cls_data.get("rule", ""),
        reason_codes=cls_data.get("reason_codes", []),
        examples_per_class=cls_data.get("examples_per_class", {}),
    )

    scrape_data = data.get("scrape", {})
    scrape = ScrapeConfig(
        extra_paths=scrape_data.get("extra_paths"),
        max_chars=scrape_data.get("max_chars", 2500),
        homepage_max_chars=scrape_data.get("homepage_max_chars"),
        homepage_min_chars=scrape_data.get("homepage_min_chars", 800),
        path_max_chars=scrape_data.get("path_max_chars"),
        skip_duplicate_pages=scrape_data.get("skip_duplicate_pages", False),
        link_keywords=scrape_data.get("link_keywords"),
        max_link_pages=scrape_data.get("max_link_pages", 4),
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
        scrape=scrape,
    )
