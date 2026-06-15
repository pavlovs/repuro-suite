"""
DR-M6: RFI Generator.

Generates a German RFI question list for a deal using:
1. Golden corpus from registered doc_type='rfi' files (Cat, Fox, Octopus) + config/rfi_examples/
2. Deal-specific financial anomalies from deal_financials (YoY changes, margin flags, adj vs stated)
3. Unresolved deal_financials conflicts → one German question per conflicting metric

Output: deal_questions rows (idempotent) + PDF draft in deal folder.
Claude invocation: claude CLI subprocess (--via-cli, OAuth, no API key).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

# ─── Brand colours (Repuro CI) ───────────────────────────────────────────────
try:
    from reportlab.lib.colors import HexColor as _HexColor

    _REPURO_TEAL = _HexColor("#1D7080")  # header background
    _REPURO_TEAL_LIGHT = _HexColor("#D5EEF2")  # P-year column tint
    _REPURO_TEAL_TEXT = _HexColor("#1D7080")  # P-year column text
    _REPURO_DARK = _HexColor("#2B2B2B")  # near-black text
    _REPURO_GRAY = _HexColor("#F4F4F4")  # alternating row tint
    _REPURO_WHITE = _HexColor("#FFFFFF")
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

logger = logging.getLogger(__name__)

_CLAUDE_CMD: str = (
    shutil.which("claude") or r"C:\Users\X1\AppData\Roaming\npm\claude.cmd"
)

# Valid fiscal year range — avoids year-detection bugs (e.g. "31.12" → 2012)
_YEAR_MIN = 2015
_YEAR_MAX = 2030

# Map source field → display label for dashboard badges
_SOURCE_LABEL_MAP: dict[str, str] = {
    "rfi_generator": "TEMPLATE",
    "rfi_generator:conflict": "CONFLICT",
    "manual": "MANUAL",
}

# Subcategory → Word section header
_SECTION_MAP: dict[str, str] = {
    "adjustments": "Allgemeine Fragen / Adjustments",
    "revenue": "GuV",
    "costs": "GuV",
    "balance": "Bilanz",
    "customers": "Kunden",
    "revenue_split": "Kunden",
    "contracts": "Kunden",
    "recurring": "Kunden",
    "personnel": "Mitarbeiter",
    "succession": "Mitarbeiter",
    "legal": "Allgemeine Fragen / Adjustments",
    "process": "Allgemeine Fragen / Adjustments",
}

# answer_feeds_data_key: keyword triggers in German question text
_FEEDS_KEY_MAP: list[tuple[str, str]] = [
    ("wiederkehr", "commercial.recurring.recurring_pct"),
    ("vertragsanteil", "commercial.recurring.recurring_pct"),
    ("top 10 kunden", "commercial.customers.top3_share_pct"),
    ("umsatzverteilung", "commercial.customers.top3_share_pct"),
    ("umsatzaufteilung", "commercial.revenue_split.revenue_split_json"),
    ("geschäftsbereiche", "commercial.revenue_split.revenue_split_json"),
    ("mitarbeiteranzahl", "operational.employees.headcount"),
    ("wie viele mitarbeiter", "operational.employees.headcount"),
    ("gf-gehalt", "financial.adjustments.gf_salary_k"),
    ("geschäftsführergehalt", "financial.adjustments.gf_salary_k"),
    ("gehalt des geschäftsführer", "financial.adjustments.gf_salary_k"),
]


# ─── Public entry point ───────────────────────────────────────────────────────


def generate_rfi(conn, code_name: str, dry_run: bool = False) -> dict[str, Any]:
    """Generate RFI question list for a deal.

    Returns dict with keys:
        code_name, questions, from_corpus, from_data, from_conflicts,
        doc_path, rows_written, dry_run
    """
    ctx = _load_deal_context(conn, code_name)
    domain = ctx["domain"]

    # 1. Build anomaly descriptions from financial data
    financial_rows, anomalies, adjustment_items = _build_financial_summary(conn, domain)

    # 2. Load golden corpus from registered RFI docs + rfi_examples/
    corpus_text = _load_rfi_corpus(conn, exclude_code=code_name)

    # 3. Build pre-formed conflict questions
    conflict_qs = _build_conflict_questions(ctx["conflicts"])

    # 4. Load already-answered questions so Claude doesn't re-ask them
    answered_qs = _load_answered_questions(conn, domain)

    # 5. Build the Claude prompt and call
    prompt = _build_prompt(
        company_name=ctx["company_name"],
        deal_stage=ctx["deal_stage"],
        financial_rows=financial_rows,
        anomalies=anomalies,
        conflict_questions=conflict_qs,
        corpus_text=corpus_text,
        answered_questions=answered_qs,
        adjustment_items=adjustment_items,
    )

    raw = _call_claude(prompt)
    try:
        questions = _parse_questions(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON parse failed on first attempt — retrying Claude call")
        raw = _call_claude(prompt)
        questions = _parse_questions(raw)

    # Tag conflict questions appropriately (pre-formed questions injected in prompt)
    n_conflict = len(conflict_qs)
    n_data = sum(
        1 for q in questions if q["source"].startswith("rfi_generator:account:")
    )
    n_corpus = len(questions) - n_data - n_conflict

    # 5. Write to DB (idempotent)
    rows_written = _write_questions(conn, domain, questions, dry_run)

    # 6. Write PDF document
    folder_path = ctx["folder_path"]
    doc_path = _write_pdf(
        code_name=code_name,
        company_name=ctx["company_name"],
        questions=questions,
        financial_rows=financial_rows,
        folder_path=folder_path,
        dry_run=dry_run,
    )

    return {
        "code_name": code_name,
        "questions": questions,
        "from_corpus": max(0, n_corpus),
        "from_data": n_data,
        "from_conflicts": n_conflict,
        "doc_path": str(doc_path) if doc_path else None,
        "rows_written": rows_written,
        "dry_run": dry_run,
    }


def _load_answered_questions(conn, domain: str) -> list[str]:
    """Return question texts that are already answered or waived — skip in next RFI run."""
    rows = conn.execute(
        "SELECT question FROM deal_questions WHERE domain = ? AND status IN ('answered', 'waived')",
        (domain,),
    ).fetchall()
    return [r["question"] for r in rows]


# ─── Context loader ───────────────────────────────────────────────────────────


def _load_deal_context(conn, code_name: str) -> dict[str, Any]:
    """Load deal metadata and unresolved conflicts."""
    row = conn.execute(
        "SELECT domain, code_name, company_name, deal_stage, folder_path FROM deals WHERE code_name = ?",
        (code_name,),
    ).fetchone()
    if not row:
        raise ValueError(f"Deal not found: {code_name}")

    domain = row["domain"] or code_name.lower()

    # Unresolved conflicts — detect from deal_financials (same key+year, different values)
    conflict_rows = conn.execute(
        """SELECT f1.line_item, f1.fiscal_year, f1.value_k AS val1, f2.value_k AS val2,
                  f1.source AS src1, f2.source AS src2
           FROM deal_financials f1
           JOIN deal_financials f2
             ON f1.domain = f2.domain
            AND f1.statement = f2.statement
            AND f1.line_item = f2.line_item
            AND f1.fiscal_year = f2.fiscal_year
            AND f1.id < f2.id
           WHERE f1.domain = ?
             AND f1.is_adjusted = 0 AND f2.is_adjusted = 0
             AND f1.value_k IS NOT NULL AND f2.value_k IS NOT NULL
             AND ABS(f1.value_k - f2.value_k) > 0.5""",
        (domain,),
    ).fetchall()
    conflicts = [
        {
            "key": r["line_item"],
            "fiscal_year": r["fiscal_year"],
            "value1": r["val1"],
            "value2": r["val2"],
            "source1": r["src1"],
            "source2": r["src2"],
        }
        for r in conflict_rows
    ]

    # Resolve folder path
    folder_path: Path | None = None
    if row["folder_path"]:
        candidate = settings.DEALS_DIR / row["folder_path"]
        if candidate.exists():
            folder_path = candidate
    if folder_path is None:
        for d in settings.DEALS_DIR.iterdir() if settings.DEALS_DIR.exists() else []:
            if f"({code_name})" in d.name:
                folder_path = d
                break

    return {
        "domain": domain,
        "company_name": row["company_name"] or code_name,
        "deal_stage": row["deal_stage"],
        "folder_path": folder_path,
        "conflicts": conflicts,
    }


# ─── Financial summary + anomaly detection ────────────────────────────────────


def _build_financial_summary(
    conn, domain: str
) -> tuple[list[dict], list[str], list[dict]]:
    """Build human-readable financial rows and anomaly descriptions.

    Returns (financial_rows, anomalies, adjustment_items) where:
        financial_rows: list of {year, key, value_num, source_type} for prompt context
        anomalies: list of German-readable anomaly strings
        adjustment_items: list of adjustment/normalization dicts
    """
    rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num, statement, period_type
           FROM deal_financials
           WHERE domain = ?
             AND statement IN ('pnl', 'balance') AND is_adjusted = 0
             AND value_k IS NOT NULL
             AND (fiscal_year IS NULL OR (fiscal_year BETWEEN ? AND ?))
           ORDER BY fiscal_year, line_item""",
        (domain, _YEAR_MIN, _YEAR_MAX),
    ).fetchall()

    pnl_by_year: dict[int | None, dict[str, float]] = {}
    bal_by_year: dict[int | None, dict[str, float]] = {}
    ltm_by_year: dict[int | None, dict[str, float]] = {}
    for r in rows:
        yr = r["fiscal_year"]
        pt = r["period_type"] or "annual"
        if pt in ("ltm",) or pt.startswith("bwa_"):
            target = ltm_by_year
        elif r["statement"] == "balance":
            target = bal_by_year
        else:
            target = pnl_by_year
        if yr not in target:
            target[yr] = {}
        target[yr][r["key"]] = r["value_num"]

    # Load adjustment rows
    adj_rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num, adjustment_note AS value_text
           FROM deal_financials
           WHERE domain = ?
             AND statement = 'adjustments'
             AND (fiscal_year IS NULL OR (fiscal_year BETWEEN ? AND ?))
           ORDER BY fiscal_year, line_item""",
        (domain, _YEAR_MIN, _YEAR_MAX),
    ).fetchall()

    adjustment_items: list[dict] = []
    for r in adj_rows:
        item: dict = {"key": r["key"], "fiscal_year": r["fiscal_year"]}
        if r["value_num"] is not None:
            item["value_num"] = r["value_num"]
        # Parse normalization_items_json if present
        if r["key"] == "normalization_items_json" and r["value_text"]:
            try:
                parsed = json.loads(r["value_text"])
                if isinstance(parsed, list):
                    for entry in parsed:
                        adjustment_items.append(entry)
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
        if r["value_num"] is not None or r["value_text"]:
            adjustment_items.append(item)

    # Build readable financial rows for prompt (P&L + LTM + balance)
    financial_rows: list[dict] = []
    for yr in sorted(k for k in pnl_by_year if k):
        d = pnl_by_year[yr]
        for key in ("revenue", "cogs", "gross_profit", "personnel", "ebitda", "ebit"):
            if key in d:
                financial_rows.append(
                    {"year": yr, "key": key, "value_num": d[key], "source_type": "pnl"}
                )
    # Fix 1: Add LTM (BWA) rows
    for yr in sorted(k for k in ltm_by_year if k):
        d = ltm_by_year[yr]
        for key in ("revenue", "cogs", "gross_profit", "personnel", "ebitda", "ebit"):
            if key in d:
                financial_rows.append(
                    {"year": yr, "key": key, "value_num": d[key], "source_type": "ltm"}
                )
    # Add balance rows
    for yr in sorted(k for k in bal_by_year if k):
        for key, val in bal_by_year[yr].items():
            financial_rows.append(
                {"year": yr, "key": key, "value_num": val, "source_type": "balance"}
            )

    # Anomaly detection
    anomalies: list[str] = []
    sorted_years = sorted(yr for yr in pnl_by_year if yr)

    revenues: dict[int, float] = {}
    ebitdas: dict[int, float] = {}
    personnels: dict[int, float] = {}

    for yr in sorted_years:
        d = pnl_by_year[yr]
        if "revenue" in d:
            revenues[yr] = d["revenue"]
        if "ebitda" in d or "ebitda_adj" in d:
            # Prefer stated ebitda for margin calc, fall back to adj
            ebitdas[yr] = d.get("ebitda") or d.get("ebitda_adj") or 0
        if "personnel" in d:
            personnels[yr] = d["personnel"]

    # Revenue YoY changes
    rev_years = sorted(revenues)
    for i in range(1, len(rev_years)):
        y0, y1 = rev_years[i - 1], rev_years[i]
        r0, r1 = revenues[y0], revenues[y1]
        if r0 and r0 != 0:
            pct = (r1 - r0) / abs(r0) * 100
            if pct > 20:
                anomalies.append(
                    f"Umsatz {y0}→{y1}: starkes Wachstum von {r0:.0f}K€ auf {r1:.0f}K€ (+{pct:.0f}%) — Treiber fragen"
                )
            elif pct < -10:
                anomalies.append(
                    f"Umsatz {y0}→{y1}: Rückgang von {r0:.0f}K€ auf {r1:.0f}K€ ({pct:.0f}%) — Gründe fragen"
                )

    # EBITDA margin flags
    for yr in sorted_years:
        rev = revenues.get(yr)
        ebitda = ebitdas.get(yr)
        if rev and ebitda is not None and rev > 0:
            margin = ebitda / rev * 100
            if margin < 10:
                anomalies.append(
                    f"EBITDA-Marge {yr}: {margin:.1f}% (unter typischer Schwelle) — Normalisierungsanpassungen fragen"
                )

    # Personnel cost high
    for yr in sorted_years:
        rev = revenues.get(yr)
        pers = personnels.get(yr)
        if rev and pers and rev > 0:
            pct = pers / rev * 100
            if pct > 20:
                anomalies.append(
                    f"Personalkosten {yr}: {pers:.0f}K€ = {pct:.0f}% des Umsatzes — GF-Gehalt und Einmalkosten fragen"
                )

    # Balance sheet anomalies
    bal_years = sorted(yr for yr in bal_by_year if yr)
    receivables: dict[int, float] = {}
    liabilities: dict[int, float] = {}
    for yr in bal_years:
        b = bal_by_year[yr]
        if "receivables" in b:
            receivables[yr] = b["receivables"]
        debt_total = (b.get("debt_lt") or 0) + (b.get("debt_st") or 0)
        if debt_total:
            liabilities[yr] = debt_total

    # Receivables YoY growth
    rec_years = sorted(receivables)
    for i in range(1, len(rec_years)):
        y0, y1 = rec_years[i - 1], rec_years[i]
        r0, r1 = receivables[y0], receivables[y1]
        if r0 and r0 != 0:
            pct = (r1 - r0) / abs(r0) * 100
            if pct > 25:
                anomalies.append(
                    f"Forderungen {y0}→{y1}: Anstieg von {r0:.0f}K€ auf {r1:.0f}K€ (+{pct:.0f}%) — Überfälligkeit und Kundenkonzentration fragen"
                )

    # High debt relative to EBITDA
    for yr in bal_years:
        liab = liabilities.get(yr)
        ebitda = ebitdas.get(yr)
        if liab and ebitda and ebitda > 0:
            leverage = liab / ebitda
            if leverage > 3:
                anomalies.append(
                    f"Bankverbindlichkeiten {yr}: {liab:.0f}K€ = {leverage:.1f}x EBITDA — Finanzierungsstruktur und Tilgungsplan fragen"
                )

    # Fix 2: Net debt anomaly — net_debt > 2× EBITDA
    cash_by_year: dict[int, float] = {}
    for yr in bal_years:
        b = bal_by_year[yr]
        if "cash" in b:
            cash_by_year[yr] = b["cash"]

    for yr in bal_years:
        bank_liab = liabilities.get(yr, 0.0) or 0.0
        cash = cash_by_year.get(yr, 0.0) or 0.0
        net_debt = bank_liab - cash
        ebitda = ebitdas.get(yr)
        if ebitda and ebitda > 0 and net_debt > 2 * ebitda:
            threshold = 2 * ebitda
            anomalies.append(
                f"Net Debt {yr}: {net_debt:.0f}K€ (>{threshold:.0f}K€ = 2× EBITDA — fragen nach Finanzierungsstruktur)"
            )

    return financial_rows, anomalies, adjustment_items


# ─── Golden corpus loader ─────────────────────────────────────────────────────


def _load_rfi_corpus(conn, exclude_code: str = "") -> str:
    """Load RFI reference text from:
    1. Golden corpus (config/golden/rfi/)
    2. Registered deal_documents WHERE doc_type='rfi' (other deals)
    3. Legacy config/rfi_examples/ directory (backward compat)

    Returns concatenated text, max ~6000 chars.
    """
    from src.golden import load_golden_text

    texts: list[str] = []

    # 1. Golden corpus
    golden_text = load_golden_text("rfi", exclude_deal=exclude_code, max_chars=4000)
    if golden_text:
        texts.append(golden_text)

    # 2. Registered RFI files from other deals
    rfi_docs = conn.execute(
        """SELECT file_path, file_name, code_name
           FROM deal_documents
           WHERE doc_type = 'rfi' AND code_name != ?
             AND (file_name LIKE '%_v1.docx' OR file_name LIKE '%_vS.docx')
           ORDER BY registered_at DESC""",
        (exclude_code,),
    ).fetchall()

    for doc in rfi_docs:
        text = _extract_docx_text(doc["file_path"], label=doc["file_name"])
        if text:
            texts.append(f"--- {doc['code_name']} / {doc['file_name']} ---\n{text}")

    # 3. Legacy rfi_examples/ (backward compat, will be removed)
    examples_dir = settings.BASE_DIR / "config" / "rfi_examples"
    if examples_dir.exists():
        for p in sorted(examples_dir.iterdir()):
            if p.suffix.lower() == ".docx" and p.name.lower() != "readme.md":
                text = _extract_docx_text(str(p), label=p.name)
                if text:
                    texts.append(f"--- {p.name} ---\n{text}")

    combined = "\n\n".join(texts)
    if len(combined) > 6000:
        combined = combined[:6000] + "\n[...gekürzt]"

    return combined


def _extract_docx_text(file_path: str, label: str = "") -> str:
    """Extract paragraph text from a .docx file. Returns '' on any error."""
    try:
        from docx import Document  # type: ignore

        doc = Document(file_path)
        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Skipping %s: %s", label or file_path, exc)
        return ""


# ─── Conflict question builder ────────────────────────────────────────────────


def _build_conflict_questions(conflicts: list[dict]) -> list[dict]:
    """Generate one German question per unique (key, fiscal_year) conflict pair."""
    questions: list[dict] = []

    grouped: dict[tuple, list[dict]] = {}
    for c in conflicts:
        k = (c["key"], c["fiscal_year"])
        grouped.setdefault(k, []).append(c)

    for (key, year), rows in grouped.items():
        # Find two distinct values
        values = list({r["value_num"] for r in rows if r["value_num"] is not None})
        if len(values) < 2:
            continue

        val_a = values[0]
        val_b = values[1]
        src_a = next((r["source"] for r in rows if r["value_num"] == val_a), "Quelle A")
        src_b = next((r["source"] for r in rows if r["value_num"] == val_b), "Quelle B")
        year_str = str(year) if year else "unbekannt"

        question = (
            f"In {year_str} weicht '{key}' zwischen zwei Quellen ab: "
            f"{src_a} zeigt {val_a:.1f}K€, {src_b} zeigt {val_b:.1f}K€. "
            f"Bitte klären Sie die Differenz."
        )

        questions.append(
            {
                "question": question,
                "category": "financial",
                "subcategory": "adjustments",
                "importance": "high",
                "sort_order": 0,
                "source": "rfi_generator:conflict",
                "answer_feeds_data_key": None,
            }
        )

    return questions


# ─── Claude prompt builder ────────────────────────────────────────────────────


def _build_prompt(
    company_name: str,
    deal_stage: str,
    financial_rows: list[dict],
    anomalies: list[str],
    conflict_questions: list[dict],
    corpus_text: str,
    answered_questions: list[str] | None = None,
    adjustment_items: list[dict] | None = None,
) -> str:
    # Separate rows by source_type
    pnl_rows: list[dict] = []
    ltm_rows: list[dict] = []
    bal_rows: list[dict] = []
    for r in financial_rows:
        st = r.get("source_type", "pnl")
        if st == "balance":
            bal_rows.append(r)
        elif st == "ltm":
            ltm_rows.append(r)
        else:
            pnl_rows.append(r)

    # Build P&L section (Fix 1: separate LTM label)
    fin_lines: list[str] = []

    # P&L years
    pnl_by_year: dict[int, dict[str, float]] = {}
    for r in pnl_rows:
        if r["year"] is not None:
            pnl_by_year.setdefault(r["year"], {})[r["key"]] = r["value_num"]

    sorted_pnl_years = _select_report_years(sorted(pnl_by_year))
    for yr in sorted_pnl_years:
        d = pnl_by_year[yr]
        parts: list[str] = []
        if "revenue" in d:
            parts.append(f"Umsatz {d['revenue']:.0f}K€")
        if "gross_profit" in d:
            gp_margin = ""
            if d.get("revenue") and d["revenue"] > 0:
                gp_margin = f" ({d['gross_profit'] / d['revenue'] * 100:.1f}%)"
            parts.append(f"Rohertrag {d['gross_profit']:.0f}K€{gp_margin}")
        ebitda = d.get("ebitda") or d.get("ebitda_adj")
        if ebitda is not None:
            margin = ""
            if d.get("revenue") and d["revenue"] > 0:
                margin = f" ({ebitda / d['revenue'] * 100:.1f}%)"
            parts.append(f"EBITDA {ebitda:.0f}K€{margin}")
        if "personnel" in d:
            parts.append(f"Personal {d['personnel']:.0f}K€")
        if parts:
            fin_lines.append(f"  {yr}: {', '.join(parts)}")

    # Fix 1: LTM (BWA) rows — labeled to distinguish source
    ltm_by_year: dict[int, dict[str, float]] = {}
    for r in ltm_rows:
        if r["year"] is not None:
            ltm_by_year.setdefault(r["year"], {})[r["key"]] = r["value_num"]

    for yr in sorted(ltm_by_year):
        d = ltm_by_year[yr]
        parts = []
        if "revenue" in d:
            parts.append(f"Umsatz {d['revenue']:.0f}K€")
        if "gross_profit" in d:
            gp_margin = ""
            if d.get("revenue") and d["revenue"] > 0:
                gp_margin = f" ({d['gross_profit'] / d['revenue'] * 100:.1f}%)"
            parts.append(f"Rohertrag {d['gross_profit']:.0f}K€{gp_margin}")
        ebitda = d.get("ebitda") or d.get("ebitda_adj")
        if ebitda is not None:
            margin = ""
            if d.get("revenue") and d["revenue"] > 0:
                margin = f" ({ebitda / d['revenue'] * 100:.1f}%)"
            parts.append(f"EBITDA {ebitda:.0f}K€{margin}")
        if "personnel" in d:
            parts.append(f"Personal {d['personnel']:.0f}K€")
        if parts:
            fin_lines.append(f"  {yr} (LTM/BWA): {', '.join(parts)}")

    # Fix 4: YoY change commentary
    yoy_lines: list[str] = []
    yoy_years = sorted_pnl_years
    for i in range(1, len(yoy_years)):
        y0, y1 = yoy_years[i - 1], yoy_years[i]
        d0, d1 = pnl_by_year[y0], pnl_by_year[y1]
        changes: list[str] = []
        for key, label in [
            ("revenue", "Umsatz"),
            ("gross_profit", "Rohertrag"),
            ("personnel", "Personal"),
            ("ebitda", "EBITDA"),
        ]:
            v0 = d0.get(key) or d0.get(key + "_adj")
            v1 = d1.get(key) or d1.get(key + "_adj")
            if v0 and v1 and abs(v0) > 0:
                pct = (v1 - v0) / abs(v0) * 100
                sign = "+" if pct >= 0 else ""
                changes.append(f"{label} {sign}{pct:.0f}%")
        if changes:
            yoy_lines.append(f"  {y0}→{y1}: {', '.join(changes)}")

    # Fix 2: Net debt per year in fin_lines
    bal_by_year_prompt: dict[int, dict[str, float]] = {}
    for r in bal_rows:
        if r["year"] is not None:
            bal_by_year_prompt.setdefault(r["year"], {})[r["key"]] = r["value_num"]

    net_debt_lines: list[str] = []
    for yr in sorted(bal_by_year_prompt):
        b = bal_by_year_prompt[yr]
        debt_total = (b.get("debt_lt") or 0.0) + (b.get("debt_st") or 0.0)
        cash = b.get("cash") or 0.0
        net_debt = debt_total - cash
        net_debt_lines.append(
            f"  {yr}: Net Debt {net_debt:.0f}K€ (Verbindlichkeiten {debt_total:.0f}K€ - Cash {cash:.0f}K€)"
        )

    # Fix 5: Balance sheet section
    bal_section_lines: list[str] = []
    for yr in sorted(bal_by_year_prompt):
        b = bal_by_year_prompt[yr]
        parts = []
        for key, label in [
            ("total_assets", "Bilanzsumme"),
            ("equity", "Eigenkapital"),
            ("receivables", "Forderungen"),
            ("working_capital", "Working Capital"),
        ]:
            if key in b:
                parts.append(f"{label} {b[key]:.0f}K€")
        if parts:
            bal_section_lines.append(f"  {yr}: {', '.join(parts)}")

    # Assemble financial text with all sections
    all_fin_parts: list[str] = []
    if fin_lines:
        all_fin_parts.append("GuV / P&L:\n" + "\n".join(fin_lines))
    else:
        all_fin_parts.append("GuV / P&L:\n  Keine P&L-Daten verfügbar")

    if yoy_lines:
        all_fin_parts.append("YoY-Veränderungen:\n" + "\n".join(yoy_lines))

    if net_debt_lines:
        all_fin_parts.append("Net Debt:\n" + "\n".join(net_debt_lines))

    if bal_section_lines:
        all_fin_parts.append("Bilanz:\n" + "\n".join(bal_section_lines))

    financial_text = (
        "\n\n".join(all_fin_parts) if all_fin_parts else "  Keine Finanzdaten verfügbar"
    )

    # Fix 3: Adjustment items section
    if adjustment_items:
        adj_lines_rendered = []
        for item in adjustment_items:
            yr_str = f" ({item['fiscal_year']})" if item.get("fiscal_year") else ""
            key = item.get("key") or item.get("name") or "Unbekannt"
            val = item.get("value_num") or item.get("amount")
            val_str = f": {val:.0f}K€" if val is not None else ""
            adj_lines_rendered.append(f"  - {key}{yr_str}{val_str}")
        adj_section = "\nBekannte Adjustierungen:\n" + "\n".join(adj_lines_rendered)
    else:
        adj_section = "\nBekannte Adjustierungen:\n  Keine Adjustierungen bekannt — vollständige Liste anfragen."

    anomaly_text = ""
    if anomalies:
        anomaly_text = "\n".join(f"  - {a}" for a in anomalies)
    else:
        anomaly_text = "  Keine spezifischen Auffälligkeiten erkannt"

    conflict_section = ""
    if conflict_questions:
        conflict_lines = [
            f"  {i + 1}. {q['question']}" for i, q in enumerate(conflict_questions)
        ]
        conflict_section = (
            "\nFolgende Konfliktfragen sind bereits vorgeneriert "
            "(übernehme sie exakt, source='rfi_generator:conflict'):\n"
            + "\n".join(conflict_lines)
        )

    corpus_section = ""
    if corpus_text.strip():
        corpus_section = (
            "\nReferenz-Fragenlisten aus vergleichbaren Deals "
            "(orientiere dich an Struktur, Detailgrad und Ton):\n"
            "--- ANFANG REFERENZ ---\n" + corpus_text + "\n--- ENDE REFERENZ ---"
        )
    else:
        corpus_section = "\n(Keine Referenz-Fragenlisten verfügbar — erstelle professionelle M&A-Fragen.)"

    answered_section = ""
    if answered_questions:
        answered_section = (
            "\nBereits beantwortete Fragen — diese NICHT erneut stellen:\n"
            + "\n".join(f"  - {q}" for q in answered_questions[:20])
        )

    return f"""Du erstellst eine Fragenliste (RFI) für einen M&A-Prozess in Deutschland.
