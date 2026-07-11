-- ============================================================================
-- DEALROOM v2 — schema (SPEC-DEALROOM-V2.md rev 2 §9)
-- Clean rebuild. domain = universal FK to ALLEX pipeline.db; code_name carried
-- on v2-native tables because three deals legitimately have NULL domain.
-- Kill list §10: deal_emails / deal_meetings / deal_granola(+archive) /
-- deal_actions / deal_notes / deal_manual_gates / deal_contacts / deal_data /
-- deal_data_v1_archive / deal_scorecard_results are NOT part of this schema.
-- ============================================================================

PRAGMA user_version = 100;

-- ---------------------------------------------------------------- core -----

CREATE TABLE deals (
    id                   TEXT PRIMARY KEY,
    domain               TEXT UNIQUE,
    code_name            TEXT NOT NULL UNIQUE,
    company_name         TEXT,
    deal_stage           TEXT NOT NULL,
    folder_path          TEXT,
    investment_thesis    TEXT,
    seller_motivation    TEXT,
    seller_age_approx    INTEGER,
    seller_profile_notes TEXT,
    stage_entered_at     TEXT,
    added_at             TEXT NOT NULL,
    notes                TEXT,
    description          TEXT,
    strategic_fit        TEXT,
    rev_m_override       REAL,
    ebitda_m_override    REAL,
    employees_override   INTEGER,
    ev_m_override        REAL,
    multiple_override    REAL,
    status_override      TEXT,
    ev_m_note            TEXT,
    multiple_note        TEXT,
    customer_summary     TEXT,
    deal_status          TEXT DEFAULT 'on_track',
    status_note          TEXT,
    sector               TEXT,
    location             TEXT,
    founded_year         INTEGER,
    exclusivity_start    TEXT,
    exclusivity_end      TEXT,
    onepager_title       TEXT,
    onepager_q1          TEXT,
    onepager_q3          TEXT,
    onepager_q4          TEXT,
    onepager_footnote    TEXT,
    onepager_generated_at TEXT,
    onepager_edited_at   TEXT,
    onepager_q1_approved INTEGER DEFAULT 0,
    onepager_q3_approved INTEGER DEFAULT 0,
    onepager_q4_approved INTEGER DEFAULT 0,
    onepager_headline    TEXT,
    bp_2026_rev_k        REAL,
    bp_2026_ebitda_k     REAL,
    maxeo_2026_ebitda_k  REAL,
    proj_topline_growth_pct REAL,
    proj_gm_pct          REAL,
    proj_ebitda_margin_pct REAL,
    pnl_row_comments     TEXT,
    bm_segments_comment  TEXT,
    bm_margin_comment    TEXT,
    bm_revquality_comment TEXT,
    bm_tieout_comment    TEXT,
    bm_description       TEXT,
    thesis_scorecard_comment TEXT,
    thesis_swot_comment  TEXT,
    thesis_rationale     TEXT
);

CREATE TABLE deal_stage_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT,
    code_name   TEXT NOT NULL,
    from_stage  TEXT,
    to_stage    TEXT NOT NULL,
    changed_at  TEXT NOT NULL,
    changed_by  TEXT NOT NULL DEFAULT 'system',
    evidence    TEXT
);
CREATE INDEX idx_dsh_code ON deal_stage_history(code_name, changed_at);

CREATE TABLE deal_terms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT,
    code_name   TEXT NOT NULL,
    term_key    TEXT NOT NULL,
    label       TEXT NOT NULL,
    value_num   REAL,
    value_text  TEXT,
    unit        TEXT,
    status      TEXT NOT NULL CHECK(status IN ('proposed','countered','agreed','locked','superseded')),
    source_doc  TEXT NOT NULL,
    note        TEXT,
    changed_at  TEXT NOT NULL,
    changed_by  TEXT NOT NULL DEFAULT 'migration',
    superseded_by_id INTEGER REFERENCES deal_terms(id)
);
CREATE INDEX idx_dt_code ON deal_terms(code_name, term_key, status);

CREATE TABLE deal_milestones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT,
    code_name   TEXT NOT NULL,
    milestone   TEXT NOT NULL,
    due_date    TEXT,
    owner       TEXT NOT NULL DEFAULT 'Repuro',
    status      TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','missed','dropped')),
    source_doc  TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL,
    done_at     TEXT
);
CREATE INDEX idx_dms_code ON deal_milestones(code_name, due_date);

