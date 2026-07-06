"""HTML dashboard generator — funnel visualization + review UI (M11)."""

from __future__ import annotations

import base64
import http.server
import json
import logging
import os
import socketserver
import sqlite3
import subprocess
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse


from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline.db import get_connection, log_activity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template feature flags — set via CLI flags
# ---------------------------------------------------------------------------
_USE_V2: bool = False
_USE_V1: bool = False
_USE_DEV: bool = False  # --dev flag: serve on separate port, shows [DEV] badge

DASHBOARD_VERSION = "v2.1.21"  # bump on every prod deploy; shown in LIVE badge


def _template_name() -> str:
    """Return the template filename based on the active feature flags."""
    if _USE_V1:
        return "dashboard_v1.html"
    if _USE_V2:
        return "dashboard_v2.html"
    return "dashboard_v2.html"  # v2 is now default (M29 promotion)


# Whitelisted fields for PATCH write-back
_WRITEBACK_FIELDS = frozenset(
    {
        "klass",
        "outreach_status",
        "outreach_sent_at",
        "outreach_comment",
        "followup1_at",
        "followup2_at",
        "followup_comment",
        "gf_email",
        "compliment_draft",
        "compliment_2",
        # M17: approval gate + letter fields
        "approved_for_sendout",
        "region",
        "region_prep",
        "anrede",
        "salutation",
        "owner_name",
        "leistung_text",
        "leistung_absatz_2",
        "mehrwerte",
        "gesellschafter_name",
        "all_gesellschafter",
        "impressum_name",
        "gf_name",
        "street",
        "plz_ort",
        "pipeline_stage",
        "is_subsidiary",
        "is_pe_backed",
        "reclassify_reason",
        "manual_note",
        "sections_reviewed",
        "full_name",
        "name_ueberschrift",
        "name_absatz_1",
        "name_absatz_3",
        "prio",
        "gruppe_1",
        "gruppe_2",
        "gesellschafter_field",
        "gesellschafter_note",
    }
)

# ---------------------------------------------------------------------------
# Dropoff computation
# ---------------------------------------------------------------------------


