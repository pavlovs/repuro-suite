"""Backfill K1/K2 for MANUAL source records — batched (3 per CLI call)."""

import json
import os
import re
import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.normalize import fix_compliment_text, restore_umlauts_german

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s"
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 3

_GUIDE_PATH = Path(__file__).parent.parent / "src" / "config" / "compliment_guide.md"


def _load_guide() -> str:
    if _GUIDE_PATH.exists():
        return _GUIDE_PATH.read_text(encoding="utf-8")
    return ""


_BATCH_PROMPT_TEMPLATE = """Generate German Kompliment sentences for a Serienbrief for each company below.

{guide_section}

Rules per company:
- Kompliment 1 (K1): opens the letter — references the company's history, longevity, or accumulated expertise
- Kompliment 2 (K2): second paragraph — highlights a specific service concept, product specialisation, or differentiator
- Each exactly one sentence in German, 15-30 words
- Specific to THAT company — use ONLY the website excerpt listed under that company
- No greeting, no sign-off

{companies_block}

Return ONLY a valid JSON array with one object per company, keyed by domain:
[{{"domain": "example.de", "k1": "...", "k2": "..."}}, ...]"""


def _build_companies_block(batch: list[dict]) -> str:
    parts = []
    for i, rec in enumerate(batch, 1):
        parts.append(
            f"=== COMPANY {i}: {rec['domain']} ===\n"
            f"Name: {rec['full_name'] or rec['domain']}\n"
            f"Website excerpt: {(rec['scraped_text'] or '')[:1200]}\n"
        )
    return "\n".join(parts)


def _call_cli_batch(prompt: str) -> Optional[str]:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(
            [
                settings.CLAUDE_CMD,
                "-p",
                "--output-format",
                "text",
                "--model",
                "sonnet",
                "--no-session-persistence",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            env=env,
        )
        if result.returncode != 0:
            logger.warning("CLI error: %s", result.stderr.strip()[:200])
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("CLI timed out (120s)")
        return None
    except Exception as e:
        logger.warning("CLI failed: %s", e)
        return None


def _parse_batch_response(
    text: str, expected_domains: list[str]
) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Parse batch JSON array response. Returns {domain: (k1, k2)}."""
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        bracket_start = text.find("[")
        if bracket_start >= 0:
            depth = 0
            for i, ch in enumerate(text[bracket_start:], bracket_start):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(text[bracket_start : i + 1])
                        except json.JSONDecodeError:
                            pass
                        break

    if data is None:
        results = {}
        for domain in expected_domains:
            k1 = _extract_value_for_domain(text, domain, "k1")
            k2 = _extract_value_for_domain(text, domain, "k2")
            if k1 or k2:
                results[domain] = (k1, k2)
        if results:
            logger.debug("JSON failed, regex extracted %d domains", len(results))
            return results
        logger.warning("Batch JSON parse failed: %s", text[:200])
        return {}

    results = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain", "")).strip()
            k1 = str(item.get("k1", "")).strip() or None
            k2 = str(item.get("k2", "")).strip() or None
            if domain and (k1 or k2):
                if k1:
                    k1 = restore_umlauts_german(k1)
                if k2:
                    k2 = restore_umlauts_german(k2)
                k1, k2 = fix_compliment_text(k1, k2)
                results[domain] = (k1, k2)
    return results


def _extract_value_for_domain(text: str, domain: str, key: str) -> Optional[str]:
    escaped = re.escape(domain)
    pattern = rf"{escaped}.*?{key}[\"']\s*:\s*[\"'](.*?)[\"']"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        val = restore_umlauts_german(m.group(1).strip())
        return val if val else None
    return None


def main():
    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)
    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "BEFORE batch-compliments")

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE source = 'MANUAL' AND klass IN ('A','B')
                 AND (compliment_draft IS NULL OR compliment_draft = ''
                      OR compliment_2 IS NULL OR compliment_2 = '')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()

    records = [dict(r) for r in rows]
    print(
        f"\nMANUAL batch compliments — {len(records)} records, batch size {BATCH_SIZE}"
    )
    print(f"  => {(len(records) + BATCH_SIZE - 1) // BATCH_SIZE} CLI calls")
    print("-" * 60)

    if not records:
        print("  Nothing to do.")
        return

    guide = _load_guide()
    guide_section = f"Style guide:\n{guide}\n" if guide else ""

    filled = 0
    failed_domains = []

    for batch_idx in range(0, len(records), BATCH_SIZE):
        batch = records[batch_idx : batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE

        domains = [r["domain"] for r in batch]
        prompt = _BATCH_PROMPT_TEMPLATE.format(
            guide_section=guide_section,
            companies_block=_build_companies_block(batch),
        )

        print(f"  Batch {batch_num}/{total_batches}: {', '.join(domains)}")
        raw = _call_cli_batch(prompt)
        results = _parse_batch_response(raw, domains)

        for rec in batch:
            d = rec["domain"]
            if d in results:
                k1, k2 = results[d]
                with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
                    pipeline_db.update_compliments(conn, d, k1, k2)
                filled += 1
                print(f"    {d}: OK")
            else:
                failed_domains.append(d)
                print(f"    {d}: FAILED")

        if batch_idx + BATCH_SIZE < len(records):
            time.sleep(1)

    print(f"\n  Filled: {filled}/{len(records)}")
    if failed_domains:
        print(f"  Failed: {len(failed_domains)} — {', '.join(failed_domains)}")

    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "AFTER batch-compliments")


if __name__ == "__main__":
    main()
