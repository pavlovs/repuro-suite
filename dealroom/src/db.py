import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)

SCHEMA_VERSION = 8
_conn = None
_conn_path = None
_conn_lock = threading.RLock()


SEED_DEALS = [
    {
        "code_name": "Octopus",
        "company_name": "HWV Hanseatische Medizin Vertriebs GmbH",
        "domain": "hwv-med.de",
        "deal_stage": "indicative_offer",
        "folder_path": "250611_HWV (Octopus)",
    },
    {
        "code_name": "Cat",
        "company_name": "Medizin & Service GmbH",
        "domain": None,
        "deal_stage": "indicative_offer",
        "folder_path": "250612_Medizin & Service (Cat)",
    },
    {
        "code_name": "Lion",
        "company_name": "Golmed GmbH",
        "domain": "golmed.de",
        "deal_stage": "indicative_offer",
        "folder_path": "250724_Golmed (Lion)",
    },
    {
        "code_name": "Fox",
        "company_name": "Com2Med",
        "domain": "com2med.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "250702_Com2Med (Fox)",
    },
    {
        "code_name": "Wolf",
        "company_name": "KVG Vertriebs GmbH",
        "domain": None,
        "deal_stage": "indicative_offer",
        "folder_path": "251125_KVG (Wolf)",
    },
    {
        "code_name": "Colibri",
        "company_name": "Menke-Med GmbH",
        "domain": "menke-med.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "250828_Menke (Colibri)",
    },
    {
        "code_name": "Falcon",
        "company_name": "KoeWe Medizinbedarf GmbH",
        "domain": "koewe.com",
        "deal_stage": "valuation_rfi",
        "folder_path": "260225_KoeWe (Falcon)",
    },
    {
        "code_name": "Owl",
        "company_name": "RS Radiology Support",
        "domain": "radiology-support.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "251126_RS Radiology (Owl)",
    },
    {
        "code_name": "Eagle",
        "company_name": "Meditec Source",
        "domain": None,
        "deal_stage": "valuation_rfi",
        "folder_path": "251002_Meditec Source (Eagle)",
    },
    {
        "code_name": "Mouse",
        "company_name": "Everto Laborhandel GmbH",
        "domain": "everto-laborhandel.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "260417_Everto Laborhandel (Mouse)",
    },
    {
        "code_name": "Panda",
        "company_name": "IST Medical GmbH",
        "domain": "ist-intensivservice.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "260223_IST Medical (Panda)",
    },
    {
        "code_name": "Blackbird",
        "company_name": "Ugietec",
        "domain": None,
        "deal_stage": "valuation_rfi",
        "folder_path": "260303_ugietec (Blackbird)",
    },
]