def _compute_dropoff(rows: list) -> list[dict]:
    """Compute per-stage pass/drop counts for the drop-off view."""
    total = len(rows)
    stages = []

    stages.append(
        {
            "stage": "Ingest",
            "sub": "ORBIS · WLW · Manual",
            "passed": total,
            "dropped": 0,
            "reasons": [],
        }
    )

    filtered_pass = [
        r for r in rows if r["filter_pass"] == 1 or r["filter_pass"] is None
    ]
    filtered_drop = [r for r in rows if r["filter_pass"] == 0]
    reason_counts: dict[str, int] = {}
    for r in filtered_drop:
        reason = r["filter_reason"] or "Unknown"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    stages.append(
        {
            "stage": "Hard Filter",
            "sub": "Branche · Größe · Land",
            "passed": len(filtered_pass),
            "dropped": len(filtered_drop),
            "reasons": [
                {"label": k, "n": v}
                for k, v in sorted(reason_counts.items(), key=lambda x: -x[1])
            ],
        }
    )

    scrape_fail = [r for r in filtered_pass if r["pipeline_stage"] == "scrape_failed"]
    scrape_pass = [r for r in filtered_pass if r["pipeline_stage"] != "scrape_failed"]
    stages.append(
        {
            "stage": "Scrape",
            "sub": "Website + Impressum",
            "passed": len(scrape_pass),
            "dropped": len(scrape_fail),
            "reasons": [{"label": "Domain nicht erreichbar", "n": len(scrape_fail)}]
            if scrape_fail
            else [],
        }
    )

    classified = [r for r in scrape_pass if r["klass"] is not None]
    not_classified = [r for r in scrape_pass if r["klass"] is None]
    klass_d = [r for r in classified if r["klass"] in ("D", "E")]
    klass_pass = [r for r in classified if r["klass"] not in ("D", "E")]
    stages.append(
        {
            "stage": "Classify",
            "sub": "AI · A/B/C/D/E",
            "passed": len(klass_pass),
            "dropped": len(klass_d) + len(not_classified),
            "reasons": [{"label": "D/E — No-fit", "n": len(klass_d)}]
            + (
                [{"label": "Nicht klassifiziert", "n": len(not_classified)}]
                if not_classified
                else []
            ),
        }
    )

    ownership_excluded = [r for r in klass_pass if r["prio"] == "Excluded"]
    ownership_pass = [
        r
        for r in klass_pass
        if r["prio"] != "Excluded" and r["klass"] not in ("D", "E", None)
    ]
    stages.append(
        {
            "stage": "Ownership Gate",
            "sub": "OpenRegister · Blocklist",
            "passed": len(ownership_pass),
            "dropped": len(ownership_excluded),
            "reasons": [
                {"label": "S — Konzerntochter / PE", "n": len(ownership_excluded)}
            ]
            if ownership_excluded
            else [],
        }
    )

    ab_records = [r for r in ownership_pass if r["prio"] == "Prio 1"]
    approved = [r for r in ab_records if r["approved_for_sendout"] == 1]
    not_approved = [r for r in ab_records if r["approved_for_sendout"] != 1]
    stages.append(
        {
            "stage": "Approval",
            "sub": "Manueller Review",
            "passed": len(approved),
            "dropped": len(not_approved),
            "reasons": [
                {"label": "In Bearbeitung / Felder fehlen", "n": len(not_approved)}
            ]
            if not_approved
            else [],
        }
    )

    return stages


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_data(db_path: Path, source_filter: Optional[str] = None) -> dict:
    """Query pipeline.db and return all data needed for the dashboard.

    Args:
        source_filter: if set, only load records matching this source value.

    Returns a dict with keys:
    - records: list[dict] — all company_records as raw dicts (all columns)
    - funnel: dict — {stage: count} for funnel visualization
    - klass_counts: dict — {klass: count}
    - d_reasons: list[dict] — [{reason, count}] for D records (reclassify_reason with filter_reason fallback)
    - source_quality: list[dict] — [{source, A, B, C, D, E, S, total}]
    - size_dist: list[dict] — [{bucket, count}] for A/B records by ma_count
    - age_dist: list[dict] — [{bucket, count}] for A/B records by gesellschafter_age
    - briefaktion_counts: list[dict] — [{briefaktion, total, sent, followup1, followup2, contact, meeting, declined, ...}]
    """
    sf = ""
    sf_and = ""
    sf_params: tuple = ()
    if source_filter:
        sf = " WHERE source = ?"
        sf_and = " AND source = ?"
        sf_params = (source_filter,)

    from src.pipeline.db import ensure_schema

    ensure_schema(db_path)

    with get_connection(db_path) as conn:
        # All records as raw dicts
        if source_filter:
            rows = conn.execute(
                "SELECT * FROM company_records WHERE source = ? ORDER BY full_name",
                sf_params,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM company_records ORDER BY full_name"
            ).fetchall()
        records: list[dict] = []
        for row in rows:
            d = dict(row)
            # Convert any non-serialisable types to strings
            for k, v in d.items():
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    d[k] = str(v)
            records.append(d)

        # Funnel counts
        total = conn.execute(
            "SELECT COUNT(*) FROM company_records" + sf, sf_params
        ).fetchone()[0]
        filtered = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE filter_pass IS NOT NULL"
            + sf_and,
            sf_params,
        ).fetchone()[0]
        scraped = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE pipeline_stage IN ('scraped','scrape_failed','classified','ownership_enriched','ownership_review_needed','ownership_gated','email_enriched')"
            + sf_and,
            sf_params,
        ).fetchone()[0]
        classified = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE klass IS NOT NULL" + sf_and,
            sf_params,
        ).fetchone()[0]
        # Approached = records with a briefaktion (proper BA assignment)
        approached = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE briefaktion IS NOT NULL"
            + sf_and,
            sf_params,
        ).fetchone()[0]

        # Per-klass counts for funnel
        klass_rows = conn.execute(
            "SELECT klass, COUNT(*) as cnt FROM company_records WHERE klass IS NOT NULL"
            + sf_and
            + " GROUP BY klass ORDER BY klass",
            sf_params,
        ).fetchall()
        klass_counts: dict[str, int] = {row[0]: row[1] for row in klass_rows}

        funnel: dict[str, int] = {
            "Total": total,
            "Filtered": filtered,
            "Scraped": scraped,
            "Classified": classified,
        }
        for k in ("A", "B", "C", "D", "E", "S"):
            funnel[k] = klass_counts.get(k, 0)
        funnel["Approached"] = approached

        # Outreach status breakdown (for KPI summary)
        outreach_rows = conn.execute(
            "SELECT outreach_status, COUNT(*) as cnt FROM company_records"
            " WHERE outreach_status IS NOT NULL" + sf_and + " GROUP BY outreach_status",
            sf_params,
        ).fetchall()
        outreach_breakdown: dict[str, int] = {row[0]: row[1] for row in outreach_rows}

        # D-reason breakdown
        d_reason_rows = conn.execute(
            "SELECT COALESCE(reclassify_reason, filter_reason, 'unknown') as reason,"
            " COUNT(*) as cnt FROM company_records WHERE klass = 'D'"
            + sf_and
            + " GROUP BY reason ORDER BY cnt DESC",
            sf_params,
        ).fetchall()
        d_reasons: list[dict] = [
            {"reason": row[0], "count": row[1]} for row in d_reason_rows
        ]

        # Source quality table
        if source_filter:
            sources = [(source_filter,)]
        else:
            sources = conn.execute(
                "SELECT DISTINCT source FROM company_records ORDER BY source"
            ).fetchall()
        source_quality: list[dict] = []
        for src_row in sources:
            src = src_row[0]
            entry: dict = {"source": src, "total": 0}
            for k in ("A", "B", "C", "D", "E", "S"):
                cnt_row = conn.execute(
                    "SELECT COUNT(*) FROM company_records WHERE source = ? AND klass = ?",
                    (src, k),
                ).fetchone()
                entry[k] = cnt_row[0]
                entry["total"] += cnt_row[0]
            source_quality.append(entry)

        # Size distribution (A/B only) — ma_count buckets
        size_buckets = [
            ("<10", "ma_count < 10"),
            ("10-20", "ma_count >= 10 AND ma_count < 20"),
            ("20-40", "ma_count >= 20 AND ma_count < 40"),
            ("40-80", "ma_count >= 40 AND ma_count < 80"),
            ("80+", "ma_count >= 80"),
        ]
        size_dist: list[dict] = []
        for bucket, where in size_buckets:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1' AND {where}"
                + sf_and,
                sf_params,
            ).fetchone()[0]
            size_dist.append({"bucket": bucket, "count": cnt})
        null_cnt = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1' AND ma_count IS NULL"
            + sf_and,
            sf_params,
        ).fetchone()[0]
        if null_cnt:
            size_dist.append({"bucket": "unknown", "count": null_cnt})

        # Age distribution (A/B only) — gesellschafter_age buckets
        age_buckets = [
            ("<40", "gesellschafter_age < 40"),
            ("40-50", "gesellschafter_age >= 40 AND gesellschafter_age < 50"),
            ("50-60", "gesellschafter_age >= 50 AND gesellschafter_age < 60"),
            ("60-70", "gesellschafter_age >= 60 AND gesellschafter_age < 70"),
            ("70+", "gesellschafter_age >= 70"),
        ]
        age_dist: list[dict] = []
        for bucket, where in age_buckets:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1' AND {where}"
                + sf_and,
                sf_params,
            ).fetchone()[0]
            age_dist.append({"bucket": bucket, "count": cnt})
        null_age = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1' AND gesellschafter_age IS NULL"
            + sf_and,
            sf_params,
        ).fetchone()[0]
        if null_age:
            age_dist.append({"bucket": "unknown", "count": null_age})

        # Briefaktion breakdown — {BA: {status: count, sent: count}}
        ba_status_rows = conn.execute(
            "SELECT briefaktion, outreach_status, COUNT(*) as cnt,"
            " SUM(CASE WHEN outreach_sent_at IS NOT NULL AND outreach_sent_at != '' THEN 1 ELSE 0 END) as sent_cnt"
            " FROM company_records WHERE briefaktion IS NOT NULL"
            + sf_and
            + " GROUP BY briefaktion, outreach_status",
            sf_params,
        ).fetchall()
        ba_map: dict[str, dict] = {}
        for row in ba_status_rows:
            ba = row[0]
            status = row[1] or "pending"
            cnt = row[2]
            sent_cnt = row[3]
            if ba not in ba_map:
                ba_map[ba] = {"briefaktion": ba, "total": 0, "sent": 0}
            ba_map[ba][status] = ba_map[ba].get(status, 0) + cnt
            ba_map[ba]["total"] += cnt
            ba_map[ba]["sent"] += sent_cnt
        briefaktion_counts: list[dict] = sorted(
            ba_map.values(), key=lambda x: x["briefaktion"]
        )

        # Dropoff data for v2 Drop-off view
        dropoff_rows = conn.execute(
            "SELECT pipeline_stage, filter_pass, filter_reason, klass, approved_for_sendout, prio"
            " FROM company_records"
        ).fetchall()

    dropoff_stages = _compute_dropoff(dropoff_rows)

    from src.pipeline.check_letter import _REQUIRED_FIELDS

    # Last edited domain from activity_log (fallback for first-load without localStorage)
    last_edited_domain = ""
    try:
        with get_connection(db_path) as conn2:
            row = conn2.execute(
                "SELECT domain FROM activity_log ORDER BY changed_at DESC LIMIT 1"
            ).fetchone()
            if row:
                last_edited_domain = row[0]
    except Exception:
        pass

    return {
        "records": records,
        "funnel": funnel,
        "klass_counts": klass_counts,
        "d_reasons": d_reasons,
        "source_quality": source_quality,
        "size_dist": size_dist,
        "age_dist": age_dist,
        "briefaktion_counts": briefaktion_counts,
        "outreach_breakdown": outreach_breakdown,
        "dropoff": {"stages": dropoff_stages, "total": len(dropoff_rows)},
        "required_fields": [{"field": f, "label": lbl} for f, lbl in _REQUIRED_FIELDS],
        "last_edited_domain": last_edited_domain,
    }


