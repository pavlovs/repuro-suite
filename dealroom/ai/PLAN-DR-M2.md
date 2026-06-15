# DR-M2: Document Registry

## Summary

`DEALROOM.py ingest-docs --deal Octopus` scans the OneDrive deal folder, classifies all files by type, and registers them in `deal_documents`. Idempotent — re-running shows new vs. already-registered counts with no duplicates. No AI calls, no reading file contents — pure filesystem scan + rule-based classification.

**Scope**: 7 active deals — Octopus, Wolf, Cat, Fox, Panda, Falcon, Blackbird. Panda and Blackbird are added to `dealroom.db` as part of this milestone (they exist in OneDrive but were not in the DR-M1 seed). The remaining deals (Lion, Colibri, Owl, Eagle, Mouse, Kangaroo, Mantis) are out of scope for this milestone.

---

## HOW TO EXECUTE THIS MILESTONE

1. Read `PLAN-DR-M2.md` (this file) fully before writing any code.
2. Implement in the sequence listed in the Plan section. Do not skip steps.
3. No new dependencies — stdlib + pathlib only.
4. No Claude API calls in this milestone.
5. Tests use `tmp_path` fixture with fake file trees — never touch the real OneDrive.
6. After implementation: run `pytest tests/` (must pass), then run live against real deal.
7. Update `PLAN-DR-M2.md ## AI Validation Results` before committing.
8. One commit: `feat(DR-M2): Document Registry — ingest-docs, classify, deal_documents`

---

## Locked Decisions

**Classification is folder-first, keyword-second — no AI.**
Accuracy is good enough without AI: the folder structure already encodes ~80% of the type. DR-M3 (extractor) knows what it's reading anyway. No cost, no latency.

**Primary key = `md5(domain + absolute_file_path)`.**
Deterministic, collision-free at this scale, enables idempotent `INSERT OR IGNORE`.

**Domain fallback for NULL-domain deals = `code_name.lower()`.**
Consistent with DR-M1 `note` command fallback. Deals without ALLEX links use code name as scope identifier throughout DEALROOM.

**Register ALL files including archive models.**
`_archive/` and `_old/` files get `doc_subtype='archive'` — they're still registered so the document count is accurate and DR-M3 can exclude them explicitly by subtype. ARCHITECTURE.md invariant ("archive files never used as active model") applies in DR-M3, not here.

**New doc_types added (forward-compatible, no schema change needed):**
- `'rfi'` — question list / RFI answers (`.docx` with "RFI" or "Fragenliste" in name)
- `'repuro_internal'` — internal strategy/analysis docs (files in `7_Repuro documents/`)

These are documented in ARCHITECTURE.md `deal_documents` section as part of this milestone.

**Fiscal year extraction via regex only.**
`\b(20[1-9][0-9])\b` finds 4-digit years. If exactly one unique year found → use it. If multiple different years (range like 2024–2026) → `fiscal_year = None`. Also handles `12.25` → 2025 (DATEV-style month.year notation).

**Files at root of deal folder are registered.**
Coretec has JA files at root. Lion has RFI at root. These are real and important — scan recursively from deal folder root.

**Zip files and email `.msg` files → `doc_type='other'`.**
Owl has a `.zip` with financials — register the zip, do not unpack. Unpacking is DR-M3's concern.