# Deals added after the initial seed — migrated idempotently on every get_conn()
MIGRATION_DEALS = [
    {
        "code_name": "Panda",
        "company_name": "IST Medical GmbH",
        "domain": "ist-intensivservice.de",
        "deal_stage": "valuation_rfi",
        "folder_path": "260223_IST Medical (Panda)",
    },
    {
        "code_name": "Blackbird",
        "company_name": "Ugietec",
        "domain": None,
        "deal_stage": "valuation_rfi",
        "folder_path": "260303_ugietec (Blackbird)",
    },
]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS deals (
            id                   TEXT PRIMARY KEY,
            domain               TEXT UNIQUE,
            code_name            TEXT NOT NULL UNIQUE,
            company_name         TEXT,
            deal_stage           TEXT NOT NULL,
            folder_path          TEXT,
            investment_thesis     TEXT,
            seller_motivation    TEXT,
            seller_age_approx    INTEGER,
            seller_profile_notes TEXT,
            stage_entered_at     TEXT,
            last_contact_at      TEXT,
            added_at             TEXT NOT NULL,
            notes                TEXT
        );

        CREATE TABLE IF NOT EXISTS deal_documents (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            code_name       TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            doc_type        TEXT NOT NULL,
            doc_subtype     TEXT,
            fiscal_year     INTEGER,
            file_name       TEXT NOT NULL,
            file_size_kb    INTEGER,
            registered_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deal_data (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            category        TEXT NOT NULL,
            subcategory     TEXT NOT NULL,
            fiscal_year     INTEGER,
            period_type     TEXT,
            key             TEXT NOT NULL,
            value_num       REAL,
            value_text      TEXT,
            unit            TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            confidence      TEXT DEFAULT 'stated',
            is_authoritative INTEGER DEFAULT 0,
            conflict_ids    TEXT,
            conflict_note   TEXT,
            extracted_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deal_valuations (
            id                  TEXT PRIMARY KEY,
            domain              TEXT NOT NULL,
            valuation_date      TEXT NOT NULL,
            offer_round         INTEGER DEFAULT 1,
            ebitda_basis        REAL,
            ebitda_basis_label  TEXT,
            source_model_file   TEXT,
            multiple_low        REAL,
            multiple_mid        REAL,
            multiple_high       REAL,
            ev_low              REAL,
            ev_mid              REAL,
            ev_high             REAL,
            cash_at_closing     REAL,
            rueckbeteiligung    REAL,
            earnout_max         REAL,
            earnout_structure   TEXT,
            seller_counter_ev   REAL,
            seller_counter_notes TEXT,
            seller_stay_value   REAL,
            seller_sell_value   REAL,
            version             INTEGER DEFAULT 1,
            offer_doc_id        TEXT,
            notes               TEXT,
            created_at          TEXT
        );

        CREATE TABLE IF NOT EXISTS deal_questions (
            id                   TEXT PRIMARY KEY,
            domain               TEXT NOT NULL,
            question             TEXT NOT NULL,
            category             TEXT NOT NULL,
            subcategory          TEXT,
            importance           TEXT DEFAULT 'medium',
            source               TEXT DEFAULT 'manual',
            sort_order           INTEGER,
            status               TEXT DEFAULT 'draft',
            answer               TEXT,
            answer_source        TEXT,
            answer_feeds_data_key TEXT,
            sent_at              TEXT,
            answered_at          TEXT,
            created_at           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deal_actions (
            id          TEXT PRIMARY KEY,
            domain      TEXT NOT NULL,
            description TEXT NOT NULL,
            category    TEXT NOT NULL,
            owner       TEXT DEFAULT 'Roman',
            due_date    TEXT,
            status      TEXT DEFAULT 'open',
            priority    TEXT DEFAULT 'medium',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deal_emails (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            intent          TEXT NOT NULL,
            direction       TEXT NOT NULL,
            recipient_name  TEXT,
            recipient_email TEXT,
            subject         TEXT,
            body_draft      TEXT,
            body_final      TEXT,
            status          TEXT DEFAULT 'draft',
            created_at      TEXT,
            sent_at         TEXT
        );

        CREATE TABLE IF NOT EXISTS deal_granola (
            id                  TEXT PRIMARY KEY,
            domain              TEXT NOT NULL,
            granola_meeting_id  TEXT NOT NULL,
            meeting_title       TEXT,
            meeting_date        TEXT,
            participants        TEXT,
            summary             TEXT,
            action_items        TEXT,
            key_topics          TEXT,
            data_points_json    TEXT,
            synced_at           TEXT
        );

        CREATE TABLE IF NOT EXISTS deal_notes (
            id          TEXT PRIMARY KEY,
            domain      TEXT NOT NULL,
            note        TEXT NOT NULL,
            author      TEXT DEFAULT 'Roman',
            created_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS deal_model_params (
            id                      TEXT PRIMARY KEY,
            domain                  TEXT NOT NULL,
            scenario_name           TEXT NOT NULL DEFAULT 'base',

            -- Entities (multi-company consolidation)
            entities_json           TEXT,

            -- Adjustment items (raw → adjusted P&L)
            adj_items_json          TEXT,

            -- GF salary adjustment (formulaic)
            gf_old_salary_monthly_k  REAL,
            gf_new_base_k            REAL,
            gf_tantieme_k            REAL,
            gf_sozialabgaben_pct     REAL DEFAULT 0.18,
            gf_benefit_factor        REAL DEFAULT 1.2,

            -- EBITDA / EBIT basis
            ebitda_basis_override    REAL,
            ebit_basis_override      REAL,
            ebitda_basis_label       TEXT,
            da_amount                REAL,

            -- Valuation
            multiple                 REAL,
            net_debt                 REAL,
            permitted_leakage        REAL DEFAULT 0,

            -- Deal structure (absolute EUR_K)
            cash_at_closing          REAL,
            vendor_loan              REAL,
            earnout_anticipated      REAL,

            -- Earn-out matrix (variable tiers)
            earnout_ebit_anchor      REAL,
            earnout_step             REAL DEFAULT 25,
            earnout_tiers_json       TEXT,

            -- Pro-forma EBIT bridge
            proforma_gf_salary_k     REAL,
            proforma_nebenkosten_pct REAL DEFAULT 0.17,

            -- Net debt detail
            net_debt_items_json      TEXT,

            -- Projection
            projection_revenue       REAL,
            projection_growth        REAL,

            -- Comments per row
            comments_json            TEXT,

            -- Metadata
            created_at               TEXT NOT NULL,
            updated_at               TEXT,
            UNIQUE(domain, scenario_name)
        );
        """
    )

    # Seed only if table is empty
    row = conn.execute("SELECT COUNT(*) FROM deals").fetchone()
    if row[0] == 0:
        now = datetime.now(timezone.utc).isoformat()
        for deal in SEED_DEALS:
            conn.execute(
                """
                INSERT INTO deals (id, domain, code_name, company_name, deal_stage, folder_path, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    deal["domain"],
                    deal["code_name"],
                    deal["company_name"],
                    deal["deal_stage"],
                    deal["folder_path"],
                    now,
                ),
            )
        conn.commit()


def migrate_add_missing_deals(conn: sqlite3.Connection) -> None:
    """Idempotent: insert deals added after the original DR-M1 seed."""
    now = datetime.now(timezone.utc).isoformat()
    for deal in MIGRATION_DEALS:
        conn.execute(
            """
            INSERT OR IGNORE INTO deals
            (id, domain, code_name, company_name, deal_stage, folder_path, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                deal["domain"],
                deal["code_name"],
                deal["company_name"],
                deal["deal_stage"],
                deal["folder_path"],
                now,
            ),
        )
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after initial schema creation. Idempotent."""
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(deal_questions)").fetchall()
    }
    if "answer_source" not in existing:
        conn.execute("ALTER TABLE deal_questions ADD COLUMN answer_source TEXT")
        conn.commit()


# ---------------------------------------------------------------------------
# Stage taxonomy mapping (old → new)
# ---------------------------------------------------------------------------
STAGE_MIGRATION_MAP = {
    "financials_received": "valuation_rfi",
    "offer_preparation": "valuation_rfi",
    "offer_negotiation": "indicative_offer",
    "offer_sent": "indicative_offer",
    "nda_exchange": "meeting_concluded",
    "valuation": "valuation_rfi",
    "offer": "indicative_offer",
    "loi": "loi_signed",
}

VALID_STAGES = frozenset(
    [
        "meeting_concluded",
        "valuation_rfi",
        "indicative_offer",
        "loi_signed",
        "due_diligence",
        "contract_negotiation",
        "closed",
        "on_hold",
        "dead",
    ]
)

# ---------------------------------------------------------------------------
# Stage gate configuration
# ---------------------------------------------------------------------------
STAGE_GATES = {
    "meeting_concluded_to_valuation_rfi": {
        "documents": [("nda", "signed")],
        "manual": [],
    },
    "valuation_rfi_to_indicative_offer": {
        "documents": [("financial_model", "approved"), ("onepager", "approved")],
        "manual": ["ic_go_decision"],
    },
    "offer_to_loi": {
        "documents": [("indicative_offer", "sent")],
        "manual": ["terms_agreed"],
    },
    "loi_to_due_diligence": {
        "documents": [("loi", "signed")],
        "manual": [],
    },
    "due_diligence_to_closed": {
        "documents": [("dd_report", "approved")],
        "manual": ["ic_go_decision"],
    },
}

# ---------------------------------------------------------------------------
# Document category → type mapping + status progressions
# ---------------------------------------------------------------------------
DOC_CATEGORIES = {
    "internal": {
        "types": [
            "financial_model",
            "onepager",
            "databook",
            "commercial_dd",
            "integration_plan",
        ],
        "progression": ["draft", "reviewed", "approved"],
    },
    "bilateral": {
        "types": [
            "nda",
            "loi",
            "spa",
            "indicative_offer",
            "employment_agreement",
            "escrow_agreement",
        ],
        "progression": ["draft", "sent", "negotiation", "signed"],
    },
    "rfi": {
        "types": ["rfi"],
        "progression": ["draft", "sent", "partially_answered", "answered"],
    },
}

# ---------------------------------------------------------------------------
# Default scorecard thresholds
# ---------------------------------------------------------------------------
DEFAULT_SCORECARD = [
    (
        "revenue_cagr_3y",
        "Revenue CAGR (3y)",
        "growth",
        10.0,
        5.0,
        "higher_is_better",
        "PCT",
        "deal_financials",
        "line_item='gesamtleistung', compute CAGR 3y",
        1,
    ),
    (
        "ebitda_margin",
        "EBITDA Margin (adj.)",
        "profitability",
        15.0,
        10.0,
        "higher_is_better",
        "PCT",
        "deal_financials",
        "ebitda_adj / gesamtleistung",
        2,
    ),
    (
        "ebitda_absolute_k",
        "EBITDA (adj., EUR K)",
        "profitability",
        500.0,
        300.0,
        "higher_is_better",
        "EUR_K",
        "deal_financials",
        "line_item='ebitda_adj'",
        3,
    ),
    (
        "recurring_pct",
        "Recurring Revenue %",
        "quality",
        30.0,
        10.0,
        "higher_is_better",
        "PCT",
        "deal_commercial",
        "metric='recurring_pct'",
        4,
    ),
    (
        "top10_concentration",
        "Top 10 Customer Share",
        "risk",
        40.0,
        60.0,
        "lower_is_better",
        "PCT",
        "deal_commercial",
        "metric='top10_share_pct'",
        5,
    ),
    (
        "top3_concentration",
        "Top 3 Customer Share",
        "risk",
        25.0,
        40.0,
        "lower_is_better",
        "PCT",
        "deal_commercial",
        "metric='top3_share_pct'",
        6,
    ),
    (
        "supplier_concentration",
        "Top 3 Supplier Share",
        "risk",
        30.0,
        50.0,
        "lower_is_better",
        "PCT",
        "deal_commercial",
        "metric='top3_supplier_share_pct'",
        7,
    ),
    (
        "ev_ebitda_multiple",
        "EV/EBITDA Multiple",
        "valuation",
        5.0,
        7.0,
        "lower_is_better",
        "x",
        "deal_valuations",
        "ev_mid / ebitda_basis",
        8,
    ),
    (
        "headcount",
        "Headcount",
        "quality",
        15.0,
        10.0,
        "higher_is_better",
        "COUNT",
        "deal_commercial",
        "metric='headcount'",
        9,
    ),
    (
        "backlog_coverage",
        "Backlog / Revenue",
        "quality",
        1.0,
        0.5,
        "higher_is_better",
        "x",
        "deal_commercial",
        "backlog_total_k / revenue",
        10,
    ),
    (
        "customer_churn",
        "Customer Churn Rate",
        "risk",
        10.0,
        20.0,
        "lower_is_better",
        "PCT",
        "deal_commercial",
        "metric='customer_churn_pct'",
        11,
    ),
]


def _migrate_schema_v2(conn: sqlite3.Connection) -> None:
    """Schema v2: normalized tables, stage redesign, doc status, scorecard.

    Fully idempotent — safe to call on every connection.
    """
    # ------------------------------------------------------------------
    # 1. New tables (CREATE IF NOT EXISTS — additive, zero risk)
    # ------------------------------------------------------------------
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deal_financials (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            statement       TEXT NOT NULL,
            line_item       TEXT NOT NULL,
            konto_nr        TEXT,
            fiscal_year     INTEGER,
            period_type     TEXT DEFAULT 'annual',
            period          TEXT,
            value_k         REAL,
            value_raw       REAL,
            is_adjusted     INTEGER DEFAULT 0,
            adjustment_note TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            confidence      TEXT DEFAULT 'stated',
            is_authoritative INTEGER DEFAULT 0,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_df_domain_stmt ON deal_financials(domain, statement, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_df_domain_item ON deal_financials(domain, line_item, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_df_konto ON deal_financials(domain, konto_nr, fiscal_year);

        CREATE TABLE IF NOT EXISTS deal_commercial (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            category        TEXT NOT NULL,
            metric          TEXT NOT NULL,
            fiscal_year     INTEGER,
            value_num       REAL,
            value_text      TEXT,
            unit            TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            confidence      TEXT DEFAULT 'stated',
            is_authoritative INTEGER DEFAULT 0,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dcom_domain ON deal_commercial(domain, category, metric, fiscal_year);

        CREATE TABLE IF NOT EXISTS deal_customers (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            customer_name   TEXT NOT NULL,
            customer_id     TEXT,
            fiscal_year     INTEGER NOT NULL,
            revenue_k       REAL,
            revenue_pct     REAL,
            rank            INTEGER,
            cohort          TEXT,
            customer_type   TEXT,
            specialty       TEXT,
            relationship_start_year INTEGER,
            has_contract    INTEGER,
            contract_end    TEXT,
            change_of_control INTEGER,
            litigation_flag INTEGER DEFAULT 0,
            notes           TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dc_domain_year ON deal_customers(domain, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_dc_domain_rank ON deal_customers(domain, fiscal_year, rank);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dc_unique ON deal_customers(domain, customer_name, fiscal_year);

        CREATE TABLE IF NOT EXISTS deal_backlog (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            project_name    TEXT,
            client_name     TEXT,
            location        TEXT,
            service_type    TEXT,
            value_k         REAL,
            execution_year  TEXT,
            status          TEXT,
            risk_flag       TEXT,
            risk_note       TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dbl_domain ON deal_backlog(domain);

        CREATE TABLE IF NOT EXISTS deal_employees (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            employee_id     TEXT,
            role            TEXT,
            department      TEXT,
            qualification   TEXT,
            employment_type TEXT,
            hours_per_week  REAL,
            salary_monthly  REAL,
            salary_annual_k REAL,
            age_bucket      TEXT,
            tenure_years    REAL,
            contract_type   TEXT,
            is_key_person   INTEGER DEFAULT 0,
            notes           TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_demp_domain ON deal_employees(domain);

        CREATE TABLE IF NOT EXISTS deal_suppliers (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            supplier_name   TEXT NOT NULL,
            fiscal_year     INTEGER,
            cost_k          REAL,
            cost_pct        REAL,
            rank            INTEGER,
            product_group   TEXT,
            exclusivity     INTEGER,
            relationship_start_year INTEGER,
            price_increase_notes TEXT,
            litigation_flag INTEGER DEFAULT 0,
            notes           TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dsup_domain ON deal_suppliers(domain, fiscal_year);

        CREATE TABLE IF NOT EXISTS deal_competitors (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            competitor_name TEXT NOT NULL,
            rank            INTEGER,
            estimated_revenue_k REAL,
            region          TEXT,
            segment_overlap TEXT,
            differentiation TEXT,
            source          TEXT NOT NULL,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dcomp_domain ON deal_competitors(domain);

        CREATE TABLE IF NOT EXISTS deal_contacts (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            role            TEXT NOT NULL,
            company         TEXT,
            email           TEXT,
            phone           TEXT,
            salutation      TEXT,
            is_primary      INTEGER DEFAULT 0,
            notes           TEXT,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dcon_domain ON deal_contacts(domain, role);

        CREATE TABLE IF NOT EXISTS deal_manual_gates (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            gate_type       TEXT NOT NULL,
            stage_transition TEXT NOT NULL,
            decided_by      TEXT,
            decided_at      TEXT,
            decision        TEXT,
            notes           TEXT,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dmg_domain ON deal_manual_gates(domain, gate_type);

        CREATE TABLE IF NOT EXISTS deal_dd_items (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            category        TEXT NOT NULL,
            subcategory     TEXT,
            description     TEXT NOT NULL,
            datenanfrage_ref TEXT,
            status          TEXT DEFAULT 'open',
            risk_level      TEXT,
            risk_note       TEXT,
            value_k         REAL,
            doc_id          TEXT,
            advisor         TEXT,
            notes           TEXT,
            source          TEXT NOT NULL,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ddi_domain ON deal_dd_items(domain, category, status);

        CREATE TABLE IF NOT EXISTS deal_meetings (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            meeting_type    TEXT NOT NULL,
            meeting_date    TEXT NOT NULL,
            participants    TEXT,
            location        TEXT,
            summary         TEXT,
            key_topics      TEXT,
            action_items    TEXT,
            data_points_json TEXT,
            decisions       TEXT,
            granola_meeting_id TEXT,
            transcript_url  TEXT,
            created_by      TEXT DEFAULT 'manual',
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dm_domain ON deal_meetings(domain, meeting_date DESC);

        CREATE TABLE IF NOT EXISTS deal_scorecard_config (
            id              TEXT PRIMARY KEY,
            metric_key      TEXT NOT NULL UNIQUE,
            label           TEXT NOT NULL,
            category        TEXT NOT NULL,
            threshold_green REAL,
            threshold_yellow REAL,
            direction       TEXT DEFAULT 'higher_is_better',
            unit            TEXT,
            source_table    TEXT NOT NULL,
            source_query_hint TEXT,
            sort_order      INTEGER,
            is_active       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS deal_scorecard_results (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            metric_key      TEXT NOT NULL,
            value           REAL,
            rating          TEXT,
            fiscal_year     INTEGER,
            notes           TEXT,
            computed_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dsr_domain ON deal_scorecard_results(domain, metric_key);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dsr_unique ON deal_scorecard_results(domain, metric_key, fiscal_year);
    """)

    # ------------------------------------------------------------------
    # 2. ALTER existing tables — add new columns (idempotent)
    # ------------------------------------------------------------------
    def _add_col(table: str, col: str, col_def: str) -> None:
        cols = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

    # deals — stage redesign + profile columns
    _add_col("deals", "deal_status", "TEXT DEFAULT 'on_track'")
    _add_col("deals", "status_note", "TEXT")
    _add_col("deals", "previous_stage", "TEXT")
    _add_col("deals", "sector", "TEXT")
    _add_col("deals", "location", "TEXT")
    _add_col("deals", "founded_year", "INTEGER")
    _add_col("deals", "exclusivity_start", "TEXT")
    _add_col("deals", "exclusivity_end", "TEXT")

    # deal_documents — doc status tracking
    _add_col("deal_documents", "doc_status", "TEXT DEFAULT 'draft'")
    _add_col("deal_documents", "doc_status_note", "TEXT")
    _add_col("deal_documents", "previous_doc_status", "TEXT")

    # deal_emails — enhanced threading + contacts
    _add_col("deal_emails", "thread_id", "TEXT")
    _add_col("deal_emails", "in_reply_to", "TEXT")
    _add_col("deal_emails", "contact_id", "TEXT")
    _add_col("deal_emails", "sender_name", "TEXT")
    _add_col("deal_emails", "sender_email", "TEXT")
    _add_col("deal_emails", "account", "TEXT")
    _add_col("deal_emails", "deal_stage_at_send", "TEXT")
    _add_col("deal_emails", "received_at", "TEXT")

    conn.commit()

    # ------------------------------------------------------------------
    # 3. Stage migration — remap old taxonomy to new
    # ------------------------------------------------------------------
    for old_stage, new_stage in STAGE_MIGRATION_MAP.items():
        conn.execute(
            "UPDATE deals SET deal_stage = ? WHERE deal_stage = ?",
            (new_stage, old_stage),
        )

    # Backfill stage_entered_at from added_at where NULL
    conn.execute(
        "UPDATE deals SET stage_entered_at = added_at WHERE stage_entered_at IS NULL"
    )
    conn.commit()

    # ------------------------------------------------------------------
    # 4. Seed scorecard config (idempotent via INSERT OR IGNORE)
    # ------------------------------------------------------------------
    for sc in DEFAULT_SCORECARD:
        conn.execute(
            """INSERT OR IGNORE INTO deal_scorecard_config
               (id, metric_key, label, category, threshold_green, threshold_yellow,
                direction, unit, source_table, source_query_hint, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), *sc),
        )
    conn.commit()

    # ------------------------------------------------------------------
    # 5. Archive deal_granola → deal_granola_v1_archive (idempotent)
    # ------------------------------------------------------------------
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "deal_granola" in tables and "deal_granola_v1_archive" not in tables:
        conn.execute("ALTER TABLE deal_granola RENAME TO deal_granola_v1_archive")
        conn.commit()

    # ------------------------------------------------------------------
    # 6. Migrate deal_data → normalized tables (idempotent)
    # ------------------------------------------------------------------
    _migrate_deal_data(conn)

    log.info("Schema v2 migration complete.")


def _migrate_schema_v3(conn: sqlite3.Connection) -> None:
    """Schema v3: deal_products table, deal_notes enrichment, extraction_config.

    Fully idempotent — safe to call on every connection.
    Spec refs: SPEC-DR-COMMERCIAL §4, SPEC-DR-GATHER §4.
    """
    # ------------------------------------------------------------------
    # 1. New table: deal_products (SPEC-DR-COMMERCIAL §4)
    # ------------------------------------------------------------------
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deal_products (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            product_name    TEXT NOT NULL,
            category        TEXT,
            subcategory     TEXT,
            fiscal_year     INTEGER NOT NULL,
            revenue_k       REAL,
            cost_k          REAL,
            gross_profit_k  REAL,
            margin_pct      REAL,
            revenue_share_pct REAL,
            units_sold      INTEGER,
            is_recurring    INTEGER DEFAULT 0,
            notes           TEXT,
            source          TEXT,
            source_file_id  TEXT,
            confidence      TEXT DEFAULT 'stated',
            is_authoritative INTEGER DEFAULT 0,
            extracted_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_dprod_domain_year
            ON deal_products(domain, fiscal_year);
    """)

    # ------------------------------------------------------------------
    # 2. ALTER deal_notes — add category/source/confidence columns
    #    (SPEC-DR-GATHER §4)
    # ------------------------------------------------------------------
    def _add_col(table: str, col: str, col_def: str) -> None:
        cols = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

    _add_col("deal_notes", "category", "TEXT")
    _add_col("deal_notes", "source", "TEXT")
    _add_col("deal_notes", "source_file_id", "TEXT")
    _add_col("deal_notes", "importance", "TEXT DEFAULT 'medium'")
    _add_col("deal_notes", "confidence", "TEXT DEFAULT 'stated'")
    _add_col("deal_notes", "fiscal_year", "INTEGER")
    _add_col("deal_notes", "is_authoritative", "INTEGER DEFAULT 0")
    _add_col("deal_notes", "extracted_at", "TEXT")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dnotes_domain_cat "
        "ON deal_notes(domain, category)"
    )

    # ------------------------------------------------------------------
    # 3. New table: deal_backlog (SPEC-DR-COMMERCIAL §4 — Phase 2)
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deal_backlog (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            customer_name   TEXT,
            project_description TEXT,
            location        TEXT,
            execution_year  TEXT,
            order_value_k   REAL,
            margin_pct      REAL,
            status          TEXT,
            fiscal_year     INTEGER,
            source          TEXT,
            source_file_id  TEXT,
            confidence      TEXT DEFAULT 'stated',
            is_authoritative INTEGER DEFAULT 0,
            extracted_at    TEXT
        )
    """)
    _add_col("deal_backlog", "fiscal_year", "INTEGER")
    _add_col("deal_backlog", "customer_name", "TEXT")
    _add_col("deal_backlog", "project_description", "TEXT")
    _add_col("deal_backlog", "order_value_k", "REAL")
    _add_col("deal_backlog", "margin_pct", "REAL")
    _add_col("deal_backlog", "confidence", "TEXT DEFAULT 'stated'")
    _add_col("deal_backlog", "is_authoritative", "INTEGER DEFAULT 0")
    backlog_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(deal_backlog)").fetchall()
    }
    if "fiscal_year" in backlog_cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dbacklog_domain_year "
            "ON deal_backlog(domain, fiscal_year)"
        )

    # ------------------------------------------------------------------
    # 4. ALTER deal_documents — extraction_config for cached column
    #    mappings (SPEC-DR-COMMERCIAL §2, §5)
    # ------------------------------------------------------------------
    _add_col("deal_documents", "extraction_config", "TEXT")

    conn.commit()
    log.info("Schema v3 migration complete.")


def _migrate_schema_v4(conn: sqlite3.Connection) -> None:
    """Schema v4: projection columns on deals, entity column on deal_financials.

    Fully idempotent — safe to call on every connection.
    Spec refs: SPEC-FINANCIALS-TAB §7.
    """

    def _add_col(table: str, col: str, col_def: str) -> None:
        cols = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

    # New columns on deals table
    _add_col("deals", "proj_topline_growth_pct", "REAL")
    _add_col("deals", "proj_gm_pct", "REAL")
    _add_col("deals", "proj_ebitda_margin_pct", "REAL")
    _add_col("deals", "pnl_row_comments", "TEXT")

    # New column on deal_financials table
    _add_col("deal_financials", "entity", "TEXT DEFAULT 'consolidated'")

    conn.commit()
    log.info("Schema v4 migration complete.")


def _migrate_schema_v5(conn: sqlite3.Connection) -> None:
    """Schema v5: deal_invoices fact table + confidence on deal_dd_items.

    Invoice-level transaction data is the atomic fact table behind the CDD
    databook — segment revenue, quarterly GM, and drill-downs are computed
    from it instead of stored as frozen aggregates.
    Fully idempotent — safe to call on every connection.
    Spec refs: PLAN-DR-M25-CDD.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deal_invoices (
            id              TEXT PRIMARY KEY,
            domain          TEXT NOT NULL,
            invoice_no      TEXT,
            status          TEXT,
            net_amount      REAL,
            gross_profit    REAL,
            segment         TEXT,
            model           TEXT,
            serial_no       TEXT,
            art             TEXT,
            invoice_date    TEXT,
            fiscal_year     INTEGER,
            quarter         INTEGER,
            customer_ref    TEXT,
            source          TEXT NOT NULL,
            source_file_id  TEXT,
            extracted_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dinv_domain_year
            ON deal_invoices(domain, fiscal_year, quarter);
        CREATE INDEX IF NOT EXISTS idx_dinv_domain_segment
            ON deal_invoices(domain, segment, fiscal_year);
    """)

    def _add_col(table: str, col: str, col_def: str) -> None:
        cols = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

    _add_col("deal_dd_items", "confidence", "TEXT")
    _add_col("deal_customers", "churn_reason", "TEXT")

    conn.commit()
    log.info("Schema v5 migration complete.")


def _migrate_deal_data(conn: sqlite3.Connection) -> None:
    """One-time migration: deal_data EAV → deal_financials + deal_commercial + deal_customers.

    Idempotent: skips if deal_data_v1_archive already exists or deal_data is empty.
    """
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "deal_data_v1_archive" in tables:
        return
    if "deal_data" not in tables:
        return

    count = conn.execute("SELECT COUNT(*) FROM deal_data").fetchone()[0]
    if count == 0:
        return

    now = datetime.now(timezone.utc).isoformat()

    # --- Financial rows → deal_financials ---
    financial_cats = [
        ("financial", "pnl", "pnl", "annual", 0),
        ("financial", "balance", "balance", "annual", 0),
        ("financial", "ltm", "pnl", "ltm", 0),
        ("financial", "adjustments", "adjustments", "annual", 0),
        ("valuation_input", "pnl_adj", "pnl", "annual", 1),
        ("valuation_input", "bewertung", "bewertung", "annual", 1),
    ]
    for cat, subcat, stmt, period_type, is_adj in financial_cats:
        rows = conn.execute(
            """SELECT id, domain, key, fiscal_year, value_num, value_text, unit,
                      source, source_file_id, confidence, is_authoritative, extracted_at
               FROM deal_data WHERE category = ? AND subcategory = ?""",
            (cat, subcat),
        ).fetchall()
        for r in rows:
            conn.execute(
                """INSERT OR IGNORE INTO deal_financials
                   (id, domain, statement, line_item, fiscal_year, period_type,
                    value_k, is_adjusted, source, source_file_id, confidence,
                    is_authoritative, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["id"],
                    r["domain"],
                    stmt,
                    r["key"],
                    r["fiscal_year"],
                    period_type,
                    r["value_num"],
                    is_adj,
                    r["source"],
                    r["source_file_id"],
                    r["confidence"],
                    r["is_authoritative"],
                    r["extracted_at"],
                ),
            )

    # --- Customer analysis/top10 → deal_customers ---
    cust_rows = conn.execute(
        """SELECT id, domain, key, fiscal_year, value_num, value_text,
                  source, source_file_id, extracted_at
           FROM deal_data WHERE category = 'customer_analysis' AND subcategory = 'top10'"""
    ).fetchall()
    for r in cust_rows:
        conn.execute(
            """INSERT OR IGNORE INTO deal_customers
               (id, domain, customer_name, fiscal_year, revenue_k,
                source, source_file_id, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["id"],
                r["domain"],
                r["key"],
                r["fiscal_year"] or 2024,
                r["value_num"],
                r["source"],
                r["source_file_id"],
                r["extracted_at"],
            ),
        )

    # --- Customer analysis/metrics → deal_commercial ---
    metric_rows = conn.execute(
        """SELECT id, domain, key, fiscal_year, value_num, value_text, unit,
                  source, source_file_id, confidence, is_authoritative, extracted_at
           FROM deal_data WHERE category = 'customer_analysis' AND subcategory = 'metrics'"""
    ).fetchall()
    for r in metric_rows:
        conn.execute(
            """INSERT OR IGNORE INTO deal_commercial
               (id, domain, category, metric, fiscal_year, value_num, value_text, unit,
                source, source_file_id, confidence, is_authoritative, extracted_at)
               VALUES (?, ?, 'customers', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["id"],
                r["domain"],
                r["key"],
                r["fiscal_year"],
                r["value_num"],
                r["value_text"],
                r["unit"],
                r["source"],
                r["source_file_id"],
                r["confidence"],
                r["is_authoritative"],
                r["extracted_at"],
            ),
        )

    # --- commercial/* → deal_commercial ---
    comm_rows = conn.execute(
        """SELECT id, domain, subcategory, key, fiscal_year, value_num, value_text, unit,
                  source, source_file_id, confidence, is_authoritative, extracted_at
           FROM deal_data WHERE category = 'commercial'"""
    ).fetchall()
    for r in comm_rows:
        cat_val = r["subcategory"] or "operational"
        conn.execute(
            """INSERT OR IGNORE INTO deal_commercial
               (id, domain, category, metric, fiscal_year, value_num, value_text, unit,
                source, source_file_id, confidence, is_authoritative, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["id"],
                r["domain"],
                cat_val,
                r["key"],
                r["fiscal_year"],
                r["value_num"],
                r["value_text"],
                r["unit"],
                r["source"],
                r["source_file_id"],
                r["confidence"],
                r["is_authoritative"],
                r["extracted_at"],
            ),
        )

    conn.commit()

    # Archive original table
    conn.execute("ALTER TABLE deal_data RENAME TO deal_data_v1_archive")
    conn.commit()
    log.info(
        "Migrated %d deal_data rows → deal_financials + deal_customers + deal_commercial",
        count,
    )


_warned_this_session: set[str] = set()


def _check_other_agent_active(db_path: Path) -> None:
    """Warn once per session if the other agent is active."""
    active_dir = db_path.resolve().parent
    for _ in range(4):
        active_dir = active_dir.parent
        candidate = active_dir / ".active"
        if candidate.is_dir():
            break
    else:
        return
    my_user = os.environ.get("USERNAME", os.environ.get("USER", "")).lower()
    db_name = db_path.name
    for md in candidate.glob("*.md"):
        agent_name = md.stem.lower()
        if agent_name == my_user:
            continue
        warn_key = f"{agent_name}:{db_name}"
        if warn_key in _warned_this_session:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        status_m = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
        if not status_m or status_m.group(1) != "active":
            continue
        if db_name in text or "dealroom" in text.lower():
            _warned_this_session.add(warn_key)
            log.warning(
                "OTHER AGENT ACTIVE: %s may be using %s -- coordinate or wait.",
                agent_name.title(),
                db_name,
            )
            print(
                f"WARNING: {agent_name.title()}'s agent is active and may be using {db_name}. "
                f"Risk of OneDrive conflict."
            )


def _migrate_mouse_to_everto(conn: sqlite3.Connection) -> None:
    """Rename Mouse from Coretec-Service to Everto Laborhandel. Idempotent."""
    row = conn.execute(
        "SELECT company_name FROM deals WHERE code_name = 'Mouse'"
    ).fetchone()
    if row and row["company_name"] == "Coretec-Service GmbH":
        conn.execute(
            """UPDATE deals SET company_name = 'Everto Laborhandel GmbH',
               domain = 'everto-laborhandel.de',
               folder_path = '260417_Everto Laborhandel (Mouse)'
               WHERE code_name = 'Mouse'""",
        )
        conn.commit()
        log.info("Migrated Mouse from Coretec-Service to Everto Laborhandel.")


def get_conn() -> sqlite3.Connection:
    """Singleton connection with lazy migration (skip if already at SCHEMA_VERSION)."""
    global _conn, _conn_path
    with _conn_lock:
        path = str(settings.DB_PATH)
        if _conn is not None and _conn_path == path:
            return _conn

        if _conn is not None:
            _conn.close()

        if os.environ.get("DEALROOM_REQUIRE_DB") and not os.path.exists(path):
            raise RuntimeError(
                f"DEALROOM_REQUIRE_DB set but DB file missing: {path!r}. "
                "Refusing to create/seed an empty database (unset DEALROOM_REQUIRE_DB for local dev)."
            )
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _check_other_agent_active(settings.DB_PATH)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        if os.environ.get("FLY_APP_NAME"):
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        allex_path = settings.ALLEX_PIPELINE_DB
        if allex_path.exists():
            if os.name != "nt":
                uri = "file:" + str(allex_path) + "?mode=ro"
                conn.execute("ATTACH DATABASE ? AS allex", (uri,))
            else:
                conn.execute("ATTACH DATABASE ? AS allex", (str(allex_path),))

        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        if ver < SCHEMA_VERSION:
            init_db(conn)
            migrate_add_missing_deals(conn)
            _migrate_schema(conn)
            _migrate_schema_v2(conn)
            _migrate_schema_v3(conn)
            _migrate_schema_v4(conn)
            _migrate_schema_v5(conn)
            _migrate_mouse_to_everto(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()

        _conn, _conn_path = conn, path
        return conn


def close_conn():
    """Drop the singleton so the next get_conn() reconnects."""
    global _conn, _conn_path
    with _conn_lock:
        if _conn is not None:
            _conn.close()
        _conn, _conn_path = None, None


def resolve_folder(code_name: str, conn=None) -> "Path | None":
    """Resolve deal folder: prefer DB folder_path, then scan DEALS_DIR."""
    deals_dir = settings.DEALS_DIR
    if not deals_dir.exists():
        return None
    if conn is None:
        conn = get_conn()
    row = conn.execute(
        "SELECT folder_path FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if row and row["folder_path"]:
        candidate = deals_dir / row["folder_path"]
        if candidate.is_dir():
            return candidate
    target = f"({code_name})"
    for child in sorted(deals_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if child.is_dir() and target in child.name:
            return child
    return None