# ---------------------------------------------------------------------------
# Logo helper
# ---------------------------------------------------------------------------


def _load_logo_b64(logo_path: Path) -> str:
    """Return base64-encoded PNG as data URI, or empty string if file missing."""
    if not logo_path.exists():
        return ""
    data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


# ---------------------------------------------------------------------------
# Changelog parser
# ---------------------------------------------------------------------------


import re as _re


def _parse_latest_changelog() -> dict:
    """Parse the most recent entry from ai/CHANGELOG.md.

    Returns {"version": "v2.0.2", "date": "2026-05-06", "sections": {"Added": [...], "Fixed": [...], ...}}
    """
    changelog_path = Path(__file__).parent.parent.parent / "ai" / "CHANGELOG.md"
    try:
        text = changelog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"version": DASHBOARD_VERSION, "date": "", "sections": {}}

    # Find first ## heading (latest entry)
    match = _re.search(r"^## (.+)", text, _re.MULTILINE)
    if not match:
        return {"version": DASHBOARD_VERSION, "date": "", "sections": {}}

    header = match.group(1).strip()
    # Parse "v2.0.2 — 2026-05-06" or similar
    parts = _re.split(r"\s*[—–-]\s*", header, maxsplit=1)
    version = parts[0].strip()
    entry_date = parts[1].strip() if len(parts) > 1 else ""

    # Extract content until next ## or end
    start = match.end()
    next_entry = _re.search(r"^## ", text[start:], _re.MULTILINE)
    block = text[start : start + next_entry.start()] if next_entry else text[start:]

    # Parse ### sections — supports both bullet items and prose paragraphs
    sections: dict[str, list[str]] = {}
    current_section = None
    for line in block.splitlines():
        sec_match = _re.match(r"^### (.+)", line)
        if sec_match:
            current_section = sec_match.group(1).strip()
            sections[current_section] = []
        elif current_section and line.strip().startswith("- "):
            sections[current_section].append(line.strip()[2:])
        elif current_section and line.strip() and not line.strip().startswith("#"):
            sections[current_section].append(line.strip())

    return {"version": version, "date": entry_date, "sections": sections}


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------