Sprache: Deutsch. Ton: professionell, direkt. Keine generischen Fragen ohne Zahlenbezug.

WICHTIG: Wir (der Käufer) erstellen das Bewertungsmodell selbst. Stelle keine Fragen zu unseren
eigenen Modellannahmen oder Adjustierungen — frage nur nach Informationen, die der Verkäufer
bereitstellen muss (Gehaltsdetails, Kundendaten, Verträge, Mitarbeiterlisten etc.).

Unternehmen: {company_name}
Deal-Status: {deal_stage}

Finanzdaten:
{financial_text}
{adj_section}

Auffälligkeiten, die Fragen erfordern:
{anomaly_text}
{conflict_section}
{answered_section}
{corpus_section}

Erstelle 12-18 Fragen zu noch offenen Punkten. Anforderungen:
- Nur Fragen, die der Verkäufer beantworten kann (keine Fragen zu unseren eigenen Berechnungen)
- Fragen müssen deal-spezifisch sein und konkrete Zahlen aus den Finanzdaten referenzieren
- Orientiere dich an Struktur und Detailgrad der Referenz-Fragenlisten
- Vermeide generische Fragen ohne Zahlenbezug

Struktur (in dieser Reihenfolge):
1. Allgemeine Fragen / Adjustments (GF-Gehalt, Privatfahrzeuge, Einmaleffekte, Normalisierungen)
2. GuV (Umsatzentwicklung, Margenentwicklung, spezifische Kostenpositionen)
3. Bilanz (Verbindlichkeiten, Forderungen, Finanzierungsstruktur)
4. Kunden (Top-10-Verteilung, Wiederkehrquote, Umsatzaufteilung nach Bereichen)
5. Mitarbeiter (Anzahl, Qualifikationen, Fluktuation, GF-Nachfolge)