-- Absorbs v1 deal_documents (spec §5). artifact_type = spec set plus the v1
-- doc_types that carry real granularity (financials_raw, commercial_raw,
-- meeting, repuro_internal) — collapsing them to 'other' would lose data.
CREATE TABLE deal_artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT,
    code_name       TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    artifact_subtype TEXT,
    version         INTEGER,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_mtime      TEXT,
    file_date       TEXT,
    file_size_kb    INTEGER,
    fiscal_year     INTEGER,
    dataroom_section TEXT,
    status          TEXT NOT NULL DEFAULT 'current' CHECK(status IN ('current','superseded','final','stale','draft')),
    checks_json     TEXT,
    supersedes_id   INTEGER REFERENCES deal_artifacts(id),
    registered_at   TEXT NOT NULL,
    last_seen_at    TEXT,
    note            TEXT,
    UNIQUE(code_name, file_path)
);
CREATE INDEX idx_da_code_type ON deal_artifacts(code_name, artifact_type, status);

CREATE TABLE freshness_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT
);

CREATE TABLE dataroom_scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT,
    code_name       TEXT NOT NULL,
    section         TEXT NOT NULL,
    section_name    TEXT,
    scanned_at      TEXT NOT NULL,
    file_count      INTEGER NOT NULL DEFAULT 0,
    newest_file_date TEXT,
    newest_file_name TEXT,
    files_json      TEXT,
    delta_json      TEXT
);
CREATE INDEX idx_drs_code ON dataroom_scans(code_name, section, scanned_at);

-- ----------------------------------------------------------- financial -----

CREATE TABLE deal_financials (
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
    extracted_at    TEXT NOT NULL,
    entity          TEXT DEFAULT 'consolidated'
);
CREATE INDEX idx_df_domain_item ON deal_financials(domain, line_item, fiscal_year);
CREATE INDEX idx_df_domain_stmt ON deal_financials(domain, statement, fiscal_year);
CREATE INDEX idx_df_konto ON deal_financials(domain, konto_nr, fiscal_year);

CREATE TABLE deal_model_params (
    id                      TEXT PRIMARY KEY,
    domain                  TEXT NOT NULL,
    scenario_name           TEXT NOT NULL DEFAULT 'base',
    entities_json           TEXT,
    adj_items_json          TEXT,
    gf_old_salary_monthly_k REAL,
    gf_new_base_k           REAL,
    gf_tantieme_k           REAL,
    gf_sozialabgaben_pct    REAL DEFAULT 0.18,
    gf_benefit_factor       REAL DEFAULT 1.2,
    ebitda_basis_override   REAL,
    ebit_basis_override     REAL,
    ebitda_basis_label      TEXT,
    da_amount               REAL,
    multiple                REAL,
    net_debt                REAL,
    permitted_leakage       REAL DEFAULT 0,
    cash_at_closing         REAL,
    vendor_loan             REAL,
    earnout_anticipated     REAL,
    earnout_ebit_anchor     REAL,
    earnout_step            REAL DEFAULT 25,
    earnout_tiers_json      TEXT,
    proforma_gf_salary_k    REAL,
    proforma_nebenkosten_pct REAL DEFAULT 0.17,
    net_debt_items_json     TEXT,
    projection_revenue      REAL,
    projection_growth       REAL,
    comments_json           TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT,
    UNIQUE(domain, scenario_name)
);