def _build_html(
    data: dict, serve_mode: bool, logo_b64: str = "", hubspot_portal_id: int = 0
) -> str:
    """Build self-contained HTML dashboard from template file.

    serve_mode=True: JS uses fetch('/api/data') for live data and enables write-back.
    serve_mode=False: JS reads from embedded JSON constant (read-only).
    Template: src/pipeline/templates/dashboard.html
    """
    from src.pipeline.region_lookup import load_region_mapping

    template_path = Path(__file__).parent / "templates" / _template_name()
    template = template_path.read_text(encoding="utf-8")

    data_json = json.dumps(data, ensure_ascii=False, default=str)
    logo_img = (
        f'<img class="header-logo" src="{logo_b64}" alt="ALLEX">' if logo_b64 else ""
    )

    # Build region mapping JS constant {city_lower: {region, region_prep}}
    mapping_js = {
        city: {"region": region, "region_prep": region_prep}
        for city, (region, region_prep) in load_region_mapping().items()
    }
    region_mapping_json = json.dumps(mapping_js, ensure_ascii=False)

    # Load letter template from config file
    letter_template_path = (
        Path(__file__).parent.parent / "config" / "letter_template.html"
    )
    try:
        letter_template_raw = letter_template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        letter_template_raw = (
            "<p>Letter template not found at src/config/letter_template.html</p>"
        )
    # Escape for JS string embedding (backslash, backtick, newlines)
    letter_template_js = (
        letter_template_raw.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )

    version_str = f"[DEV] {DASHBOARD_VERSION}" if _USE_DEV else DASHBOARD_VERSION
    badge_text = f"{'LIVE' if serve_mode else 'STATIC'} · {version_str}"

    release_notes_json = json.dumps(_parse_latest_changelog(), ensure_ascii=False)

    # BASE_PATH is injected by supervisord (e.g. "/allex"). Caddy strips the
    # prefix before proxying, so the browser must include it in every API call.
    api_base = os.environ.get("BASE_PATH", "").rstrip("/")

    html = (
        template.replace("__DATA_JSON__", data_json)
        .replace("__SERVE_MODE_JS__", "true" if serve_mode else "false")
        .replace("__LIVE_BADGE__", badge_text)
        .replace("__DATE_STR__", date.today().isoformat())
        .replace("__LOGO_IMG__", logo_img)
        .replace("__HUBSPOT_PORTAL_ID__", str(hubspot_portal_id))
        .replace("__REGION_MAPPING_JSON__", region_mapping_json)
        .replace("__LETTER_TEMPLATE__", letter_template_js)
        .replace("__RELEASE_NOTES_JSON__", release_notes_json)
        .replace("__API_BASE__", api_base)
    )
    return html


# ---------------------------------------------------------------------------
# HTTP request handler (serve mode)
# ---------------------------------------------------------------------------


