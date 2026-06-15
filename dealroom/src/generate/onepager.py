"""
DR-M9: One-pager quadrant text generator.

Generates investor-ready bullets for Q1 (Executive Summary), Q3 (Process & Status),
and Q4 (Service Portfolio) using style guides from the golden corpus.
Claude invocation: claude CLI subprocess (OAuth, no API key).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_CLAUDE_CMD: str = (
    shutil.which("claude") or r"C:\Users\X1\AppData\Roaming\npm\claude.cmd"
)

_GUIDE_DIR = Path(__file__).parent.parent.parent / "config" / "golden" / "onepager"

_GUIDE_FILES = {
    "q1": _GUIDE_DIR / "guide-q1-exec-summary.md",
    "q3": _GUIDE_DIR / "guide-q3-process-status.md",
    "q4": _GUIDE_DIR / "guide-q4-service-portfolio.md",
}


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


# ─── Deal context loader ──────────────────────────────────────────────────────


def _gather_deal_context(conn, code_name: str) -> dict[str, Any]:
    """Gather all deal data needed for generation prompts."""
    deal = conn.execute(
        "SELECT * FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not deal:
        raise ValueError(f"Deal not found: {code_name}")

    domain = deal["domain"] or deal["code_name"].lower()

    ctx: dict[str, Any] = {
        "code_name": deal["code_name"],
        "company_name": deal["company_name"],
        "deal_stage": deal["deal_stage"],
        "stage_entered_at": deal["stage_entered_at"],
        "last_contact_at": deal["last_contact_at"],
        "investment_thesis": deal["investment_thesis"],
        "seller_motivation": deal["seller_motivation"],
        "description": deal["description"] or "",
    }

    # Financial snapshot — most recent value per metric
    for metric in ("gesamtleistung", "revenue"):
        row = conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND line_item = ?
                 AND period_type = 'annual' AND is_adjusted = 0 AND value_k IS NOT NULL
               ORDER BY fiscal_year DESC LIMIT 1""",
            (domain, metric),
        ).fetchone()
        if row:
            ctx.setdefault("revenue_k", row["value_k"])
            ctx.setdefault("revenue_year", row["fiscal_year"])

    # EBITDA — prefer adjusted, fallback to raw
    for adj in (1, 0):
        row = conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND line_item = 'ebitda'
                 AND period_type = 'annual' AND is_adjusted = ? AND value_k IS NOT NULL
               ORDER BY fiscal_year DESC LIMIT 1""",
            (domain, adj),
        ).fetchone()
        if row:
            ctx["ebitda_k"] = row["value_k"]
            ctx["ebitda_year"] = row["fiscal_year"]
            break

    # EBITDA margin
    rev = ctx.get("revenue_k")
    ebitda = ctx.get("ebitda_k")
    if rev and ebitda and rev != 0:
        ctx["ebitda_margin_pct"] = round(ebitda / rev * 100, 1)

    # Revenue CAGR — prefer gesamtleistung, fallback to revenue
    rev_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND line_item = 'gesamtleistung'
             AND period_type = 'annual' AND is_adjusted = 0 AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    if len(rev_rows) < 2:
        rev_rows = conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl'
                 AND line_item = 'revenue'
                 AND period_type = 'annual' AND is_adjusted = 0 AND value_k IS NOT NULL
               ORDER BY fiscal_year""",
            (domain,),
        ).fetchall()
    if len(rev_rows) >= 2:
        first, last = rev_rows[0]["value_k"], rev_rows[-1]["value_k"]
        n = rev_rows[-1]["fiscal_year"] - rev_rows[0]["fiscal_year"]
        if n > 0 and first > 0 and last > 0:
            ctx["revenue_cagr"] = round((last / first) ** (1 / n) - 1, 4)
            ctx["cagr_period"] = (
                f"{rev_rows[0]['fiscal_year']}-{rev_rows[-1]['fiscal_year']}"
            )

    # Commercial KPIs
    for kpi in ("recurring_pct", "top3_share_pct", "headcount"):
        row = conn.execute(
            """SELECT value_num FROM deal_commercial
               WHERE domain = ? AND metric = ? AND value_num IS NOT NULL
               ORDER BY fiscal_year DESC LIMIT 1""",
            (domain, kpi),
        ).fetchone()
        if row:
            ctx[kpi] = row["value_num"]

    # Valuation
    val = conn.execute(
        """SELECT ev_mid, ev_low, ev_high, earnout_max, ebitda_basis, valuation_date
           FROM deal_valuations WHERE domain = ? ORDER BY created_at DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    if val:
        ctx["valuation"] = {
            k: val[k]
            for k in (
                "ev_mid",
                "ev_low",
                "ev_high",
                "earnout_max",
                "ebitda_basis",
                "valuation_date",
            )
        }

    # ALLEX data (attached DB — graceful degradation if not available)
    try:
        allex = conn.execute(
            """SELECT leistung_text, region, city, ma_count, rechtsform
               FROM allex.company_records WHERE domain = ? LIMIT 1""",
            (domain,),
        ).fetchone()
        if allex:
            ctx["allex"] = {
                k: allex[k]
                for k in ("leistung_text", "region", "city", "ma_count", "rechtsform")
            }
    except Exception:
        pass

    # RFI question counts by status
    q_counts = conn.execute(
        """SELECT status, COUNT(*) as cnt FROM deal_questions
           WHERE domain = ? GROUP BY status""",
        (domain,),
    ).fetchall()
    ctx["questions"] = {r["status"]: r["cnt"] for r in q_counts}

    return ctx


# ─── Prompt builder ───────────────────────────────────────────────────────────


def _build_prompt(quadrant: str, guide_text: str, deal_ctx: dict) -> str:
    """Build the generation prompt for a specific quadrant."""
    ctx_json = json.dumps(deal_ctx, ensure_ascii=False, default=str, indent=2)
    return f"""You are generating investor one-pager content for a German M&A deal.

## Style Guide
{guide_text}

## Deal Data
```json
{ctx_json}
```

## Instructions
Generate the bullets for this quadrant based on the style guide and deal data above.
Output ONLY the bullet list — no headers, no commentary, no markdown code fences.
Each bullet starts with "- " on its own line.
Use the code name "{deal_ctx["code_name"]}" — never the real company name in the output.
If data is missing for a required topic, write: "- [DATA MISSING — to be completed manually]"
Language: English. German domain terms (Gesamtleistung, Sofortzahlung, etc.) are acceptable.
"""


# ─── Public entry point ───────────────────────────────────────────────────────


def generate_onepager(
    conn,
    code_name: str,
    quadrants: list[str] | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Generate one-pager bullets for specified quadrants.

    Returns dict mapping quadrant name to generated text.
    Skips generation if onepager_edited_at > onepager_generated_at unless force=True.
    """
    if quadrants is None:
        quadrants = ["q1", "q3", "q4"]

    deal = conn.execute(
        "SELECT * FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not deal:
        raise ValueError(f"Deal not found: {code_name}")

    # Re-generation guard — don't overwrite manual edits
    if not force:
        edited = deal["onepager_edited_at"]
        generated = deal["onepager_generated_at"]
        if edited and generated and edited > generated:
            logger.info(
                "Skipping %s: edited_at (%s) > generated_at (%s). Use force=True to override.",
                code_name,
                edited,
                generated,
            )
            return {}

    deal_ctx = _gather_deal_context(conn, code_name)
    results: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat()

    for q in quadrants:
        if q not in _GUIDE_FILES:
            logger.warning("Unknown quadrant: %s", q)
            continue

        guide_path = _GUIDE_FILES[q]
        if not guide_path.exists():
            logger.error("Guide file not found: %s", guide_path)
            continue

        guide_text = guide_path.read_text(encoding="utf-8")
        prompt = _build_prompt(q, guide_text, deal_ctx)

        logger.info("Generating %s for %s...", q, code_name)
        text = _call_claude(prompt)

        if not text:
            logger.error("Empty response for %s", q)
            continue

        results[q] = text

        # Persist to DB
        col = f"onepager_{q}"
        conn.execute(
            f"UPDATE deals SET {col} = ? WHERE code_name = ?",
            (text, code_name),
        )
        # Reset approval flag on re-generation
        approved_col = f"onepager_{q}_approved"
        conn.execute(
            f"UPDATE deals SET {approved_col} = 0 WHERE code_name = ?",
            (code_name,),
        )

    if results:
        conn.execute(
            "UPDATE deals SET onepager_generated_at = ? WHERE code_name = ?",
            (now, code_name),
        )
        conn.commit()
        logger.info("Generated %s for %s", list(results.keys()), code_name)

    return results