CREATE TABLE deal_valuations (
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

-- ---------------------------------------------------- commercial (CDD) -----

CREATE TABLE deal_commercial (
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
CREATE INDEX idx_dcom_domain ON deal_commercial(domain, category, metric, fiscal_year);

CREATE TABLE deal_customers (
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
    extracted_at    TEXT NOT NULL,
    churn_reason    TEXT
);
CREATE INDEX idx_dc_domain_rank ON deal_customers(domain, fiscal_year, rank);
CREATE INDEX idx_dc_domain_year ON deal_customers(domain, fiscal_year);
CREATE UNIQUE INDEX idx_dc_unique ON deal_customers(domain, customer_name, fiscal_year);

CREATE TABLE deal_products (
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
CREATE INDEX idx_dprod_domain_year ON deal_products(domain, fiscal_year);

CREATE TABLE deal_invoices (
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
CREATE INDEX idx_dinv_domain_segment ON deal_invoices(domain, segment, fiscal_year);
CREATE INDEX idx_dinv_domain_year ON deal_invoices(domain, fiscal_year, quarter);

CREATE TABLE deal_backlog (
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
);
CREATE INDEX idx_dbacklog_domain_year ON deal_backlog(domain, fiscal_year);

CREATE TABLE deal_suppliers (
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
CREATE INDEX idx_dsup_domain ON deal_suppliers(domain, fiscal_year);

CREATE TABLE deal_employees (
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
CREATE INDEX idx_demp_domain ON deal_employees(domain);

CREATE TABLE deal_competitors (
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
CREATE INDEX idx_dcomp_domain ON deal_competitors(domain);

-- ------------------------------------------------------------------ DD -----

CREATE TABLE deal_dd_items (
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
    extracted_at    TEXT NOT NULL,
    confidence      TEXT,
    last_verified_at TEXT
);
CREATE INDEX idx_ddi_domain ON deal_dd_items(domain, category, status);

CREATE TABLE deal_questions (
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
    answer_feeds_data_key TEXT,
    sent_at              TEXT,
    answered_at          TEXT,
    created_at           TEXT NOT NULL,
    answer_source        TEXT
);

-- --------------------------------------------- negotiation / CRM spine -----
-- Unchanged from v1 (SPEC-negotiation-tool.md M1/M2, shipped 08.07).

CREATE TABLE stakeholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    company TEXT, role TEXT, email TEXT, phone TEXT,
    hubspot_contact_id TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX ux_stakeholder_hsid
    ON stakeholders(hubspot_contact_id) WHERE hubspot_contact_id IS NOT NULL;

CREATE TABLE stakeholder_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stakeholder_id INTEGER NOT NULL REFERENCES stakeholders(id),
    context_type TEXT NOT NULL CHECK(context_type IN ('deal','investor','advisor','lead','other')),
    context_ref TEXT NOT NULL,
    deal_domain TEXT,
    relationship TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE profile_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stakeholder_id INTEGER NOT NULL REFERENCES stakeholders(id),
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK(confidence IN ('UNSCORED','LOW','MED','HIGH')),
    evidence_quote TEXT,
    source_medium TEXT,
    source_date TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','contradicted','stale')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE negotiation_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stakeholder_id INTEGER NOT NULL REFERENCES stakeholders(id),
    context_type TEXT NOT NULL,
    context_ref TEXT NOT NULL,
    deal_domain TEXT,
    outcome_target TEXT NOT NULL,
    reservation TEXT, aspiration TEXT, locked_terms TEXT,
    memo_md TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','executing','superseded','closed')),
    created_at TEXT DEFAULT (datetime('now')),
    our_goals TEXT, their_goals TEXT, closed_reason TEXT
);
CREATE UNIQUE INDEX ux_strategy_active
    ON negotiation_strategies(stakeholder_id, context_ref) WHERE status='active';

CREATE TABLE negotiation_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL REFERENCES negotiation_strategies(id),
    stakeholder_id INTEGER NOT NULL REFERENCES stakeholders(id),
    round_no INTEGER NOT NULL,
    date TEXT NOT NULL, channel TEXT,
    we_asked TEXT, they_asked TEXT, we_gave TEXT, they_gave TEXT,
    outcome TEXT, next_step TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX ux_rounds_no ON negotiation_rounds(strategy_id, round_no);

CREATE TABLE negotiation_round_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES negotiation_rounds(id),
    went_well TEXT, went_wrong TEXT, lesson TEXT,
    self_rating INTEGER CHECK(self_rating BETWEEN 1 AND 5),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE negotiation_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polarity TEXT NOT NULL CHECK(polarity IN ('strength','weakness')),
    rule_ref TEXT,
    pattern TEXT NOT NULL,
    evidence TEXT NOT NULL,
    cost_estimate TEXT,
    drill TEXT,
    deal_refs TEXT,
    occurrences INTEGER DEFAULT 1,
    last_seen TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','watching','resolved','recurred')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE negotiation_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL REFERENCES negotiation_strategies(id),
    round_id INTEGER,
    objection TEXT NOT NULL,
    tag TEXT NOT NULL CHECK(tag IN ('profile','archetype')),
    counter TEXT,
    occurred INTEGER,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- §12 negotiation-tool tables (added to v1 on 2026-07-10/11, carried as-is)
CREATE TABLE negotiation_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    label TEXT NOT NULL,
    side TEXT DEFAULT 'both' CHECK (side IN ('ours','theirs','both')),
    consequence TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','met','missed','moved')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE negotiation_open_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    item TEXT NOT NULL,
    owner TEXT NOT NULL CHECK (owner IN ('us','them')),
    due TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved')),
    resolution TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE strategy_parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    stakeholder_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('primary','co_seller','advisor','influencer')),
    notes TEXT,
    UNIQUE (strategy_id, stakeholder_id)
);

CREATE TABLE negotiation_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    preferred TEXT NOT NULL,
    fallback TEXT,
    walk_away TEXT,
    escalation_required INTEGER DEFAULT 0,
    roman_confirmed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open' CHECK (status IN ('open','agreed','conceded','escalated')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE communication_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stakeholder_id INTEGER NOT NULL REFERENCES stakeholders(id),
    source TEXT NOT NULL,
    ref TEXT,
    date TEXT, direction TEXT, subject TEXT,
    read_status TEXT NOT NULL DEFAULT 'unread' CHECK(read_status IN ('read','unread','sealed')),
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX ux_trail
    ON communication_trail(stakeholder_id, source, ref, date, direction);

-- ---------------------------------------------------------------- meta -----

CREATE TABLE scorecard_config (
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

CREATE TABLE portfolio_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