class _DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for --serve mode."""

    # Set by dashboard_cmd before starting server
    _db_path: Path = settings.PIPELINE_DB_PATH
    _html_content: str = ""
    _source_filter: str | None = None
    _logo_b64: str = ""
    _hubspot_portal_id: int = 0

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug("HTTP %s", format % args)

    def _send_auth_challenge(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="ALLEX Dashboard"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _check_auth(self) -> bool:
        """Verify HTTP Basic Auth. If AUTH_USER/AUTH_PASS env vars are unset, allow all (local dev)."""
        user = os.environ.get("AUTH_USER", "")
        password = os.environ.get("AUTH_PASS", "")
        if not user or not password:
            return True
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            self._send_auth_challenge()
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            req_user, req_pass = decoded.split(":", 1)
        except Exception:
            self._send_auth_challenge()
            return False
        if req_user != user or req_pass != password:
            self._send_auth_challenge()
            return False
        return True

    def _json_error(self, code: int, message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._check_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/data":
            self._serve_data()
        elif path.startswith("/api/activity"):
            qs = parse_qs(parsed.query)
            domain_filter = qs.get("domain", [None])[0]
            limit = int(qs.get("limit", ["100"])[0])
            db_path = self.__class__._db_path
            try:
                with get_connection(db_path) as conn:
                    if domain_filter:
                        rows = conn.execute(
                            "SELECT id, domain, actor, field, old_value, new_value, changed_at "
                            "FROM activity_log WHERE domain = ? ORDER BY changed_at DESC LIMIT ?",
                            (domain_filter, limit),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT id, domain, actor, field, old_value, new_value, changed_at "
                            "FROM activity_log ORDER BY changed_at DESC LIMIT ?",
                            (limit,),
                        ).fetchall()
                entries = [dict(r) for r in rows]
            except Exception as exc:
                logger.warning("activity_log query failed: %s", exc)
                entries = []
            content = json.dumps(entries, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/export-leadliste":
            self._export_leadliste(parsed)
        elif path == "/api/export-briefmarken":
            self._export_briefmarken(parsed)
        else:
            self._json_error(404, "Not found")

    def do_PATCH(self) -> None:
        if not self._check_auth():
            return
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        # /api/company/{domain} — single record
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "company":
            domain = parts[2]
            self._patch_company(domain)
        # /api/batch — multiple records
        elif len(parts) == 2 and parts[0] == "api" and parts[1] == "batch":
            self._patch_batch()
        else:
            self._json_error(404, "Not found")

    def do_POST(self) -> None:
        if not self._check_auth():
            return
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "compliment":
            self._post_compliment(parts[2])
        elif len(parts) == 2 and parts[0] == "api" and parts[1] == "ingest-domain":
            self._post_ingest_domain()
        elif len(parts) == 2 and parts[0] == "api" and parts[1] == "export-pdf":
            self._post_export_pdf()
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "re-enrich":
            self._post_re_enrich(parts[2])
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "resolve-parent":
            self._post_resolve_parent(parts[2])
        elif len(parts) == 2 and parts[0] == "api" and parts[1] == "batch-send":
            self._post_batch_send()
        else:
            self._json_error(404, "Not found")

    def _serve_html(self) -> None:
        if _USE_DEV:
            # Hot-reload: re-read template from disk on every request
            data = _load_data(
                self.__class__._db_path,
                source_filter=self.__class__._source_filter,
            )
            html = _build_html(
                data,
                serve_mode=True,
                logo_b64=self.__class__._logo_b64,
                hubspot_portal_id=self.__class__._hubspot_portal_id,
            )
            content = html.encode("utf-8")
        else:
            content = self.__class__._html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_data(self) -> None:
        try:
            data = _load_data(
                self.__class__._db_path,
                source_filter=getattr(self.__class__, "_source_filter", None),
            )
            content = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            logger.exception("Error loading data: %s", exc)
            self._json_error(500, "Internal server error")

    def _export_leadliste(self, parsed) -> None:
        """GET /api/export-leadliste?batch=BA8&all=0 — .xlsx Serienbrief data source."""
        import io as _io  # noqa: PLC0415

        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
        from openpyxl.utils import get_column_letter  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        batch = qs.get("batch", [None])[0] or None
        export_all = qs.get("all", ["0"])[0] == "1"
        db_path = self.__class__._db_path

        _BATCH_ORDER = [
            "BA1",
            "BA2",
            "BA3",
            "BA4",
            "BA5",
            "BA6",
            "BA7",
            "BA8",
            "testbatch",
        ]
        _COLS = [
            ("# (ID)", "_ref_id"),
            ("Name", "full_name"),
            ("Domain", "domain"),
            ("Beschreibung", "reasoning"),
            ("Klass", "klass"),
            ("Priorität", "prio"),
            ("Batch", "briefaktion"),
            ("Freigabe", "approved_for_sendout"),
            ("Anrede", "anrede"),
            ("Salutation", "salutation"),
            ("Ansprechpartner", "owner_name"),
            ("Firmenname Briefkopf", "full_name"),
            ("Name Überschrift", "name_ueberschrift"),
            ("Name Absatz 1", "name_absatz_1"),
            ("Name Absatz 3", "name_absatz_3"),
            ("Straße", "street"),
            ("PLZ Ort", "plz_ort"),
            ("Stadt", "city"),
            ("Region", "region"),
            ("Region Brief", "region_prep"),
            ("Kompliment 1", "compliment_draft"),
            ("Kompliment 2", "compliment_2"),
            ("Leistung 1", "leistung_text"),
            ("Leistung 2", "leistung_absatz_2"),
            ("Mehrwerte", "mehrwerte"),
        ]

        def _bi(ba):
            try:
                return _BATCH_ORDER.index(ba)
            except ValueError:
                return 999

        try:
            with get_connection(db_path) as conn:
                all_refs = conn.execute(
                    "SELECT domain, briefaktion FROM company_records"
                ).fetchall()
                q = "SELECT * FROM company_records WHERE 1=1"
                params: list = []
                if batch:
                    q += " AND briefaktion = ?"
                    params.append(batch)
                if not export_all:
                    q += " AND approved_for_sendout = 1"
                rows = conn.execute(q, params).fetchall()
        except Exception as exc:
            logger.error("export-leadliste DB error: %s", exc)
            self._json_error(500, "Internal server error")
            return

        sorted_refs = sorted(
            all_refs, key=lambda r: (_bi(r["briefaktion"] or ""), r["domain"] or "")
        )
        ref_map = {r["domain"]: i + 1 for i, r in enumerate(sorted_refs)}

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = batch or "Export"

        hdr_fill = PatternFill("solid", fgColor="1A6B6B")
        hdr_font = Font(bold=True, color="FFFFFF")
        hdr_align = Alignment(horizontal="left", vertical="center")

        for ci, (header, _) in enumerate(_COLS, 1):
            c = ws.cell(row=1, column=ci, value=header)
            c.font = hdr_font
            c.fill = hdr_fill
            c.alignment = hdr_align

        for ri, r in enumerate(rows, 2):
            for ci, (_, field) in enumerate(_COLS, 1):
                if field == "_ref_id":
                    val = ref_map.get(r["domain"], "")
                elif field == "approved_for_sendout":
                    val = "Ja" if r[field] else "Nein"
                elif field in ("name_ueberschrift", "name_absatz_1", "name_absatz_3"):
                    val = r[field] if r[field] else (r["full_name"] or "")
                else:
                    val = r[field] if r[field] is not None else ""
                ws.cell(row=ri, column=ci, value=val)

        for ci, (header, _) in enumerate(_COLS, 1):
            ws.column_dimensions[get_column_letter(ci)].width = max(len(header) + 4, 14)

        buf = _io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        content = buf.read()

        scope = "alle" if export_all else "freigegeben"
        fname = f"leadliste_{batch or 'alle'}_{scope}.xlsx"

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _export_briefmarken(self, parsed) -> None:
        """GET /api/export-briefmarken?batch=BA8 — Deutsche Post Briefmarken CSV."""
        import tempfile as _tmpfile  # noqa: PLC0415

        from src.pipeline.export_briefmarken import export_briefmarken  # noqa: PLC0415

        qs = parse_qs(parsed.query)
        batch = qs.get("batch", [None])[0]
        if not batch:
            self._json_error(400, "Missing 'batch' parameter")
            return
        db_path = self.__class__._db_path
        try:
            tmp_dir = Path(_tmpfile.mkdtemp())
            out_path = tmp_dir / f"briefmarken_{batch}.csv"
            result = export_briefmarken(db_path, batch, out_path)
            if result["exported"] == 0:
                self._json_error(404, f"No approved records in batch {batch}")
                return
            content = out_path.read_bytes()
            fname = f"briefmarken_{batch}.csv"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=latin-1")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            logger.exception("export-briefmarken error: %s", exc)
            self._json_error(500, "Internal server error")

    _MAX_BODY_BYTES = 10_485_760  # 10 MB general cap

    def _read_body(self) -> dict:
        raw = self.headers.get("Content-Length", "")
        if not raw or not raw.strip().lstrip("-").isdigit():
            return {}
        length = int(raw)
        if length < 0 or length > self._MAX_BODY_BYTES:
            self._json_error(413, "Request body too large or invalid Content-Length")
            return None  # type: ignore[return-value]
        body = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(body.decode("utf-8"))

    def _patch_company(self, domain: str) -> None:
        try:
            payload = self._read_body()
        except (json.JSONDecodeError, ValueError):
            self._json_error(400, "Invalid JSON body")
            return

        updates = {k: v for k, v in payload.items() if k in _WRITEBACK_FIELDS}
        if not updates:
            self._json_error(400, "No writable fields in payload")
            return

        actor = parse_qs(urlparse(self.path).query).get("actor", ["unknown"])[0]
        db_path = self.__class__._db_path
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [domain]
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(5):
            try:
                with get_connection(db_path) as conn:
                    # Read old values before update for activity log
                    fields_str = ", ".join(updates.keys())
                    old_row = conn.execute(
                        f"SELECT {fields_str} FROM company_records WHERE domain = ?",
                        (domain,),
                    ).fetchone()
                    cursor = conn.execute(
                        f"UPDATE company_records SET {set_clause} WHERE domain = ?",
                        values,
                    )
                    if cursor.rowcount == 0:
                        self._json_error(404, f"Domain not found: {domain}")
                        return
                    if old_row:
                        for i, field in enumerate(updates.keys()):
                            old_val = old_row[i]
                            new_val = updates[field]
                            if str(old_val) != str(new_val):
                                log_activity(
                                    conn,
                                    domain,
                                    actor,
                                    field,
                                    str(old_val) if old_val is not None else None,
                                    str(new_val) if new_val is not None else None,
                                )
                logger.info(
                    "PATCH /api/company/%s: updated %s", domain, list(updates.keys())
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
                return
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" in str(exc).lower() and attempt < 4:
                    logger.warning(
                        "DB locked on attempt %d, retrying in %ds…",
                        attempt + 1,
                        attempt + 1,
                    )
                    time.sleep(attempt + 1)
                else:
                    break
            except Exception as exc:
                last_exc = exc
                break
        logger.exception("DB write error: %s", last_exc)
        self._json_error(500, "Internal server error")

    def _patch_batch(self) -> None:
        """PATCH /api/batch — apply same field updates to multiple domains."""
        try:
            payload = self._read_body()
        except (json.JSONDecodeError, ValueError):
            self._json_error(400, "Invalid JSON body")
            return

        domains = payload.get("domains", [])
        updates = {
            k: v
            for k, v in payload.get("updates", {}).items()
            if k in _WRITEBACK_FIELDS
        }
        if not domains or not updates:
            self._json_error(400, "Need domains[] and updates{}")
            return

        db_path = self.__class__._db_path
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(5):
            try:
                with get_connection(db_path) as conn:
                    for domain in domains:
                        values = list(updates.values()) + [domain]
                        conn.execute(
                            f"UPDATE company_records SET {set_clause} WHERE domain = ?",
                            values,
                        )
                logger.info(
                    "PATCH /api/batch: updated %d records, fields=%s",
                    len(domains),
                    list(updates.keys()),
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"ok": True, "updated": len(domains)}).encode()
                )
                return
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" in str(exc).lower() and attempt < 4:
                    logger.warning(
                        "DB locked on batch attempt %d, retrying in %ds…",
                        attempt + 1,
                        attempt + 1,
                    )
                    time.sleep(attempt + 1)
                else:
                    break
            except Exception as exc:
                last_exc = exc
                break
        logger.exception("Batch write error: %s", last_exc)
        self._json_error(500, "Internal server error")

    def _post_compliment(self, domain: str) -> None:
        try:
            db_path = self.__class__._db_path
            # Fetch company name and leistung_text for prompt
            with get_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT full_name, leistung_text, reasoning FROM company_records WHERE domain = ?",
                    (domain,),
                ).fetchone()
            if not row:
                self._json_error(404, f"Domain not found: {domain}")
                return

            full_name = row["full_name"] or domain
            leistung = row["leistung_text"] or ""
            reasoning = row["reasoning"] or ""

            prompt = (
                f"Schreibe einen kurzen, persönlichen Einstiegssatz (1-2 Sätze) für einen Akquisitionsbrief "
                f"an {full_name}. Bezug auf das Leistungsportfolio: {leistung}. "
                f"Kontext: {reasoning[:300]}. Auf Deutsch, professionell, ohne Floskeln."
            )

            # Run claude CLI subprocess (OAuth; strip API key to prevent SDK-LEAK)
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            result = subprocess.run(
                [settings.CLAUDE_CMD, "-p", "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                env=env,
            )
            compliment = result.stdout.strip() if result.returncode == 0 else ""

            if not compliment:
                self._json_error(500, "claude CLI returned empty output")
                return

            with get_connection(db_path) as conn:
                conn.execute(
                    "UPDATE company_records SET compliment_draft = ? WHERE domain = ?",
                    (compliment, domain),
                )

            logger.info("POST /api/compliment/%s: regenerated compliment", domain)
            content = json.dumps(
                {"compliment_draft": compliment}, ensure_ascii=False
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except subprocess.TimeoutExpired:
            self._json_error(504, "claude CLI timed out")
        except Exception as exc:
            logger.exception("Compliment regen error: %s", exc)
            self._json_error(500, "Internal server error")

    def _post_batch_send(self) -> None:
        """POST /api/batch-send — mark approved records in a batch as sent."""
        body = self._read_body()
        if body is None:
            return
        batch = body.get("batch")
        actor = body.get("actor", "unknown")
        if not batch:
            self._json_error(400, "Missing 'batch' field")
            return
        sent_at = date.today().isoformat()
        db_path = self.__class__._db_path
        try:
            with get_connection(db_path) as conn:
                # Collect candidate domain IDs first (pre-UPDATE snapshot).
                candidates = [
                    r[0]
                    for r in conn.execute(
                        "SELECT domain FROM company_records "
                        "WHERE briefaktion = ? AND approved_for_sendout = 1 "
                        "AND (outreach_sent_at IS NULL OR outreach_sent_at = '')",
                        (batch,),
                    ).fetchall()
                ]
                if not candidates:
                    domains = []
                else:
                    # UPDATE only the rows that were still unsent at SELECT time.
                    # Use an IN clause over the explicit candidate set so concurrent
                    # requests cannot audit rows they didn't actually change.
                    placeholders = ",".join("?" * len(candidates))
                    conn.execute(
                        f"UPDATE company_records SET outreach_sent_at = ? "
                        f"WHERE domain IN ({placeholders}) "
                        f"AND (outreach_sent_at IS NULL OR outreach_sent_at = '')",
                        [sent_at] + candidates,
                    )
                    # Re-query to find exactly which rows were changed by THIS request
                    # (rowcount is unreliable across concurrent connections in WAL mode).
                    domains = [
                        r[0]
                        for r in conn.execute(
                            f"SELECT domain FROM company_records "
                            f"WHERE domain IN ({placeholders}) "
                            f"AND outreach_sent_at = ?",
                            candidates + [sent_at],
                        ).fetchall()
                    ]
                    for domain in domains:
                        log_activity(
                            conn, domain, actor, "outreach_sent_at", "", sent_at
                        )
            updated = len(domains)
            logger.info(
                "batch-send: %s — %d records marked sent by %s", batch, updated, actor
            )
            resp = json.dumps({"updated": updated, "sent_at": sent_at}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except Exception as exc:
            logger.exception("batch-send error: %s", exc)
            self._json_error(500, "Internal server error")

    def _post_export_pdf(self) -> None:
        """POST /api/export-pdf — generate PDF and return as file download."""
        try:
            from src.pipeline.export_pdf import export_pdf_cmd

            domain_filter: list[str] | None = None
            _PDF_MAX_BODY = 1_048_576  # 1 MB cap for export-pdf
            raw_cl = self.headers.get("Content-Length", "")
            content_length = int(raw_cl) if raw_cl.strip().lstrip("-").isdigit() else 0
            if content_length < 0 or content_length > _PDF_MAX_BODY:
                self._json_error(
                    413, "Request body too large or invalid Content-Length"
                )
                return
            if content_length > 0:
                import json as _json

                body = _json.loads(self.rfile.read(content_length))
                domain_filter = body.get("domains")

            out_path = export_pdf_cmd(
                approved_only=True,
                db_path=self.__class__._db_path,
                domain_filter=domain_filter,
            )
            if not out_path or not out_path.exists():
                self._json_error(
                    400,
                    "No approved records to export",
                )
                return
            data = out_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header(
                "Content-Disposition", f'attachment; filename="{out_path.name}"'
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            logger.exception("PDF export error: %s", exc)
            self._json_error(500, "Internal server error")

    def _post_ingest_domain(self) -> None:
        """POST /api/ingest-domain — add one or more domains manually to the pipeline."""
        import hashlib
        from datetime import datetime, timezone

        try:
            payload = self._read_body()
        except (json.JSONDecodeError, ValueError):
            self._json_error(400, "Invalid JSON body")
            return

        raw_domains = payload.get("domains", [])
        if not raw_domains or not isinstance(raw_domains, list):
            self._json_error(400, "domains must be a non-empty list")
            return

        # Normalise domains (strip protocol, www, path)
        import re as _re

        _prefix = _re.compile(r"^(https?://)?(www\.)?", _re.IGNORECASE)

        def _norm(d: str) -> str:
            s = str(d).strip().lower()
            s = _prefix.sub("", s)
            return s.split("/")[0].strip()

        domains = [_norm(d) for d in raw_domains if str(d).strip()]
        domains = list(dict.fromkeys(d for d in domains if d))  # dedupe, preserve order

        added, skipped, details = 0, 0, []
        db_path = self.__class__._db_path
        ingested_at = datetime.now(timezone.utc).isoformat()

        try:
            with get_connection(db_path) as conn:
                for domain in domains:
                    exists = conn.execute(
                        "SELECT 1 FROM company_records WHERE domain = ?", (domain,)
                    ).fetchone()
                    if exists:
                        skipped += 1
                        details.append({"domain": domain, "status": "skipped"})
                        continue
                    rec_id = hashlib.md5(domain.encode()).hexdigest()
                    conn.execute(
                        """INSERT INTO company_records
                           (id, domain, full_name, profile_id, source, pipeline_stage,
                            already_approached, ingested_at)
                           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                        (
                            rec_id,
                            domain,
                            domain,
                            "medtech_germany",
                            "manual",
                            "ingested",
                            ingested_at,
                        ),
                    )
                    added += 1
                    details.append({"domain": domain, "status": "added"})

            logger.info("POST /api/ingest-domain: added=%d skipped=%d", added, skipped)
            result = {"added": added, "skipped": skipped, "details": details}
            content = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            logger.exception("ingest-domain error: %s", exc)
            self._json_error(500, "Internal server error")

    def _post_re_enrich(self, domain: str) -> None:
        """POST /api/re-enrich/{domain} — re-run ownership enrichment with waterfall."""
        from src.pipeline.enrich import re_enrich_single_domain

        try:
            result = re_enrich_single_domain(domain, db_path=self.__class__._db_path)
            content = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            logger.exception("re-enrich error for %s: %s", domain, exc)
            self._json_error(500, "Internal server error")

    def _post_resolve_parent(self, domain: str) -> None:
        """POST /api/resolve-parent/{domain} — UBO lookup on corporate parent entity."""
        from src.pipeline.enrich import resolve_parent_for_domain

        try:
            payload = self._read_body()
        except (json.JSONDecodeError, ValueError):
            self._json_error(400, "Invalid JSON body")
            return

        parent_name = payload.get("parent_name", "").strip()
        if not parent_name:
            self._json_error(400, "parent_name is required")
            return

        try:
            result = resolve_parent_for_domain(
                domain, parent_name, db_path=self.__class__._db_path
            )
            content = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            logger.exception("resolve-parent error for %s: %s", domain, exc)
            self._json_error(500, "Internal server error")