Gib AUSSCHLIESSLICH ein JSON-Array zurück. Kein Text davor oder danach. Kein Markdown.
Jedes Element:
{{
  "question": "...",
  "category": "financial|commercial|general",
  "subcategory": "adjustments|revenue|costs|balance|customers|revenue_split|personnel|succession|legal",
  "importance": "high|medium",
  "sort_order": 1,
  "source": "rfi_generator",
  "answer_feeds_data_key": null
}}
Verwende source="rfi_generator:account:{{key}}" wenn die Frage direkt aus einem Finanzkennwert abgeleitet ist.
"""


# ─── Claude invocation ────────────────────────────────────────────────────────


def _call_claude(prompt: str) -> str:
    """Call Claude via CLI subprocess (OAuth, no API key). Returns raw stdout."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    for attempt in range(2):
        try:
            result = subprocess.run(
                [_CLAUDE_CMD, "-p", "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI exited {result.returncode}: {result.stderr[:300]}"
                )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            if attempt == 0:
                logger.warning("Claude CLI timeout on attempt 1, retrying...")
                continue
            raise RuntimeError("Claude CLI timed out after 2 attempts")

    raise RuntimeError("Claude CLI failed after retries")


# ─── Response parser ──────────────────────────────────────────────────────────


def _parse_questions(raw: str) -> list[dict]:
    """Parse Claude JSON response → validated question list."""
    text = raw.strip()

    # Strip markdown code fences
    if "```" in text:
        # Extract content between fences
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("["):
                text = cleaned
                break

    # Also strip any leading non-JSON text before '['
    bracket = text.find("[")
    if bracket > 0:
        text = text[bracket:]

    questions: list[dict] = json.loads(text)

    required = {"question", "category", "subcategory", "importance", "source"}
    validated: list[dict] = []
    for i, q in enumerate(questions):
        missing = required - set(q.keys())
        if missing:
            logger.warning("Question %d missing fields %s — skipping", i, missing)
            continue

        # Normalise source
        if not q.get("source"):
            q["source"] = "rfi_generator"

        # Apply answer_feeds_data_key if not set by Claude (None means unset, not intentionally blank)
        if q.get("answer_feeds_data_key") is None:
            q["answer_feeds_data_key"] = _infer_feeds_key(q["question"])

        # Ensure sort_order is int
        q.setdefault("sort_order", i + 1)

        validated.append(q)

    return validated


def _infer_feeds_key(question: str) -> str | None:
    """Map German question text to answer_feeds_data_key."""
    lower = question.lower()
    for keyword, key in _FEEDS_KEY_MAP:
        if keyword in lower:
            return key
    return None


# ─── DB write ─────────────────────────────────────────────────────────────────


def _write_questions(conn, domain: str, questions: list[dict], dry_run: bool) -> int:
    """Idempotent: delete rfi_generator drafts, insert new questions.

    Never touches questions with status='sent'|'answered'|'waived' or source='manual'.
    """
    if dry_run:
        return 0

    conn.execute(
        """DELETE FROM deal_questions
           WHERE domain = ? AND source LIKE 'rfi_generator%' AND status = 'draft'""",
        (domain,),
    )

    now = datetime.now(timezone.utc).isoformat()
    for i, q in enumerate(questions):
        conn.execute(
            """INSERT INTO deal_questions
               (id, domain, question, category, subcategory, importance, source,
                sort_order, status, answer_feeds_data_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (
                str(uuid.uuid4()),
                domain,
                q["question"],
                q["category"],
                q.get("subcategory") or "",
                q.get("importance") or "medium",
                q.get("source") or "rfi_generator",
                q.get("sort_order") or (i + 1),
                q.get("answer_feeds_data_key"),
                now,
            ),
        )
    conn.commit()
    return len(questions)


# ─── Year window helper ───────────────────────────────────────────────────────


def _select_report_years(sorted_years: list[int]) -> list[int]:
    """Return the last 3 fiscal years from a sorted year list.

    Ensures Claude and the PDF table focus on the most recent period rather
    than a long tail of older data.  The 'P' projection year (last + 1) is
    handled separately by the PDF builder.
    """
    return sorted_years[-3:] if len(sorted_years) > 3 else sorted_years


# ─── PDF document writer ──────────────────────────────────────────────────────


def _build_pnl_table_data(
    financial_rows: list[dict],
) -> tuple[list[int], int | None, dict[str, dict[int, float | None]]]:
    """Extract adj. P&L matrix for the PDF summary table.

    Returns:
        actual_years  — last 3 P&L years (sorted)
        proj_year     — actual_years[-1] + 1  (the 'P' column)
        kv            — {metric_key: {year: value_or_None}}
                        Keys: revenue, cogs, gross_profit, personnel, opex, ebitda_adj
    """
    # PDF table uses only annual Jahresabschluss rows — LTM/BWA (partial year) excluded.
    # LTM context is still passed to Claude via _build_prompt for question generation.
    pnl_by_year: dict[int, dict[str, float]] = {}
    for r in financial_rows:
        if r.get("source_type", "pnl") != "pnl":
            continue
        if r["year"] is not None:
            pnl_by_year.setdefault(r["year"], {})[r["key"]] = r["value_num"]

    actual_years = _select_report_years(sorted(pnl_by_year))
    proj_year = (actual_years[-1] + 1) if actual_years else None

    metrics = [
        "revenue",
        "cogs",
        "gross_profit",
        "personnel",
        "opex",
        "ebitda_adj",
        "ebitda",
    ]
    kv: dict[str, dict[int, float | None]] = {m: {} for m in metrics}
    for yr in actual_years:
        d = pnl_by_year.get(yr, {})
        for m in metrics:
            kv[m][yr] = d.get(m)
        # ebitda fallback: prefer ebitda_adj, then ebitda
        if kv["ebitda_adj"][yr] is None:
            kv["ebitda_adj"][yr] = d.get("ebitda")

    return actual_years, proj_year, kv


def _fmt_num(val: float | None, paren_neg: bool = True) -> str:
    """Format K€ value for PDF table. Negative values in parentheses."""
    if val is None:
        return "-"
    if paren_neg and val < 0:
        return f"({abs(val):,.0f})"
    return f"{val:,.0f}"


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.1f}%"


def _cagr(first: float | None, last: float | None, n_years: int) -> str:
    """CAGR over n_years periods. Returns formatted % string."""
    if first is None or last is None or first <= 0 or n_years <= 0:
        return "-"
    rate = (last / first) ** (1 / n_years) - 1
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate * 100:.1f}%"


def _write_pdf(
    code_name: str,
    company_name: str,
    questions: list[dict],
    financial_rows: list[dict],
    folder_path: Path | None,
    dry_run: bool,
) -> Path | None:
    """Generate RFI as PDF: adj. P&L summary table + question list. Repuro brand colours."""
    if dry_run:
        return None

    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab not installed — run: pip install reportlab")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    out_path = _resolve_output_path(code_name, folder_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle(
        "rfi_normal",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=_REPURO_DARK,
    )
    style_intro = ParagraphStyle(
        "rfi_intro",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=_REPURO_DARK,
        spaceBefore=6,
    )
    style_title = ParagraphStyle(
        "rfi_title",
        parent=styles["Normal"],
        fontSize=14,
        leading=18,
        textColor=_REPURO_DARK,
        fontName="Helvetica-Bold",
    )
    style_section = ParagraphStyle(
        "rfi_section",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=_REPURO_WHITE,
        fontName="Helvetica-Bold",
        spaceBefore=10,
    )
    style_q = ParagraphStyle(
        "rfi_q",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=_REPURO_DARK,
        leftIndent=4,
    )

    story = []

    # ── Title ──
    date_str = datetime.now().strftime("%d.%m.%Y")
    story.append(Paragraph(f"{date_str} — {company_name}", style_title))
    story.append(Spacer(1, 4 * mm))

    # ── Adj. P&L summary table ──
    actual_years, proj_year, kv = _build_pnl_table_data(financial_rows)

    if actual_years:
        all_cols = actual_years + ([proj_year] if proj_year else [])
        n_actual = len(actual_years)

        # Column headers: blank label col + year cols + CAGR
        col_labels = (
            ["P&L in €K"]
            + [f"{yr}A" if yr in actual_years else f"{yr}P" for yr in all_cols]
            + [
                f"CAGR ({str(actual_years[0])[-2:]}–{str(actual_years[-1])[-2:]})"
                if actual_years
                else "CAGR"
            ]
        )

        def row(label: str, key: str, is_cost: bool = False) -> list[str] | None:
            vals = [kv[key].get(yr) for yr in actual_years]
            if all(v is None for v in vals):
                return None  # skip rows with no data
            display = [
                _fmt_num((-abs(v) if is_cost and v is not None else v)) for v in vals
            ]
            # P column: no projection data in deal_financials, show "—"
            if proj_year:
                display.append("—")
            # CAGR
            first_val = kv[key].get(actual_years[0]) if actual_years else None
            last_val = kv[key].get(actual_years[-1]) if actual_years else None
            cagr_str = _cagr(first_val, last_val, n_actual - 1) if n_actual > 1 else "-"
            return [label] + display + [cagr_str]

        def kpi_row(
            label: str, numerator_key: str, denominator_key: str = "revenue"
        ) -> list[str] | None:
            vals = []
            for yr in actual_years:
                num = kv[numerator_key].get(yr)
                den = kv[denominator_key].get(yr)
                if num is not None and den and den > 0:
                    vals.append(_fmt_pct(num / den * 100))
                else:
                    vals.append("-")
            if all(v == "-" for v in vals):
                return None
            proj_cell = "—" if proj_year else ""
            return [label] + vals + ([proj_cell] if proj_year else []) + ["-"]

        pnl_rows_data = [
            col_labels,
            row("Total Sales", "revenue"),
            row("Cost of Sales (adj.)", "cogs", is_cost=True),
            row("Gross Margin", "gross_profit"),
            row("Personnel Expenses (adj.)", "personnel", is_cost=True),
            row("OPEX (adj.)", "opex", is_cost=True),
            row("EBITDA (adj.)", "ebitda_adj"),
        ]
        pnl_rows_data = [r for r in pnl_rows_data if r is not None]

        kpi_rows_data: list[list[str]] = []
        tg = kpi_row("Topline growth", "revenue")
        gm = kpi_row("Gross margin %", "gross_profit")
        pex = kpi_row("PEX %", "personnel")
        ebm = kpi_row("EBITDA margin %", "ebitda_adj")
        for kr in [tg, gm, pex, ebm]:
            if kr is not None:
                kpi_rows_data.append(kr)

        # Compute topline growth differently (YoY %, not ratio to revenue)
        if actual_years and len(actual_years) > 1:
            tg_row_idx = next(
                (
                    i
                    for i, r in enumerate(kpi_rows_data)
                    if r and r[0] == "Topline growth"
                ),
                None,
            )
            if tg_row_idx is not None:
                growth_vals = []
                for i, yr in enumerate(actual_years):
                    if i == 0:
                        growth_vals.append("-")
                    else:
                        v0 = kv["revenue"].get(actual_years[i - 1])
                        v1 = kv["revenue"].get(yr)
                        if v0 and v1 and abs(v0) > 0:
                            pct = (v1 - v0) / abs(v0) * 100
                            growth_vals.append(_fmt_pct(pct))
                        else:
                            growth_vals.append("-")
                proj_cell = ["—"] if proj_year else []
                kpi_rows_data[tg_row_idx] = (
                    ["Topline growth"] + growth_vals + proj_cell + ["-"]
                )

        all_table_data = pnl_rows_data + [[""] * len(col_labels)] + kpi_rows_data

        # Column widths: label col wide, year cols equal, CAGR col
        n_cols = len(col_labels)
        page_w = A4[0] - 40 * mm
        label_w = page_w * 0.32
        cagr_w = page_w * 0.14
        year_w = (page_w - label_w - cagr_w) / max(1, n_cols - 2)
        col_widths = [label_w] + [year_w] * (n_cols - 2) + [cagr_w]

        tbl = Table(all_table_data, colWidths=col_widths, repeatRows=1)

        # Determine P-column index (last actual + 1 if proj exists)
        p_col_idx = (
            n_actual + 1 if proj_year else None
        )  # 1-indexed in TableStyle = col index

        ts_cmds = [
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), _REPURO_TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), _REPURO_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (1, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            # Body
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_REPURO_WHITE, _REPURO_GRAY]),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.3, _REPURO_GRAY),
            ("LINEBELOW", (0, 0), (-1, 0), 1, _REPURO_TEAL),
            # Bold label column
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            # Top padding
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]

        # Highlight P-year column
        if p_col_idx is not None:
            ts_cmds += [
                ("BACKGROUND", (p_col_idx, 0), (p_col_idx, 0), _REPURO_TEAL_TEXT),
                ("BACKGROUND", (p_col_idx, 1), (p_col_idx, -1), _REPURO_TEAL_LIGHT),
                ("TEXTCOLOR", (p_col_idx, 1), (p_col_idx, -1), _REPURO_TEAL_TEXT),
                ("FONTNAME", (p_col_idx, 1), (p_col_idx, -1), "Helvetica-BoldOblique"),
            ]

        tbl.setStyle(TableStyle(ts_cmds))
        story.append(tbl)
        story.append(Spacer(1, 5 * mm))

    # ── Intro paragraph ──
    story.append(
        Paragraph(
            "Unsere Kaufpreisberechnung hängt insbesondere von der Größe, Stabilität, "
            "Wachstum und Profitabilität sowie strategischem Mehrwert des Unternehmens ab. "
            "Für eine Erstbewertung ist somit ein möglichst gutes Verständnis dieser Faktoren "
            "wichtig, um Ihnen einen repräsentativen Kaufpreis nennen zu können.",
            style_intro,
        )
    )
    story.append(Spacer(1, 5 * mm))

    # ── Questions by section ──
    section_order = [
        "Allgemeine Fragen / Adjustments",
        "GuV",
        "Bilanz",
        "Kunden",
        "Mitarbeiter",
    ]
    sections: dict[str, list[dict]] = {s: [] for s in section_order}
    other: list[dict] = []

    for q in questions:
        sub = q.get("subcategory") or ""
        section = _SECTION_MAP.get(sub)
        if not section:
            if q["category"] == "financial":
                section = "GuV"
            elif q["category"] == "commercial":
                section = "Kunden"
            else:
                section = "Allgemeine Fragen / Adjustments"
        if section in sections:
            sections[section].append(q)
        else:
            other.append(q)

    for section_title in section_order:
        qs = sections[section_title]
        if not qs:
            continue
        # Section header bar
        sec_tbl = Table(
            [[Paragraph(section_title, style_section)]], colWidths=[A4[0] - 40 * mm]
        )
        sec_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _REPURO_TEAL),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(sec_tbl)
        story.append(Spacer(1, 2 * mm))
        for i, q in enumerate(qs, 1):
            story.append(Paragraph(f"{i}.  {q['question']}", style_q))
            story.append(Spacer(1, 1 * mm))
        story.append(Spacer(1, 3 * mm))

    if other:
        sec_tbl = Table(
            [[Paragraph("Sonstiges", style_section)]], colWidths=[A4[0] - 40 * mm]
        )
        sec_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _REPURO_TEAL),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(sec_tbl)
        story.append(Spacer(1, 2 * mm))
        for i, q in enumerate(other, 1):
            story.append(Paragraph(f"{i}.  {q['question']}", style_q))
            story.append(Spacer(1, 1 * mm))

    doc.build(story)
    logger.info("RFI PDF saved: %s", out_path)
    return out_path


def _resolve_output_path(code_name: str, folder_path: Path | None) -> Path:
    date_str = datetime.now().strftime("%y%m%d")
    filename = f"{date_str}_{code_name}_Fragenliste_DRAFT.pdf"

    if folder_path:
        subdir = folder_path / "1_Unternehmensinformationen"
        if subdir.exists():
            return subdir / filename
        return folder_path / filename

    # Fallback: data/output/
    out_dir = settings.DATA_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / filename


# ─── Source label helper (used by dashboard) ─────────────────────────────────


def source_label(source: str) -> str:
    """Convert source field to display badge label."""
    if source in _SOURCE_LABEL_MAP:
        return _SOURCE_LABEL_MAP[source]
    if source.startswith("rfi_generator:account:"):
        key = source[len("rfi_generator:account:") :]
        return "ACCOUNT:" + key.upper()
    return source.upper()[:15]
