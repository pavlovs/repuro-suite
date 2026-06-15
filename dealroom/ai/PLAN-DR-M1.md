# PLAN-DR-M1: Foundation

## Context

First milestone. Nothing exists yet. Establishes:
- `DEALROOM.py` CLI entry point — all 10 commands, 8 fully stubbed, `deals` and `status` functional
- `dealroom.db` with all 9 tables (schema from ARCHITECTURE.md): `deals`, `deal_data`, `deal_valuations`, `deal_documents`, `deal_questions`, `deal_actions`, `deal_emails`, `deal_granola`, `deal_notes`
- ALLEX ATTACH helper (`src/db.py`) — read-only connection to `pipeline.db`
- `config/settings.py` — paths and constants, including OneDrive DEALS_DIR
- Seed data: 5 confirmed active deals in `dealroom.deals`
- Passing `pytest tests/`

After DR-M1: `python DEALROOM.py deals` prints all active deals with stage and company name. `python DEALROOM.py status` shows DB table row counts and folder link status. All other commands print "not implemented".

**No dependency on ALLEX M15.** `pipeline.db` has only `company_records`. `deals` table lives in `dealroom.db`.

**Folders live in OneDrive** — already synced locally. DEALROOM reads from there; it does not create folders.

---

## Files to Create

```
DEALROOM.py                          # CLI entry point
config/__init__.py
config/settings.py                   # paths, ALLEX_PIPELINE_DB, DEALS_DIR
src/__init__.py
src/db.py                            # init_db(), get_conn() — read-only ATTACH
tests/__init__.py
tests/test_db.py                     # schema integrity, ATTACH smoke test
tests/test_deals.py                  # deals listing, NULL domain / folder handling
data/dealroom.db                     # created at runtime by init_db()
```

---

## Implementation Sequence

### Step 1: `config/settings.py`

```python
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "dealroom.db"

# OneDrive deal folders — already synced locally
DEALS_DIR = Path(os.getenv(
    "DEALS_DIR",
    str(Path.home() / "Documents" / "OneDrive - Kamu Kapital" /
        "Dokumente - Kamu Kapital" / "3_Deals" / "3_Targets")
))

ALLEX_PIPELINE_DB = Path(os.getenv(
    "ALLEX_PIPELINE_DB",
    str(BASE_DIR.parent / "lead-pipeline" / "data" / "pipeline.db")
))
```

### Step 2: `src/db.py`

Two responsibilities:
1. `init_db(conn)` — creates all 8 tables if not exist, inserts seed deals
2. `get_conn()` — returns connection to dealroom.db with ALLEX attached read-only

```python
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, uri=False)
    conn.row_factory = sqlite3.Row
    allex_path = settings.ALLEX_PIPELINE_DB
    if allex_path.exists():
        conn.execute(f"ATTACH DATABASE 'file:{allex_path}?mode=ro' AS allex")
    return conn
```

**Read-only ATTACH**: use `file:path?mode=ro`. This enforces read-only at the driver level.

**`init_db()` creates these tables in order**:
1. `deals` — tracks active deals (code_name, domain, company_name, deal_stage, folder_path)
2. `deal_documents`
3. `deal_financials`
4. `deal_valuations`
5. `deal_emails`
6. `deal_granola`
7. `deal_notes`

All `CREATE TABLE IF NOT EXISTS`.

**Seed data** (inserted only if `deals` table is empty):

| code_name | company_name | domain | deal_stage | folder_path |
|-----------|-------------|--------|------------|-------------|
| Octopus | HWV Hanseatische... | hwv-med.de | offer_sent | `250611_HWV (Octopus)` |
| Cat | Medizin & Service GmbH | NULL | offer_negotiation | `250612_Medizin & Service (Cat)` |
| Lion | Golmed GmbH | golmed.de | offer_negotiation | `250724_Golmed (Lion)` |
| Fox | Com2Med | com2med.de | offer_preparation | `250702_Com2Med (Fox)` |
| Wolf | KVG Vertriebs GmbH | NULL | offer_negotiation | `251125_KVG (Wolf)` |
| Colibri | Menke-Med GmbH | menke-med.de | offer_preparation | `250828_Menke (Colibri)` |
| Falcon | KoeWe Medizinbedarf GmbH | koewe.com | offer_preparation | `260225_KoeWe (Falcon)` |
| Owl | RS Radiology Support | radiology-support.de | financials_received | `251126_RS Radiology (Owl)` |
| Eagle | Meditec Source | NULL | financials_received | `251002_Meditec Source (Eagle)` |
| Mouse | Coretec-Service GmbH | coretec-service.de | financials_received | `250625_Coretec-Service (Mouse)` |

**No folder creation in init_db** — folders already exist in OneDrive. `init_db()` only creates `data/` dir and `dealroom.db`.