# ---------------------------------------------------------------------------
# Threaded HTTP server (handles concurrent API + UI requests)
# ---------------------------------------------------------------------------


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


def dashboard_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    serve: bool = False,
    port: int = 8080,
    db_path: Optional[Path] = None,
    source_filter: Optional[str] = None,
    no_open: bool = False,
) -> Optional[Path]:
    """Generate HTML dashboard. With --serve, also starts local HTTP server."""
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    if not db_path.exists():
        if serve:
            # Cloud deployment: start server with empty DB until push-db.sh is run
            db_path.parent.mkdir(parents=True, exist_ok=True)
            sqlite3.connect(db_path).close()
            logger.warning("pipeline.db not found — created empty DB at %s", db_path)
        else:
            logger.error("pipeline.db not found at %s — run ingest first.", db_path)
            return None

    label = f" (source={source_filter})" if source_filter else ""
    logger.info("Loading pipeline data from %s%s", db_path, label)
    try:
        data = _load_data(db_path, source_filter=source_filter)
    except sqlite3.OperationalError as exc:
        if serve:
            logger.warning("DB has no schema yet (%s) — serving empty dashboard", exc)
            data = {
                "records": [],
                "funnel": {},
                "klass_counts": {},
                "d_reasons": [],
                "source_quality": [],
                "size_dist": [],
                "age_dist": [],
                "briefaktion_counts": [],
                "outreach_breakdown": {},
                "dropoff": {"stages": [], "total": 0},
                "required_fields": [],
            }
        else:
            raise

    total = len(data["records"])
    klass_summary = " ".join(
        f"{k}:{v}" for k, v in sorted(data["klass_counts"].items())
    )
    logger.info(
        "Loaded %d records. Classifications: %s",
        total,
        klass_summary or "(none)",
    )

    logo_b64 = _load_logo_b64(settings.ALLEX_LOGO_PATH)
    html = _build_html(
        data,
        serve_mode=serve,
        logo_b64=logo_b64,
        hubspot_portal_id=settings.HUBSPOT_PORTAL_ID,
    )

    out_path: Optional[Path] = None
    if not dry_run:
        settings.DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"dashboard_{date.today().strftime('%Y%m%d')}.html"
        out_path = settings.DATA_OUTPUT_DIR / filename
        out_path.write_text(html, encoding="utf-8")
        size_kb = out_path.stat().st_size // 1024
        logger.info("Dashboard written to %s (%d KB)", out_path, size_kb)
        print(f"Dashboard written: {out_path}  ({size_kb} KB)")
    else:
        logger.info("DRY RUN — HTML not written (would be %d chars)", len(html))
        print(f"DRY RUN — dashboard would be {len(html):,} chars")

    if serve:
        _DashboardHandler._db_path = db_path
        _DashboardHandler._source_filter = source_filter
        _DashboardHandler._logo_b64 = logo_b64
        _DashboardHandler._hubspot_portal_id = settings.HUBSPOT_PORTAL_ID
        _DashboardHandler._html_content = _build_html(
            data,
            serve_mode=True,
            logo_b64=logo_b64,
            hubspot_portal_id=settings.HUBSPOT_PORTAL_ID,
        )

        server = _ThreadedHTTPServer(("0.0.0.0", port), _DashboardHandler)
        url = f"http://localhost:{port}"
        logger.info("Dashboard server started at %s (Ctrl+C to stop)", url)
        try:
            import socket as _socket

            lan_ip = _socket.gethostbyname(_socket.gethostname())
        except Exception:
            lan_ip = "unknown"
        print(f"Server running at {url} (network: http://{lan_ip}:{port})")

        if not no_open:

            def _open_browser() -> None:
                import time

                time.sleep(0.5)
                webbrowser.open(url)

            threading.Thread(target=_open_browser, daemon=True).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Dashboard server stopped.")

    return out_path