**Panda and Blackbird are added to `dealroom.db` in Step 0 of this plan.**
They exist in OneDrive (`260223_IST Medical (Panda)`, `260303_ugietec` — note: no `(Blackbird)` in the folder name, so `resolve_folder` won't find it by code name; see Step 0 for the fix).

---

## Plan

### Step 0 — Add Panda + Blackbird to `dealroom.db`; fix Blackbird folder name

Check the actual OneDrive folder names for Panda and Blackbird:

```bash
ls "$DEALS_DIR" | grep -i "panda\|ist medical\|ugietec\|blackbird"
```

From prior scan:
- Panda → `260223_IST Medical (Panda)` — contains `(Panda)`, resolve_folder works
- Blackbird → `260303_ugietec` — does NOT contain `(Blackbird)`, resolve_folder will return None

**Fix for Blackbird**: the `deals.folder_path` field stores the folder name. `resolve_folder` searches for `({code_name})`. Since the folder is `260303_ugietec` (no code name in parentheses), add a fallback in `resolve_folder`: if no `({code_name})` match found, also check if `deals.folder_path` matches any subfolder name directly.

Update `src/db.py` `resolve_folder()`:
```python
def resolve_folder(code_name: str) -> "Path | None":
    deals_dir = settings.DEALS_DIR
    if not deals_dir.exists():
        return None
    # Primary: match by (CodeName) pattern
    target = f"({code_name})"
    for child in deals_dir.iterdir():
        if child.is_dir() and target in child.name:
            return child
    # Fallback: match by stored folder_path in DB (requires a DB conn — handled in scan_deal)
    return None
```

The fallback via stored `folder_path` is handled in `scan_deal`: if `resolve_folder` returns None, try `settings.DEALS_DIR / deals.folder_path` directly.

**Two new seed rows** added to `src/db.py` `SEED_DEALS` (appended — `init_db` only inserts if table is empty, so existing DBs need a one-time INSERT):

| code_name | company_name | domain | deal_stage | folder_path |
|-----------|-------------|--------|------------|-------------|
| Panda | IST Medical GmbH | ist-intensivservice.de | financials_received | `260223_IST Medical (Panda)` |
| Blackbird | Ugietec | None | financials_received | `260303_ugietec` |

**Migration for existing `dealroom.db`**: add a `migrate_add_missing_deals(conn)` function called in `get_conn()` after `init_db()`. It INSERTs Panda and Blackbird with `INSERT OR IGNORE` (safe to run multiple times).

```python
MIGRATION_DEALS = [
    {
        "code_name": "Panda",
        "company_name": "IST Medical GmbH",
        "domain": "ist-intensivservice.de",
        "deal_stage": "financials_received",
        "folder_path": "260223_IST Medical (Panda)",
    },
    {
        "code_name": "Blackbird",
        "company_name": "Ugietec",
        "domain": None,
        "deal_stage": "financials_received",
        "folder_path": "260303_ugietec",
    },
]

def migrate_add_missing_deals(conn: sqlite3.Connection) -> None:
    """Idempotent: add deals that were not in the original DR-M1 seed."""
    now = datetime.now(timezone.utc).isoformat()
    for deal in MIGRATION_DEALS:
        conn.execute(
            """
            INSERT OR IGNORE INTO deals
            (id, domain, code_name, company_name, deal_stage, folder_path, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), deal["domain"], deal["code_name"],
             deal["company_name"], deal["deal_stage"], deal["folder_path"], now),
        )
    conn.commit()
```

Call `migrate_add_missing_deals(conn)` in `get_conn()` after `init_db(conn)`.

### Step 1 — `src/ingest.py`

Create `src/ingest.py`. Structure:

```python
# src/ingest.py

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings


# Classification rules — evaluated in order, first match wins.
# Each rule: (folder_keywords, name_keywords, extension_set, doc_type, doc_subtype)
# folder_keywords: list of strings that must appear in the relative path parts
# name_keywords: list of strings (lowercased) checked against filename
# extension_set: set of allowed extensions (None = any)

def extract_year(filename: str) -> Optional[int]:
    """Extract fiscal year from filename. Returns None if ambiguous."""
    years = list(set(re.findall(r'\b(20[1-9][0-9])\b', filename)))
    if len(years) == 1:
        return int(years[0])
    # DATEV-style: "12.25" or "9.25" → 2025
    m = re.search(r'\b\d{1,2}\.(\d{2})\b', filename)
    if m and not years:
        return 2000 + int(m.group(1))
    return None


def classify_file(
    file_path: Path, deal_folder: Path
) -> tuple[str, Optional[str], Optional[int]]:
    """
    Returns (doc_type, doc_subtype, fiscal_year).

    doc_type options:
        'financials_raw' | 'model' | 'offer' | 'nda' | 'loi' | 'meeting'
        | 'dd' | 'rfi' | 'repuro_internal' | 'other'

    Classification is folder-first, then filename keywords.
    """
    try:
        rel = file_path.relative_to(deal_folder)
    except ValueError:
        return 'other', None, None

    parts = [p.lower() for p in rel.parts]
    name_lower = file_path.name.lower()
    ext = file_path.suffix.lower()
    year = extract_year(file_path.name)

    # ── 2_Model ──────────────────────────────────────────────────────────────
    if any('2_model' in p for p in parts):
        subtype = 'archive' if ('_archive' in parts or '_old' in parts) else None
        return 'model', subtype, year

    # ── 3_Indikatives Angebot ────────────────────────────────────────────────
    if any('3_' in p and 'angebot' in p for p in parts):
        return 'offer', None, year

    # ── 4_LOI ────────────────────────────────────────────────────────────────
    if any('4_loi' in p for p in parts):
        subtype = 'archive' if ('_old' in parts or '_archive' in parts) else None
        return 'loi', subtype, year

    # ── 5_DD ─────────────────────────────────────────────────────────────────
    if any('5_dd' in p for p in parts):
        return 'dd', None, year

    # ── 7_Repuro documents ───────────────────────────────────────────────────
    if any('7_repuro' in p or 'repuro doc' in p for p in parts):
        return 'repuro_internal', None, year

    # ── 0_Verträge und Meetings ───────────────────────────────────────────────
    if any('0_vertr' in p or '0_verträ' in p for p in parts):
        # NDA subfolder
        if 'nda' in parts:
            return 'nda', None, year
        # NDA by filename (some deals store NDA directly in folder)
        if any(kw in name_lower for kw in ('vertraulichkeit', 'nda', 'ndas')):
            return 'nda', None, year
        return 'meeting', None, year

    # ── 1_Unternehmensinformationen ───────────────────────────────────────────
    if any('1_unternehmen' in p for p in parts):
        return _classify_financials_raw(name_lower, year)

    # ── Files at root of deal folder (no subfolder) ───────────────────────────
    if len(parts) == 1:
        return _classify_root_file(name_lower, year)

    return 'other', None, year


def _classify_financials_raw(
    name_lower: str, year: Optional[int]
) -> tuple[str, Optional[str], Optional[int]]:
    """Classify files in 1_Unternehmensinformationen/."""
    # RFI / Fragenliste
    if any(kw in name_lower for kw in ('rfi', 'fragenliste')):
        return 'rfi', None, year
    # GuV — Gewinn und Verlust
    if any(kw in name_lower for kw in ('g.u.v', 'guv', 'gewinn', 'erfolgsrechnung', 'deckungsbeitrag')):
        return 'financials_raw', 'guv', year
    # Bilanz
    if 'bilanz' in name_lower:
        return 'financials_raw', 'bilanz', year
    # BWA — Betriebswirtschaftliche Auswertung
    if 'bwa' in name_lower:
        return 'financials_raw', 'bwa', year
    # SUSA — Summen und Salden
    if any(kw in name_lower for kw in ('susa', 'summen und salden', 'summen-und-salden')):
        return 'financials_raw', 'susa', year
    # JA — Jahresabschluss
    if any(kw in name_lower for kw in ('ja ', 'ja_', 'jahresabschluss', 'testat', 'annual')):
        return 'financials_raw', 'ja', year
    # Customer data
    if any(kw in name_lower for kw in ('kundenumsatz', 'kundengruppen', 'kunden', 'customer')):
        return 'financials_raw', 'customer', year
    # Product/article split
    if any(kw in name_lower for kw in ('artikelgruppen', 'warengruppen', 'umsätze nach')):
        return 'financials_raw', 'product_split', year
    # Planning / Planung
    if any(kw in name_lower for kw in ('planung', 'plan', 'vorschau', 'forecast')):
        return 'financials_raw', 'planning', year
    # Analysis
    if any(kw in name_lower for kw in ('analyse', 'analysis', 'auswertung')):
        return 'financials_raw', 'analysis', year
    # Exposé
    if 'expose' in name_lower or 'exposé' in name_lower:
        return 'financials_raw', 'expose', year
    return 'financials_raw', None, year


def _classify_root_file(
    name_lower: str, year: Optional[int]
) -> tuple[str, Optional[str], Optional[int]]:
    """Classify files at the root of the deal folder (no subfolder)."""
    if any(kw in name_lower for kw in ('rfi', 'fragenliste')):
        return 'rfi', None, year
    if any(kw in name_lower for kw in ('g.u.v', 'guv', 'ja ', 'ja_', 'bilanz', 'bwa')):
        return 'financials_raw', None, year
    if any(kw in name_lower for kw in ('vertraulichkeit', 'nda')):
        return 'nda', None, year
    return 'other', None, year


def scan_deal(code_name: str, conn) -> dict:
    """
    Scan the OneDrive folder for `code_name`, classify and register all files.

    Returns: {'new': int, 'skipped': int, 'total': int, 'by_type': dict}
    """
    from src.db import resolve_folder

    row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Deal not found: {code_name}")

    domain = row["domain"] or code_name.lower()
    folder = resolve_folder(code_name)
    if folder is None:
        raise FileNotFoundError(
            f"OneDrive folder for '{code_name}' not found in DEALS_DIR: {settings.DEALS_DIR}"
        )

    now = datetime.now(timezone.utc).isoformat()
    counts = {'new': 0, 'skipped': 0, 'total': 0, 'by_type': {}}

    # Skip temp files (OneDrive lock files, .tmp, etc.)
    SKIP_PREFIXES = ('~$', '.~')
    SKIP_EXTENSIONS = {'.tmp', '.lnk', '.url'}

    for file_path in sorted(folder.rglob('*')):
        if not file_path.is_file():
            continue
        if file_path.name.startswith(SKIP_PREFIXES):
            continue
        if file_path.suffix.lower() in SKIP_EXTENSIONS:
            continue

        doc_type, doc_subtype, fiscal_year = classify_file(file_path, folder)
        doc_id = hashlib.md5(
            f"{domain}{str(file_path)}".encode('utf-8')
        ).hexdigest()
        size_kb = int(file_path.stat().st_size / 1024)

        counts['total'] += 1
        counts['by_type'].setdefault(doc_type, {'new': 0, 'skipped': 0})

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO deal_documents
                (id, domain, code_name, file_path, doc_type, doc_subtype,
                 fiscal_year, file_name, file_size_kb, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id, domain, code_name, str(file_path),
                    doc_type, doc_subtype, fiscal_year,
                    file_path.name, size_kb, now,
                ),
            )
            if conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0:
                counts['new'] += 1
                counts['by_type'][doc_type]['new'] += 1
            else:
                counts['skipped'] += 1
                counts['by_type'][doc_type]['skipped'] += 1
        except Exception:
            counts['skipped'] += 1
            counts['by_type'][doc_type]['skipped'] += 1

    conn.commit()
    return counts
```

---

### Step 2 — `DEALROOM.py` — wire up `ingest-docs`

Replace the `ingest-docs` stub in `DEALROOM.py` with a real handler:

```python
def cmd_ingest_docs(args) -> None:
    from src.ingest import scan_deal
    conn = get_conn()

    deals_to_scan = []
    if args.deal:
        deals_to_scan = [args.deal]
    elif args.all:
        rows = conn.execute(
            "SELECT code_name FROM deals ORDER BY code_name"
        ).fetchall()
        deals_to_scan = [r["code_name"] for r in rows]
    else:
        print("Provide --deal <CODE> or --all")
        sys.exit(1)

    for code in deals_to_scan:
        try:
            counts = scan_deal(code, conn)
            _print_ingest_report(code, counts)
        except FileNotFoundError as e:
            print(f"  {code}: {e}")
        except ValueError as e:
            print(f"  {code}: {e}")
    conn.close()


def _print_ingest_report(code_name: str, counts: dict) -> None:
    print(f"\n{code_name}  ({counts['total']} files total, {counts['new']} new)")
    print(f"  {'Type':<20} {'New':>5}  {'Already registered':>5}")
    print("  " + "-" * 38)
    for doc_type, c in sorted(counts['by_type'].items()):
        if c['new'] > 0 or c['skipped'] > 0:
            print(f"  {doc_type:<20} {c['new']:>5}  {c['skipped']:>5}")
```

Update the argparse entry for `ingest-docs` in `main()`:
```python
p_ingest = sub.add_parser("ingest-docs", help="Register documents from OneDrive deal folder")
p_ingest.add_argument("--deal", metavar="CODE_NAME")
p_ingest.add_argument("--all", action="store_true", help="Scan all deals")
p_ingest.set_defaults(func=cmd_ingest_docs)
```

---

### Step 3 — Update `ARCHITECTURE.md`

In the `deal_documents` schema section, update the `doc_type` comment:
```
-- 'financials_raw' | 'model' | 'offer' | 'nda' | 'loi' | 'meeting' | 'dd'
-- | 'rfi' | 'repuro_internal' | 'other'
```

Add a `doc_subtype` taxonomy table below the schema:

| doc_type | doc_subtype values |
|----------|-------------------|
| `financials_raw` | `guv` \| `bilanz` \| `bwa` \| `susa` \| `ja` \| `customer` \| `product_split` \| `planning` \| `analysis` \| `expose` \| `None` |
| `model` | `archive` \| `None` (active) |
| `loi` | `archive` \| `None` (active) |
| all others | `None` |

---

### Step 4 — `tests/test_ingest.py`

```python
import sqlite3, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db
from src.ingest import classify_file, extract_year, scan_deal


# ── extract_year ─────────────────────────────────────────────────────────────

def test_year_from_plain_name():
    assert extract_year("JA 2022 Kontennachweis.xlsx") == 2022

def test_year_from_datev_style():
    assert extract_year("BWA 12.25.pdf") == 2025

def test_year_ambiguous_range():
    assert extract_year("hwv bilanz 3jÜ_2024-2026.pdf") is None

def test_year_none_when_absent():
    assert extract_year("Vertraulichkeitsvereinbarung.docx") is None


# ── classify_file ─────────────────────────────────────────────────────────────

@pytest.fixture
def deal_root(tmp_path):
    """Build a minimal fake deal folder structure."""
    (tmp_path / "0_Verträge und Meetings" / "NDA").mkdir(parents=True)
    (tmp_path / "1_Unternehmensinformationen").mkdir()
    (tmp_path / "2_Model" / "_archive").mkdir(parents=True)
    (tmp_path / "3_Indikatives Angebot").mkdir()
    (tmp_path / "4_LOI" / "_old").mkdir(parents=True)
    (tmp_path / "5_DD").mkdir()
    (tmp_path / "7_Repuro documents").mkdir()
    return tmp_path


def _f(deal_root, rel):
    p = deal_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    return p


def test_classify_nda_in_subfolder(deal_root):
    f = _f(deal_root, "0_Verträge und Meetings/NDA/250724_NDA.docx")
    assert classify_file(f, deal_root)[:2] == ('nda', None)

def test_classify_nda_by_name_in_meetings(deal_root):
    f = _f(deal_root, "0_Verträge und Meetings/250612_Vertraulichkeitsvereinbarung.docx")
    assert classify_file(f, deal_root)[:2] == ('nda', None)

def test_classify_meeting(deal_root):
    f = _f(deal_root, "0_Verträge und Meetings/250814_Repuro_vP.pptx")
    assert classify_file(f, deal_root)[:2] == ('meeting', None)

def test_classify_guv(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis zur G.u.V..xlsx")
    t, st, _ = classify_file(f, deal_root)
    assert t == 'financials_raw' and st == 'guv'

def test_classify_bilanz(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis zur Bilanz.xlsx")
    t, st, _ = classify_file(f, deal_root)
    assert t == 'financials_raw' and st == 'bilanz'

def test_classify_bwa(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/BWA 12.25.pdf")
    t, st, _ = classify_file(f, deal_root)
    assert t == 'financials_raw' and st == 'bwa'

def test_classify_ja(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 31.12.2023_HWV.pdf")
    t, st, _ = classify_file(f, deal_root)
    assert t == 'financials_raw' and st == 'ja'

def test_classify_model_active(deal_root):
    f = _f(deal_root, "2_Model/260119_Golmed_v8.xlsx")
    assert classify_file(f, deal_root)[:2] == ('model', None)

def test_classify_model_archive(deal_root):
    f = _f(deal_root, "2_Model/_archive/250629_HWV_v1.xlsx")
    assert classify_file(f, deal_root)[:2] == ('model', 'archive')

def test_classify_offer(deal_root):
    f = _f(deal_root, "3_Indikatives Angebot/250908_Angebot_v1.docx")
    assert classify_file(f, deal_root)[:2] == ('offer', None)

def test_classify_loi(deal_root):
    f = _f(deal_root, "4_LOI/260210_LOI_v1.docx")
    assert classify_file(f, deal_root)[:2] == ('loi', None)

def test_classify_loi_old(deal_root):
    f = _f(deal_root, "4_LOI/_old/251202_LOI_v1.docx")
    assert classify_file(f, deal_root)[:2] == ('loi', 'archive')

def test_classify_dd(deal_root):
    f = _f(deal_root, "5_DD/260108_Datenanfrage.xlsx")
    assert classify_file(f, deal_root)[:2] == ('dd', None)

def test_classify_repuro_internal(deal_root):
    f = _f(deal_root, "7_Repuro documents/260309_overview_vS.pdf")
    assert classify_file(f, deal_root)[:2] == ('repuro_internal', None)

def test_classify_rfi_in_financials(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/250807_HWV_RFI_vS.docx")
    assert classify_file(f, deal_root)[:2] == ('rfi', None)

def test_classify_rfi_at_root(deal_root):
    f = _f(deal_root, "250831_Golmed_RFI_vS.docx")
    assert classify_file(f, deal_root)[:2] == ('rfi', None)

def test_classify_year_extracted(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis.xlsx")
    _, _, year = classify_file(f, deal_root)
    assert year == 2022


# ── scan_deal ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_conn_with_deal(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Override DEALS_DIR to tmp_path
    import config.settings as s
    s.DEALS_DIR = tmp_path
    yield conn, tmp_path
    conn.close()
    import config.settings as original_settings
    # restore is best-effort; each test uses fresh tmp_path


def _build_fake_folder(base: Path, code: str) -> Path:
    folder = base / f"250101_TestCo ({code})"
    (folder / "1_Unternehmensinformationen").mkdir(parents=True)
    (folder / "2_Model").mkdir()
    (folder / "0_Verträge und Meetings" / "NDA").mkdir(parents=True)
    (folder / "1_Unternehmensinformationen" / "GuV_2023.xlsx").write_text("x")
    (folder / "1_Unternehmensinformationen" / "Bilanz_2023.xlsx").write_text("x")
    (folder / "2_Model" / "250101_code_v1.xlsx").write_text("x")
    (folder / "0_Verträge und Meetings" / "NDA" / "250101_NDA.docx").write_text("x")
    return folder


def test_scan_registers_files(mem_conn_with_deal):
    conn, tmp_path = mem_conn_with_deal
    # Add a test deal
    import uuid
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO deals (id, code_name, company_name, domain, deal_stage, folder_path, added_at) "
        "VALUES (?, 'TestDeal', 'Test Co', 'test.de', 'financials_received', '250101_TestCo (TestDeal)', ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    _build_fake_folder(tmp_path, "TestDeal")

    counts = scan_deal("TestDeal", conn)
    assert counts['total'] == 4
    assert counts['new'] == 4
    assert counts['skipped'] == 0
    # DB should have 4 rows
    n = conn.execute("SELECT COUNT(*) FROM deal_documents WHERE code_name='TestDeal'").fetchone()[0]
    assert n == 4


def test_scan_idempotent(mem_conn_with_deal):
    conn, tmp_path = mem_conn_with_deal
    import uuid
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO deals (id, code_name, company_name, domain, deal_stage, folder_path, added_at) "
        "VALUES (?, 'TestDeal2', 'Test Co 2', 'test2.de', 'financials_received', '250101_TestCo2 (TestDeal2)', ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    (tmp_path / "250101_TestCo2 (TestDeal2)" / "1_Unternehmensinformationen").mkdir(parents=True)
    (tmp_path / "250101_TestCo2 (TestDeal2)" / "1_Unternehmensinformationen" / "GuV.xlsx").write_text("x")

    scan_deal("TestDeal2", conn)
    scan_deal("TestDeal2", conn)  # second run
    n = conn.execute("SELECT COUNT(*) FROM deal_documents WHERE code_name='TestDeal2'").fetchone()[0]
    assert n == 1  # no duplicates


def test_scan_null_domain_uses_codename(mem_conn_with_deal):
    conn, tmp_path = mem_conn_with_deal
    import uuid
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO deals (id, code_name, company_name, domain, deal_stage, folder_path, added_at) "
        "VALUES (?, 'TestDeal3', 'Test Co 3', NULL, 'financials_received', '250101_NullDomain (TestDeal3)', ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    (tmp_path / "250101_NullDomain (TestDeal3)" / "1_Unternehmensinformationen").mkdir(parents=True)
    (tmp_path / "250101_NullDomain (TestDeal3)" / "1_Unternehmensinformationen" / "GuV.xlsx").write_text("x")

    scan_deal("TestDeal3", conn)
    row = conn.execute("SELECT domain FROM deal_documents WHERE code_name='TestDeal3'").fetchone()
    assert row["domain"] == "testdeal3"  # falls back to code_name.lower()
```

---

## Better Engineering Notes

**`.zip` handling**: Owl has `Unterlagen Fa. Repuro.zip` with financials inside. Registered as `doc_type='other'` in DR-M2. In DR-M3, the extractor should detect `.zip` files in `1_Unternehmensinformationen/`, unpack to a temp dir, and classify/extract each inner file. Design note for DR-M3 plan.

**File path stability**: OneDrive absolute paths are stable as long as the user doesn't rename folders. The md5-based ID will produce a different hash if OneDrive renames a file (unlikely). Acceptable risk at this scale.

**`changes()` for INSERT OR IGNORE tracking**: After `INSERT OR IGNORE`, call `SELECT changes()` to check if the row was inserted (1) or ignored (0). This is the clean SQLite idiom for distinguishing new vs. already-registered without an extra SELECT.

**DATEV-format filenames**: "1213976_1_2024_Kontennachweis zur G.u.V.[34].xlsx" — the `[34]` suffix is a DATEV export artifact (page count or copy number). Shouldn't affect classification, but worth knowing for DR-M3.

**Temp file skipping**: OneDrive creates `~$filename.xlsx` lock files when a file is open. Must skip these (already handled with `SKIP_PREFIXES`).

---

## AI Validation Plan

```bash
# 1. Tests pass
cd REPURO/dealroom && python -m pytest tests/ -v

# Expected: all tests pass including new test_ingest.py tests

# 2. Verify Panda + Blackbird added to DB
python DEALROOM.py deals
# Expected: 12 rows including Panda and Blackbird

# 3. Live run against the 7 scoped deals
python DEALROOM.py ingest-docs --deal Octopus
python DEALROOM.py ingest-docs --deal Wolf
python DEALROOM.py ingest-docs --deal Cat
python DEALROOM.py ingest-docs --deal Fox
python DEALROOM.py ingest-docs --deal Falcon
python DEALROOM.py ingest-docs --deal Panda
python DEALROOM.py ingest-docs --deal Blackbird

# Expected: each prints file counts by type, non-zero new count

# 4. Idempotency check on one deal
python DEALROOM.py ingest-docs --deal Octopus
# Expected: same total, 0 new

# 5. Status shows non-zero deal_documents count
python DEALROOM.py status
# Expected: deal_documents row > 0 (expect 100+ for Octopus alone)

# 6. Blackbird specifically — confirm folder_path fallback works
python DEALROOM.py ingest-docs --deal Blackbird
# Expected: no crash, registers whatever is in 260303_ugietec/
```

---

## AI Validation Results

**2026-03-29** — Executed cleanly.

- `pytest tests/ -v` → 44 passed, 0 warnings (27 existing + 17 new in test_ingest.py)
- `DEALROOM.py deals` → 12 rows; Panda and Blackbird present
- `DEALROOM.py ingest-docs` run on all 7 scoped deals:
  - Octopus: 145 files (dd=11, financials_raw=51, loi=20, meeting=16, model=21, nda=3, offer=14, repuro_internal=7, rfi=2)
  - Wolf: 26, Cat: 98, Fox: 68, Falcon: 6, Panda: 3, Blackbird: 7
  - Total: 353 documents registered
- Idempotency: second run on Octopus → 0 new, 145 already registered
- `DEALROOM.py status` → deal_documents = 353

**One plan deviation**: Blackbird folder is `260303_ugietec (Blackbird)` — `(Blackbird)` IS in the name. No folder_path fallback was needed; resolve_folder works normally. The plan's Step 0 complexity was unnecessary.

**One bug found and fixed**: `extract_year` used `\b` word-boundary regex. Python's `\b` treats `_` as a word character, so `_2024_` doesn't produce two boundaries — only the trailing one matches, causing DATEV-style filenames like `1213976_1_2024_...` to return None. Fixed with digit-boundary lookarounds: `(?<!\d)(20[1-9][0-9])(?!\d)`.

---

## User Validation Walkthrough

```bash
cd REPURO/dealroom

# 1. Check Panda + Blackbird are now in the DB
python DEALROOM.py deals

# 2. Run the 7 scoped deals
python DEALROOM.py ingest-docs --deal Octopus
python DEALROOM.py ingest-docs --deal Wolf
python DEALROOM.py ingest-docs --deal Cat
python DEALROOM.py ingest-docs --deal Fox
python DEALROOM.py ingest-docs --deal Falcon
python DEALROOM.py ingest-docs --deal Panda
python DEALROOM.py ingest-docs --deal Blackbird

# 3. Check status
python DEALROOM.py status

# 4. Re-run one — confirm 0 new
python DEALROOM.py ingest-docs --deal Octopus
```

Verify:
- `deals` shows 12 rows (10 original + Panda + Blackbird)
- `deal_documents` row count is non-zero
- Second run on Octopus shows 0 new files
- Blackbird resolves via `folder_path` fallback — no crash