**`resolve_folder(code_name)`** helper: searches `DEALS_DIR` for a subfolder whose name contains `({code_name})`. Returns `Path | None`. Used by `status` and `ingest-docs`.

### Step 3: `DEALROOM.py`

CLI entry point. Uses `argparse` with subcommands.

```
python DEALROOM.py deals                        # list active deals
python DEALROOM.py status                       # DB state + folder inventory
python DEALROOM.py ingest-docs --deal <name>    # stub
python DEALROOM.py extract --deal <name>        # stub
python DEALROOM.py value --deal <name>          # stub
python DEALROOM.py bench                        # stub
python DEALROOM.py draft-offer --deal <name>    # stub
python DEALROOM.py draft-email --deal <name>    # stub
python DEALROOM.py draft-nda --deal <name>      # stub
python DEALROOM.py sync-granola [--deal <name>] # stub
python DEALROOM.py dashboard [--deal <name>]    # stub
```

**`deals` command output** (tabular, no external deps):

```
CODE      STAGE                COMPANY                         DOMAIN
-------   -------------------  ------------------------------ ----------
Octopus   loi_negotiation      HWV Hanseatische...             hwv-med.de
Cat       indicative_offer     Medizin & Service GmbH          [unlinked]
Lion      indicative_offer     Golmed GmbH                     golmed.de
Fox       indicative_offer     Com2Med                         com2med.de
Wolf      declined             KVG Vertriebs GmbH              [unlinked]
```

Query: read from `dealroom.deals` only (company_name stored at seed time, domain for ALLEX link).

Handle case where ALLEX file is missing: show `[allex unavailable]`, continue.

**`status` command output**:

```
dealroom.db: data/dealroom.db (42 KB)
ALLEX: ../lead-pipeline/data/pipeline.db ✓ attached (2420 records)
DEALS_DIR: C:/Users/X1/Documents/OneDrive - Kamu Kapital/... ✓ exists

Table            Rows
-----------      ----
deals               5
deal_documents      0
deal_financials     0
deal_valuations     0
deal_emails         0
deal_granola        0
deal_notes          0

Deal folders (OneDrive):
  Octopus  ✓  250611_HWV (Octopus)
  Cat      ✓  250612_Medizin & Service (Cat)
  Lion     ✓  250724_Golmed (Lion)
  Fox      ✓  250702_Com2Med (Fox)
  Wolf     ✓  251125_KVG (Wolf)
```

**Stubbed commands**: print `[DR-M{n}] <command> not implemented yet.` with the relevant milestone number.

### Step 4: Tests

**`tests/test_db.py`**:
- `init_db()` creates all 9 tables in a tmp_path DB (including deal_questions, deal_actions)
- Seed data: 10 deals inserted
- Octopus domain = 'hwv-med.de', stage = 'offer_sent'
- Lion domain = 'golmed.de', Colibri domain = 'menke-med.de', Falcon domain = 'koewe.com'
- ATTACH: no crash if pipeline.db missing
- `get_conn()` sets `row_factory = sqlite3.Row`

**`tests/test_deals.py`**:
- `deals` query returns 5 rows
- NULL domain handled without crash
- `resolve_folder()` returns correct path when OneDrive present; returns None gracefully when DEALS_DIR missing

Use `tmp_path` fixture for all DB creation — never touch `data/` in tests.

---

## Architecture Changes

`ARCHITECTURE.md`: `deals` table schema updated (folder_path, company_name added). Folder structure section updated to reflect OneDrive reality.
`ROADMAP.md`: DR-M1 spec updated (no M15 dep, OneDrive path, seed data).
`PLAN.md`: current state updated.

---

## Definition of Done

- [x] `python DEALROOM.py deals` prints 10 active deals from dealroom.db
- [x] `python DEALROOM.py status` shows table row counts + OneDrive folder link status (all 10 folders found)
- [x] All other 10 commands run without error (print stub message)
- [x] `pytest tests/` passes — 17 passed, 0 warnings
- [x] `ARCHITECTURE.md` `deals` table and folder structure updated
- [x] One commit: `feat(DR-M1): Foundation — dealroom.db, CLI skeleton, seed deals`

---

## AI Validation Results

**2026-03-28** — Executed cleanly.

- `pytest tests/` → 17 passed, 0 warnings
- `DEALROOM.py deals` → 10 rows, correct stages and domains
- `DEALROOM.py status` → ALLEX attached (2420 records), DEALS_DIR exists, all 10 OneDrive folders resolved
- All 10 stub commands respond correctly
- `stage` and `note` commands functional

**One fix during execution**: SQLite ATTACH URI mode (`file:path?mode=ro`) fails on Windows with drive-letter paths. Switched to plain `ATTACH DATABASE ? AS allex`. Read-only enforced at application level (invariant in ARCHITECTURE.md). Added note to LEARNINGS.md.
