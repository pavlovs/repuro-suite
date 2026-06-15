"""CompanyRecord — universal data model for all pipeline stages."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Optional


@dataclass
class CompanyRecord:
    # Required identity fields
    domain: str
    full_name: str
    profile_id: str
    source: str  # "WLW" / "ORBIS" / "MASTER_CLEANING" / "MANUAL"

    # Computed from domain — do not pass in constructor
    id: str = field(init=False)

    # Location
    hrb_number: Optional[str] = None
    rechtsform: Optional[str] = None
    street: Optional[str] = None
    plz_ort: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    region_prep: Optional[str] = None

    # Size
    ma_count: Optional[int] = None
    revenue_tsd_eur: Optional[float] = None

    # Classification (filled by classify stage)
    klass: Optional[str] = None
    services_score: Optional[int] = None
    service_flag: Optional[bool] = None
    distributor_flag: Optional[bool] = None
    ssb_flag: Optional[bool] = None
    leistung_text: Optional[str] = None
    leistung_absatz_2: Optional[str] = None
    mehrwerte: Optional[str] = None
    reasoning: Optional[str] = None
    compliment_draft: Optional[str] = None
    compliment_2: Optional[str] = None
    reclassify_reason: Optional[str] = None  # set when ownership gate forces D
    prio: Optional[str] = None  # M36: queue priority (replaces klass-based filtering)
    gruppe_1: Optional[str] = None  # M36: category-driven letter field
    gruppe_2: Optional[str] = None  # M36: category-driven letter field
    gesellschafter_field: Optional[str] = None  # M36: gendered from Anrede
    gesellschafter_note: Optional[str] = None

    # Ownership (filled by enrich stage)
    gesellschafter_name: Optional[str] = None  # majority / controlling owner
    gesellschafter_share_pct: Optional[float] = None
    gesellschafter_age: Optional[int] = None
    is_subsidiary: Optional[bool] = None
    is_pe_backed: Optional[bool] = None
    all_gesellschafter: Optional[str] = None  # JSON array: all owners sorted by % desc

    # Contact (filled by email enrich stage)
    owner_name: Optional[str] = None
    gf_name: Optional[str] = None  # Geschäftsführer from impressum/OffeneRegister (M20)
    impressum_name: Optional[str] = (
        None  # Correct company name from Impressum (overrides full_name in letter)
    )
    impressum_address: Optional[str] = None
    openregister_address: Optional[str] = None
    gf_email: Optional[str] = None
    gf_phone: Optional[str] = None
    anrede: Optional[str] = None  # "Herr" / "Frau"
    salutation: Optional[str] = None  # "Sehr geehrter Herr X"

    # Send-out approval (M17)
    approved_for_sendout: int = 0

    # Pipeline metadata
    already_approached: bool = False
    filter_pass: Optional[bool] = None
    filter_reason: Optional[str] = None
    ownership_pass: Optional[bool] = None
    ownership_reason: Optional[str] = None
    scraped_text: Optional[str] = None
    scraped_at: Optional[datetime] = None
    classified_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "id", hashlib.md5(self.domain.encode()).hexdigest()[:12]
        )

    def to_dict(self) -> dict:
        """Serialize to dict for CSV. Converts datetimes to ISO strings."""
        d = asdict(self)
        for key in ("scraped_at", "classified_at", "enriched_at"):
            if d[key] is not None:
                d[key] = d[key].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CompanyRecord":
        """Deserialize from CSV dict. Handles type coercions."""
        d = {k: v for k, v in d.items()}

        # Datetime fields
        for key in ("scraped_at", "classified_at", "enriched_at"):
            val = d.get(key)
            if val and str(val) not in ("", "None", "nan"):
                try:
                    d[key] = datetime.fromisoformat(str(val))
                except ValueError:
                    d[key] = None
            else:
                d[key] = None

        # Boolean fields — CSV stores as "True"/"False" strings
        bool_fields_nullable = (
            "filter_pass",
            "service_flag",
            "distributor_flag",
            "ssb_flag",
            "is_subsidiary",
            "is_pe_backed",
            "ownership_pass",
        )
        for key in bool_fields_nullable:
            val = d.get(key)
            if val is None or str(val) in ("", "None", "nan"):
                d[key] = None
            else:
                d[key] = str(val).lower() in ("true", "1", "yes")

        # already_approached defaults False
        val = d.get("already_approached")
        d["already_approached"] = (
            str(val).lower() in ("true", "1", "yes")
            if val not in (None, "", "nan")
            else False
        )

        # Integer fields
        for key in ("ma_count", "services_score", "gesellschafter_age"):
            val = d.get(key)
            if val is not None and str(val) not in ("", "None", "nan"):
                try:
                    d[key] = int(float(str(val)))
                except (ValueError, TypeError):
                    d[key] = None
            else:
                d[key] = None

        # Float fields
        for key in ("revenue_tsd_eur", "gesellschafter_share_pct"):
            val = d.get(key)
            if val is not None and str(val) not in ("", "None", "nan"):
                try:
                    d[key] = float(str(val))
                except (ValueError, TypeError):
                    d[key] = None
            else:
                d[key] = None

        # Remove 'id' — recomputed in __post_init__
        d.pop("id", None)

        valid_fields = {f.name for f in fields(cls) if f.name != "id"}
        return cls(**{k: d[k] for k in valid_fields if k in d})
