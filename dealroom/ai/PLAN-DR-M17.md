# DR-M17: Outside-In Canvas + `/deal-update` Orchestrator

## Summary

Adds `DEALROOM.py draft-canvas --deal <code>` — generates a per-target strategic one-page canvas (market, competition, regulation, customer dynamics, strategic fit, precedents) as a static HTML file, using ALLEX + `dealroom.deals` + `deal_data` as factual seed and WebSearch (via Claude CLI) for outside-in signal. Adds a thin Claude Code slash command `/deal-update <target>` that orchestrates `ingest-docs → extract → draft-canvas` for one target in sequence.

This milestone absorbs the scope of the v4 standalone spec at `CLAUDE_COWORK/docs/superpowers/specs/2026-04-17-cat-deal-support-agent-design.md` — the only additive piece beyond existing dealroom features is the outside-in canvas (open_items ≈ `deal_questions`, scorecard ≈ Overview + Internal Deal Screen, financial extraction ≈ DR-M3, Granola ≈ DR-M11 pending). Blocker consolidation and non-financial document extraction (legal, Q&A, LOI text) are deferred.

**Done when**: `draft-canvas --deal Cat` writes a non-stub HTML file to `{deal_folder}/7_Repuro documents/` with all 6 sections populated, WebSearch citations inline, ALLEX + deal_data values rendered as header facts; `/deal-update Cat` runs the full chain end-to-end with atomic write guarantees.

---

## HOW TO EXECUTE THIS MILESTONE

Planning: run `/plan-milestone` (reads `ai/ROADMAP.md` for scope)
Execution: run `/execute-milestone`

Full protocols: `~/.claude/commands/plan-milestone.md` and `~/.claude/commands/execute-milestone.md`

One commit: `feat(DR-M17): outside-in canvas + /deal-update orchestrator`

---

## Locked Decisions

### Scope

1. **Deliverable split**: (a) `src/generate/canvas.py` + `DEALROOM.py draft-canvas` command, (b) `src/web/search.py` web-search wrapper, (c) `scripts/deal_update.py` orchestrator Python entry, (d) `~/.claude/commands/deal-update.md` slash command. Nothing else.
2. **Deferred out of this milestone** (tracked for DR-M17+):
   - Blocker consolidation across folder-scan + Granola + email (extends `deal_questions` with `category='blocker'`).
   - Non-financial document extraction (LOI/SPA/legal/Q&A → `deal_data category='legal'/'contract'`).
   - Priority-document protection rules from v4 C1 fix (folder classifier + degraded-status semantics for non-financial docs).
   - Gmail UNION query + `secondary_private_search` opt-in from v4 S1 fix.
3. **Granola sync**: DR-M11 is not yet shipped. The orchestrator calls `sync-granola` conditionally (if the subcommand exists in `DEALROOM.py`'s argparse); if not, it prints `"granola sync: not yet implemented (DR-M11)"` and continues. No hard dependency on DR-M11.
4. **Target coverage**: 5 live targets — Cat, Octopus, Lion, Fox, Wolf. Backtest runs on Cat (most mature data, known thesis) + Fox (smaller, less thesis).

### Data sources

5. **Factual seed** (no WebSearch — deterministic from DB):
   - `dealroom.deals`: code_name, company_name, domain, deal_stage, investment_thesis
   - `allex.company_records` via ATTACH (read-only): full_name, services (`leistung_text`), rechtsform, region, city, plz_ort, revenue_tsd_eur, ma_count
   - `dealroom.deal_data` category='financial' subcategory='pnl'/'ltm': revenue, EBITDA, EBITDA margin (latest year)
   - `dealroom.deal_data` category='commercial' subcategory='recurring'/'customers'/'revenue_split'/'segment': recurring %, top-3 concentration, service line split
6. **Outside-in signal** (WebSearch via Claude CLI): per-target queries covering market size (segment), competitors, regulatory environment, customer dynamics, precedent transactions. Hard cap **10 searches per run**, 7-day cache TTL per query-hash. No market-research APIs in V1 (no SimilarWeb, no Crunchbase).
7. **Query construction**: queries built from `leistung_text` + `region` + `deal_data commercial.segment` (if present) + a small per-query template. Example templates:
   - `"{services} Markt Deutschland Wachstum"` — market size
   - `"{services} Wettbewerber {region}"` — competition
   - `"MDR {services} Regulierung 2025"` — regulatory
   - `"Käufer Konsolidierung {customer_type} Deutschland"` — customer dynamics (customer_type inferred from `leistung_text`)
   - `"{services} M&A Transaktion Multiple"` — precedents
   - One generic thesis query: `"{company_name} {services}"` for direct seller mentions

### Model selection

8. **Canvas generation**: Claude **Opus** (quality matters for a strategic narrative read by Roman + investors). One call per run, full canvas drafted in one pass. Follows the "narrative synthesis" model selection rule in `~/.claude/rules/working-style.md`.
9. **Query expansion / parsing**: Claude **Haiku** if needed (cheap, deterministic). Kept minimal — prefer hardcoded templates.
10. **Invocation method**: `claude --via-cli` subprocess with prompt via stdin. Same pattern as DR-M6 (`_call_claude`). `ANTHROPIC_API_KEY` not required. `--tools web_search` passed for the generation call. 180s timeout. Retry once on non-zero exit.

### Canvas structure

11. **6 sections**, fixed order:
    1. **Markt & Segment** — segment size in Germany, growth, relevant sub-segment the target plays in. 3–5 bullets with citations.
    2. **Wettbewerb** — named competitors (regional + national), positioning differentiators. Up to 5 competitors in a table: name | focus | scale indicator (employees/revenue if found) | source.
    3. **Regulatorisches Umfeld** — MDR, KV-Erstattung, DiGA-Adjazenz, other relevant rules. 2–4 bullets with tailwind/headwind label.
    4. **Kundendynamik** — consolidation of buyer base (MVZ, Krankenhäuser, niedergelassene Ärzte), pricing pressure, budget cycles. 2–4 bullets.
    5. **Strategic Fit zu Repuro-These** — maps target attributes to `deals.investment_thesis` as directional matches/gaps. 3–5 bullets. Each tagged as ✅ fit / ⚠️ open / ❌ gap.
    6. **Vergleichbare Transaktionen** — 3–5 precedent M&A deals in adjacent German Medtech distribution/service. Table: target | acquirer | year | indicator (multiple or EV if public) | source.
12. **Header strip** (above sections): `{company_name} | {deal_stage} badge | Revenue €X.XM (year) | EBITDA €X.XK | Services: {leistung_text, truncated 120ch} | Region: {region}` — deterministic from seed data, never WebSearch-derived.
13. **Citations**: every non-trivial claim in sections 1–4 and 6 has a trailing `[{n}]` that links to a footnote list at the bottom (`<ol class="footnotes">` with source URLs + retrieval date). No inline URLs in body text. Section 5 (Strategic Fit) does not cite — it is interpretive and clearly labeled as Repuro judgment.
14. **Visual style**: follows DR-M8 Overview card pattern (teal `#1D7080` accents, `overview-card` class). Inline CSS, no external stylesheets except Leaflet (not needed here). Print-friendly.
15. **Empty-state handling**: if WebSearch returns zero results for a query, the section renders with "Keine belastbaren Quellen gefunden — recherche manuell ergänzen" instead of fabricated content. No hallucinated competitors, no made-up multiples.

### Output path & atomicity

16. **Output path**: `{folder_path}/7_Repuro documents/{date}_{code}_Canvas_DRAFT.html`. If `7_Repuro documents/` does not exist, fall back to `{folder_path}/3_Indikatives Angebot/` (matching DR-M9). If neither exists, create `7_Repuro documents/`.
17. **Atomic write**: write to `{same_dir}/.{filename}.tmp`, `fsync`, validate non-empty + HTML-closing `</html>`, then `os.replace(tmp, final)`. On Windows, set hidden attribute on the `.tmp` sibling via `ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)`. Stale-temp cleanup: any `.tmp` sibling older than 24h at start of run is deleted.
18. **History**: on successful write, existing `{date}_{code}_Canvas_DRAFT.html` (if the filename would collide because the run is same-day) is moved to `{folder_path}/7_Repuro documents/.canvas_history/{timestamp}_{code}_Canvas.html` before overwrite. `.canvas_history/` is gitignored at the dealroom level (dealroom data lives on OneDrive, not git).
19. **Document registration**: after successful write, register the canvas in `deal_documents` with `doc_type='canvas'`, `doc_subtype='outside_in'`. Idempotent on re-run (update `registered_at` if already exists).

### WebSearch cache

20. **Cache path**: `{folder_path}/.cache/canvas_web/{sha256(query)[:12]}.json`. `.cache/` gitignored. JSON shape: `{"query": str, "retrieved_at": ISO-8601, "results": [{"title": str, "url": str, "snippet": str}], "schema_version": 1}`.
21. **TTL**: 7 days. On cache hit within TTL: use cached results, skip web_search call, label in footnote as `(cached YYYY-MM-DD)`. On expired cache: re-query, overwrite. On network failure: fall back to expired cache if available, label `(cached, stale)`, emit warning. If no cache and network fails: section renders empty-state text (see decision 15).
22. **Budget enforcement**: global counter per run, hard-stops at 10 live queries. If 10 cap hit mid-run, remaining queries use cached-only fallback.

### CLI signature

23. `DEALROOM.py draft-canvas --deal <code> [--dry-run] [--no-web] [--force-refresh]`
    - `--dry-run`: print section plan + query list, no HTML write, no web_search calls.
    - `--no-web`: skip WebSearch entirely, render sections 1–4 and 6 as empty-state (useful for offline runs or cache-only regeneration debugging).
    - `--force-refresh`: ignore cache, re-query all 10 slots.
    - Default (no flags): use cache where valid, live-query otherwise.
24. **Exit codes**: 0 on success, 1 on deal-not-found, 2 on output-path-error, 3 on Claude CLI failure after retry.

### `/deal-update` slash command

25. **Location**: `~/.claude/commands/deal-update.md` (user-level, matching `deal-status.md`). Not project-scoped — Roman uses the command from Claude Code root, it cd's into dealroom.
26. **Orchestration sequence** (single slash invocation):
    1. Resolve target: slash argument or ask (same pattern as `/deal-status`).
    2. `cd` to `CLAUDE_REPURO/dealroom/`.
    3. Run `python DEALROOM.py ingest-docs --deal <target>` (existing, DR-M2) — refresh doc registry in case new files landed.
    4. Run `python DEALROOM.py extract --deal <target>` (existing, DR-M3) — refresh financial extraction. Skips if no new docs since last run (DR-M3 handles this).
    5. Run `python DEALROOM.py sync-granola --deal <target>` **if** the subcommand exists; else print placeholder line. No hard DR-M11 dependency.
    6. Run `python DEALROOM.py draft-canvas --deal <target>` — new, this milestone.
    7. Print final summary: "`{target}`: canvas written to {path}. Dashboard: `python DEALROOM.py dashboard --deal {target}`." Done.
27. **Error handling**: any step non-zero exit → halt, print which step failed + suggested remedy. Do not proceed to next step. No partial success claims.
28. **No output parsing**: the slash command does not parse or aggregate outputs from subcommands — it chains them and surfaces stdout + exit codes. This keeps it thin.

### Testing policy

29. **Unit tests** mock `_call_claude` and `web_search` (no live network). Hardcoded JSON/HTML fixtures.
30. **Live backtest** runs on Cat (after unit tests pass) + Fox. Output reviewed manually, embedded in AI Validation Results.
31. **Atomic-write regression test**: spawn subprocess that runs `draft-canvas`, wait for `.tmp` to appear, `proc.terminate()` + `proc.kill()`, then assert: existing canvas (if any) unchanged, no partial HTML on disk.

---

## Plan

> **Forward references**: all `src/web/*`, `src/generate/canvas.py`, `scripts/deal_update.py`, `tests/test_canvas.py`, and the `~/.claude/commands/deal-update.md` slash command are files created by this milestone (see steps below). Any path-lint hook complaining about these should be ignored until after execution. `ai/ARCHITECTURE.md`, `ai/PLAN.md`, `ai/ROADMAP.md` all exist in this folder.

### Step 1 — Create `src/web/` package

Files:
- `src/web/__init__.py` (empty)
- `src/web/search.py`

```python
# src/web/search.py
import hashlib, json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess

CACHE_DIRNAME = ".cache/canvas_web"
TTL_DAYS = 7
BUDGET_PER_RUN = 10

class WebSearchBudget:
    def __init__(self, cap: int = BUDGET_PER_RUN):
        self.cap = cap
        self.used = 0
    def can_spend(self) -> bool:
        return self.used < self.cap
    def spend(self) -> None:
        self.used += 1

def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]

def _cache_path(folder_path: Path, query: str) -> Path:
    return folder_path / CACHE_DIRNAME / f"{_cache_key(query)}.json"

def _read_cache(path: Path) -> dict | None:
    if not path.exists(): return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data.get("schema_version") == 1 else None
    except Exception:
        return None

def _is_fresh(data: dict) -> bool:
    try:
        ts = datetime.fromisoformat(data["retrieved_at"])
        return datetime.now(timezone.utc) - ts < timedelta(days=TTL_DAYS)
    except Exception:
        return False

def _write_cache(path: Path, query: str, results: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "schema_version": 1,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

def run_query(
    query: str,
    folder_path: Path,
    budget: WebSearchBudget,
    force_refresh: bool = False,
    no_web: bool = False,
) -> tuple[list[dict], str]:
    """Returns (results, status) where status ∈ {'cache_fresh','cache_stale','live','empty','skipped'}."""
    path = _cache_path(folder_path, query)
    cached = _read_cache(path)

    if no_web:
        if cached:
            return cached["results"], "cache_stale"
        return [], "skipped"

    if cached and not force_refresh and _is_fresh(cached):
        return cached["results"], "cache_fresh"

    if not budget.can_spend():
        if cached:
            return cached["results"], "cache_stale"
        return [], "empty"

    try:
        results = _claude_web_search(query)
        budget.spend()
        _write_cache(path, query, results)
        return results, "live"
    except Exception:
        if cached:
            return cached["results"], "cache_stale"
        return [], "empty"

def _claude_web_search(query: str) -> list[dict]:
    """Invoke Claude CLI with web_search tool, parse JSON results."""
    prompt = (
        "Perform one web search for the query below and return the top 5 results "
        "as a JSON array. Each element: {\"title\": str, \"url\": str, \"snippet\": str}. "
        "Return ONLY the JSON array, no other text.\n\nQuery: " + query
    )
    proc = subprocess.run(
        ["claude", "--via-cli", "--allowed-tools", "web_search"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr[:200]}")
    raw = proc.stdout.strip()
    if raw.startswith("```"):
        # strip fence + optional json marker
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    return json.loads(raw)
```

### Step 2 — Create `src/generate/canvas.py`

Main entry point + helpers. Sketch:

```python
# src/generate/canvas.py
from datetime import datetime, timezone
from pathlib import Path
import json, subprocess, ctypes, os, sys, time
from src.web.search import WebSearchBudget, run_query

SECTION_SPEC = [
    ("markt_segment", "Markt & Segment", "Markt Deutschland Wachstum"),
    ("wettbewerb", "Wettbewerb", "Wettbewerber"),
    ("regulatorisches_umfeld", "Regulatorisches Umfeld", "MDR Regulierung 2025"),
    ("kundendynamik", "Kundendynamik", "Konsolidierung Käufer Deutschland"),
    ("vergleichbare_transaktionen", "Vergleichbare Transaktionen", "M&A Multiple Transaktion"),
]
# strategic_fit is LLM-interpretive, no WebSearch query

def generate_canvas(
    conn, code_name: str, *,
    dry_run: bool = False,
    no_web: bool = False,
    force_refresh: bool = False,
) -> dict:
    """
    Returns {
      "code_name": str,
      "output_path": str | None,
      "queries_run": int,
      "queries_cached": int,
      "sections_empty": list[str],   # section keys with no sources
      "dry_run": bool,
    }
    """
    ctx = _load_deal_context(conn, code_name)
    queries = _build_queries(ctx)
    budget = WebSearchBudget()
    folder_path = Path(ctx["folder_path"])
    search_results = {}
    stats = {"live": 0, "cache_fresh": 0, "cache_stale": 0, "empty": 0}

    for section_key, query in queries.items():
        results, status = run_query(
            query, folder_path, budget,
            force_refresh=force_refresh, no_web=no_web,
        )
        search_results[section_key] = {"query": query, "results": results, "status": status}
        stats[status] = stats.get(status, 0) + 1

    if dry_run:
        _print_plan(code_name, queries, stats)
        return {
            "code_name": code_name, "output_path": None,
            "queries_run": stats["live"], "queries_cached": stats["cache_fresh"],
            "sections_empty": _empty_sections(search_results),
            "dry_run": True,
        }

    html = _call_claude_canvas(ctx, search_results)
    output_path = _resolve_output_path(folder_path, code_name)
    _atomic_write_html(output_path, html)
    _register_canvas_doc(conn, ctx["domain"], output_path)

    return {
        "code_name": code_name,
        "output_path": str(output_path),
        "queries_run": stats["live"],
        "queries_cached": stats["cache_fresh"],
        "sections_empty": _empty_sections(search_results),
        "dry_run": False,
    }


def _load_deal_context(conn, code_name: str) -> dict:
    """
    Pull: deals row, allex company_record via ATTACH, deal_data commercial.* + financial.pnl latest.
    Fall back to code_name.lower() if deals.domain IS NULL.
    Returns flat dict with keys: code_name, company_name, domain, deal_stage, investment_thesis,
      folder_path, leistung_text, region, city, plz_ort, rechtsform, revenue_latest_k,
      revenue_latest_year, ebitda_latest_k, ebitda_latest_year, recurring_pct, top3_concentration_pct,
      revenue_split_json, ma_count.
    """

def _build_queries(ctx: dict) -> dict[str, str]:
    """Build 6 queries from SECTION_SPEC + one company-specific catchall."""

def _call_claude_canvas(ctx: dict, search_results: dict) -> str:
    """
    Single Opus call. Prompt includes:
      - Header facts (deterministic)
      - Per-section seed: query + top 5 snippets
      - Investment thesis (for strategic fit section)
      - Explicit instruction: do not fabricate; cite via [n]; render full HTML document.
    Returns HTML string.
    """

def _resolve_output_path(folder_path: Path, code_name: str) -> Path:
    """Prefer 7_Repuro documents/, fall back to 3_Indikatives Angebot/."""
    today = datetime.now().strftime("%y%m%d")
    candidates = [
        folder_path / "7_Repuro documents",
        folder_path / "3_Indikatives Angebot",
    ]
    for cand in candidates:
        if cand.exists():
            return cand / f"{today}_{code_name}_Canvas_DRAFT.html"
    target = folder_path / "7_Repuro documents"
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{today}_{code_name}_Canvas_DRAFT.html"

def _atomic_write_html(final_path: Path, html: str) -> None:
    tmp = final_path.parent / f".{final_path.name}.tmp"
    _cleanup_stale_tmp(final_path.parent, max_age_h=24)
    # history: move existing same-name file to .canvas_history/
    if final_path.exists():
        history = final_path.parent / ".canvas_history"
        history.mkdir(exist_ok=True)
        stamp = int(time.time())
        final_path.replace(history / f"{stamp}_{final_path.name}")
    tmp.write_text(html, encoding="utf-8")
    # validate
    if len(html) < 500 or "</html>" not in html.lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Claude returned malformed or truncated HTML")
    if sys.platform == "win32":
        try:
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(tmp), FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass  # hidden attr is nice-to-have, not critical
    os.replace(tmp, final_path)

def _cleanup_stale_tmp(d: Path, max_age_h: int) -> None:
    now = time.time()
    for p in d.glob(".*.tmp"):
        try:
            if now - p.stat().st_mtime > max_age_h * 3600:
                p.unlink()
        except Exception:
            pass

def _register_canvas_doc(conn, domain: str, output_path: Path) -> None:
    """Insert or update deal_documents row with doc_type='canvas', doc_subtype='outside_in'."""

def _empty_sections(search_results: dict) -> list[str]:
    return [k for k, v in search_results.items() if not v["results"]]

def _print_plan(code_name: str, queries: dict, stats: dict) -> None:
    print(f"\n{code_name} — canvas dry-run")
    for k, q in queries.items():
        print(f"  [{k}] {q}")
    print(f"  stats: {stats}")
```

### Step 3 — Canvas prompt

Passed to Opus via stdin. Structure:

```
Du bist Analyst für Repuro, einem Buy-and-Build Käufer im deutschen ambulanten Healthcare-Distribution-Markt.
Sprache: Deutsch. Ton: operator-präzise, faktisch, keine Marketing-Floskeln.

Ziel: Outside-In Canvas für das Target "{company_name}" ({code_name}) als eine HTML-Seite.

Fakten aus Repuro-Daten (KEINE Erfindung, nur nutzen):
- Rechtsform: {rechtsform}
- Sitz: {city}, Region: {region}
- Leistung: {leistung_text}
- Umsatz {revenue_latest_year}: {revenue_latest_k} T€
- EBITDA {ebitda_latest_year}: {ebitda_latest_k} T€
- Mitarbeiter (ALLEX): {ma_count}
- Commercial: Wiederkehrquote {recurring_pct}%, Top-3 Kundenkonzentration {top3_concentration_pct}%

Repuro-These:
{investment_thesis}

Suchergebnisse pro Sektion ([N] = Fußnotennummer für Zitate):

### Markt & Segment
Query: {markt_segment_query}
{snippets_markt_segment}

### Wettbewerb
Query: {wettbewerb_query}
{snippets_wettbewerb}

### Regulatorisches Umfeld
Query: {regulatorisches_umfeld_query}
{snippets_regulatorisches_umfeld}

### Kundendynamik
Query: {kundendynamik_query}
{snippets_kundendynamik}

### Vergleichbare Transaktionen
Query: {vergleichbare_transaktionen_query}
{snippets_vergleichbare_transaktionen}

Anforderungen:
1. Gib EIN vollständiges HTML-Dokument zurück (inkl. <!DOCTYPE html>, <html>, <head>, <body>, schließende Tags).
2. Header-Strip: Firmenname | Stage | Umsatz | EBITDA | Leistung | Region. Werte aus obigen Fakten, keine Erfindung.
3. Sektionen in dieser Reihenfolge: Markt & Segment, Wettbewerb, Regulatorisches Umfeld, Kundendynamik, Strategic Fit zu Repuro-These, Vergleichbare Transaktionen.
4. Für Sektionen 1, 2, 3, 4, 6: nur Aussagen die aus den Suchergebnissen belegbar sind. Jede nicht-triviale Aussage mit Fußnotennummer [N] versehen. Keine Fußnotennummer vergeben ohne passendes Suchergebnis.
5. Für Sektionen OHNE Suchergebnisse: rendere Hinweistext "Keine belastbaren Quellen gefunden — recherche manuell ergänzen". KEINE Erfindung.
6. Strategic Fit (Sektion 5): Interpretation auf Basis der Repuro-These vs. Target-Fakten. 3-5 Bullets, jeder mit ✅ / ⚠️ / ❌. Keine Zitate in dieser Sektion — labeliere sie klar als "Repuro-Einschätzung".
7. Wettbewerb-Tabelle: max 5 Einträge. Spalten: Name | Fokus | Größe (MA/Umsatz falls gefunden) | Quelle [N].
8. Precedent-Tabelle: max 5 Einträge. Spalten: Target | Käufer | Jahr | Indikator | Quelle [N].
9. Footnote-Liste <ol class="footnotes"> am Ende mit allen Quellen. Format: "Titel — URL (abgerufen YYYY-MM-DD)".
10. Design: dezent, Repuro-Farbe #1D7080 für Akzente (Header, Sektions-Unterstriche, Tabellen-Header). Inline-CSS im <style>-Block im <head>. A4-druckbar (max-width: 900px).
11. Keine externen Scripts, keine externen Stylesheets (außer Fonts optional), keine JavaScript.

Gib AUSSCHLIESSLICH das HTML-Dokument zurück. Kein Text davor oder danach, keine Markdown-Fences.
```

Response post-processing: strip ````html fences if present (Opus sometimes wraps despite instructions — same retry pattern as DR-M6 `_parse_questions`).

### Step 4 — Wire `DEALROOM.py draft-canvas`

```python
# In DEALROOM.py
def cmd_draft_canvas(args) -> None:
    from src.generate.canvas import generate_canvas
    conn = get_conn()
    try:
        result = generate_canvas(
            conn, args.deal,
            dry_run=getattr(args, 'dry_run', False),
            no_web=getattr(args, 'no_web', False),
            force_refresh=getattr(args, 'force_refresh', False),
        )
    except DealNotFound:
        print(f"Deal not found: {args.deal}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{result['code_name']}: canvas")
    print(f"  queries live:   {result['queries_run']}")
    print(f"  queries cached: {result['queries_cached']}")
    if result['sections_empty']:
        print(f"  empty sections: {', '.join(result['sections_empty'])}")
    if result['dry_run']:
        print("  [DRY RUN — no HTML written]")
    else:
        print(f"  output: {result['output_path']}")
    conn.close()
```

Argparse:
```python
p_canvas = sub.add_parser("draft-canvas")
p_canvas.add_argument("--deal", required=True)
p_canvas.add_argument("--dry-run", action="store_true")
p_canvas.add_argument("--no-web", action="store_true")
p_canvas.add_argument("--force-refresh", action="store_true")
p_canvas.set_defaults(func=cmd_draft_canvas)
```

### Step 5 — Create `scripts/deal_update.py` orchestrator

```python
# scripts/deal_update.py
"""
Orchestrator for /deal-update slash command.
Runs ingest-docs → extract → sync-granola (if exists) → draft-canvas for one target.
"""
import subprocess, sys
from pathlib import Path

DEALROOM_ROOT = Path(__file__).resolve().parent.parent

def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n=== {label} ===")
    proc = subprocess.run(cmd, cwd=DEALROOM_ROOT)
    if proc.returncode != 0:
        print(f"\n{label} failed with exit {proc.returncode}. Halting.", file=sys.stderr)
        sys.exit(proc.returncode)

def has_subcommand(name: str) -> bool:
    # cheap check: parse `python DEALROOM.py --help` output
    proc = subprocess.run(
        ["python", "DEALROOM.py", "--help"],
        cwd=DEALROOM_ROOT, capture_output=True, text=True,
    )
    return name in (proc.stdout or "")

def main(target: str) -> None:
    run_step("1. Ingest docs", ["python", "DEALROOM.py", "ingest-docs", "--deal", target])
    run_step("2. Extract financials", ["python", "DEALROOM.py", "extract", "--deal", target])
    if has_subcommand("sync-granola"):
        run_step("3. Sync Granola", ["python", "DEALROOM.py", "sync-granola", "--deal", target])
    else:
        print("\n=== 3. Sync Granola ===")
        print("   not yet implemented (DR-M11) — skipping")
    run_step("4. Draft canvas", ["python", "DEALROOM.py", "draft-canvas", "--deal", target])
    print(f"\n{target}: deal-update complete.")
    print(f"   Dashboard: python DEALROOM.py dashboard --deal {target}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/deal_update.py <target>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
```

### Step 6 — Create `~/.claude/commands/deal-update.md`

```markdown
# /deal-update

Refresh one deal end-to-end: ingest new docs, re-extract financials, pull Granola (if available), regenerate outside-in canvas.

## Step 1 — Identify the deal

If the user provided a target code name (Cat, Octopus, Lion, Fox, Wolf): use it.
If not: ask — "Which deal? (code name)"

Resolve code names by querying `SELECT code_name FROM deals` in the dealroom SQLite DB if ambiguous.

## Step 2 — Run the orchestrator

Run from the dealroom directory:

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/dealroom"
python scripts/deal_update.py <target>
```

Surface the output verbatim. The orchestrator halts on any step failure — do not attempt to continue past a non-zero exit.

## Step 3 — Confirm

After success, the orchestrator prints the canvas path and dashboard command. Do not open files or run the dashboard unless Roman asks.

## Rules

- Never modify `dealroom.db` outside the orchestrator.
- If a step fails, surface the exit code and the last 10 lines of stderr. Do not retry automatically.
- Do not invoke this command during a session tagged `[REPURO]` without confirming — it can take 3-5 minutes including WebSearch.
```

### Step 7 — Tests (`tests/test_canvas.py`)

Mock `_call_claude_canvas` and `run_query`. No live network.

1. `test_dry_run_produces_plan` — `dry_run=True` returns dict with `output_path=None`, no HTML written.
2. `test_golden_path_writes_html` — mock returns valid HTML → file exists at expected path, content matches mock.
3. `test_html_validation_rejects_truncated` — mock returns HTML without `</html>` → raises, tmp cleaned up, no file at final path.
4. `test_atomic_write_history_rotation` — second run same day → previous canvas moved to `.canvas_history/`, new canvas at primary path.
5. `test_no_web_flag_uses_only_cache` — cache populated → sections render cached snippets, zero `_claude_web_search` calls.
6. `test_budget_caps_at_10` — 6 queries in spec + thesis query = 7; verify budget never exceeds 10 even on `--force-refresh`.
7. `test_cache_stale_fallback_on_network_error` — `_claude_web_search` raises → cached results returned with status `cache_stale`.
8. `test_output_path_fallback` — `7_Repuro documents/` missing, `3_Indikatives Angebot/` present → canvas written to latter.
9. `test_output_path_creates_primary` — neither target dir exists → `7_Repuro documents/` created + canvas written.
10. `test_empty_section_rendering` — zero results for one section → prompt includes empty-state instruction; test mock-generated HTML contains "Keine belastbaren Quellen gefunden".
11. `test_missing_allex_record` — deal with no ALLEX domain match → `_load_deal_context` returns None for ALLEX fields, canvas still generates (uses dealroom fields only).
12. `test_register_canvas_doc_idempotent` — run twice → one row in `deal_documents` with updated `registered_at`.
13. `test_windows_hidden_attr_on_tmp` — skip on non-win32. On win32: monkeypatch `SetFileAttributesW` to record call, assert called with `0x02`.
14. `test_stale_tmp_cleanup` — pre-create 25h-old `.tmp` sibling → run → sibling deleted before new write.
15. `test_atomic_write_subprocess_kill` — spawn subprocess running `draft-canvas`, wait for `.tmp` to appear (polling), `proc.terminate()+kill()`, verify: final file unchanged (or absent if first run), no corrupt HTML on disk.

Live-only tests (marked `@pytest.mark.live`, skipped in default run):

16. `test_live_cat_canvas` — real Claude CLI + WebSearch on Cat. Assert file exists, file > 3 KB, contains `<ol class="footnotes">`, contains "Medizin & Service".

### Step 8 — Update `ai/ARCHITECTURE.md`

Append to the module map:

```
src/generate/canvas.py  — DR-M17 outside-in canvas generator (Opus + WebSearch)
src/web/search.py       — DR-M17 WebSearch wrapper with 7-day cache
scripts/deal_update.py  — DR-M17 orchestrator called by /deal-update slash command
```

Append to key invariants:

```
10. WebSearch budget hard-caps at 10 live queries per canvas run. Cache TTL 7 days.
11. Canvas HTML writes are atomic (temp + validate + os.replace). Windows hidden attr on tmp.
12. Canvas never fabricates external facts — empty WebSearch → empty-state text, no filler.
```

### Step 9 — Update `ai/ROADMAP.md` + `ai/PLAN.md`

Add DR-M17 row to both milestone tables. Update Current State block in PLAN.md after completion.

---

## Better Engineering Notes

- **Why Opus, not Sonnet**: canvas is read by external stakeholders (investor calls, strategy discussions). The 5-10× cost delta per run (roughly 1 call/day across 5 targets = 5 Opus calls/day) is tolerable. Sonnet's narrative quality on nuanced strategic framing has been observably weaker in prior Consultio work. Revisit after first 10 real runs if Roman judges output overfit to template.
- **WebSearch budget is per-run, not per-deal-per-day**: simpler mental model, and re-running on the same day uses cache for all 7 queries anyway. A budget that rolled over across deals would be operationally confusing.
- **No Granola dependency in V1**: isolating DR-M17 from DR-M11 lets this ship in 2-3 days without waiting. The slash command's conditional sync-granola branch is 5 lines of code — trivial to keep.
- **Why slash command shells out**: keeps the Claude Code surface a thin orchestrator. Logic stays in `DEALROOM.py` where it is testable and callable headlessly. The slash command is the human UX, not the business logic.
- **`.canvas_history/` gitignored**: dealroom data lives on OneDrive and is not versioned in git (per CLAUDE.md). History is for local rollback, not for cross-session reference. Older canvases accumulate — prune manually if disk pressure.
- **No structured JSON intermediate**: canvas is a one-pass HTML render. If a future milestone needs programmatic access to canvas fields (e.g. to feed back into `deal_data`), add a structured JSON emit alongside HTML then. Don't speculatively split now.
- **Cache-key on raw query**: if the prompt template changes, old cache entries become semantically stale but hash-fresh. Accept this — the TTL still hard-evicts after 7 days. Bumping `schema_version` invalidates globally if a template change is substantive.
- **Priority-document protection from v4 C1 is NOT in this milestone**: extraction scope here is read-only (DR-M3 already extracts financials). If DR-M17 adds non-financial extraction, the priority manifest + degraded-status semantics land there. Captured in "Deferred" below.

---

## Deferred (tracked for DR-M17+)

1. **Blocker consolidation**: extend `deal_questions` with `category='blocker'` populated from (a) `deal_documents` flagged `parse_failed` or `truncated`, (b) seller Q&A docs with TODOs, (c) Granola `action_items`. Surfaces in dashboard Open Topics tab.
2. **Non-financial document extraction**: extract legal terms (SPA clauses, LOI deadlines), Q&A answers, contract dates into `deal_data` with `category IN ('legal', 'contract', 'qa')`.
3. **Priority-document protection**: v4 C1 priority manifest — pattern-based (contract_loi, shareholder_cap, debt_tax, seller_qna, vdr_export) with degraded-status flip on any priority-doc truncation.
4. **Gmail UNION query + secondary private search**: v4 S1 fix. Requires an email ingestion module (currently scoped as DR-M10 email composer but only writes, doesn't read).
5. **WebSearch budget per-target-per-week** instead of per-run: if cost grows, shift to weekly budget with cross-run state.

---

## AI Validation Plan

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/dealroom"

# 1. Unit tests (no live network)
python -m pytest tests/ -v -m "not live"
# Expected: 121 existing + ~15 new = ~136 passed

# 2. Dry run on Cat (no web calls, no HTML write)
python DEALROOM.py draft-canvas --deal Cat --dry-run
# Expected:
#   Cat: canvas (plan-only)
#   Queries listed per section
#   stats: all zero (no live/cached, dry_run skips run_query)

# 3. Live canvas on Cat — cold cache
python DEALROOM.py draft-canvas --deal Cat
# Expected:
#   queries live:   7  (6 sections + 1 thesis)
#   queries cached: 0
#   output: .../260419_Cat_Canvas_DRAFT.html
#   wall clock: < 5 min

# 4. Live canvas on Cat — warm cache
python DEALROOM.py draft-canvas --deal Cat --force-refresh=false
# Expected:
#   queries live:   0
#   queries cached: 7
#   wall clock: < 90s (Claude Opus call only)

# 5. Live canvas on Fox — separate target, cold cache
python DEALROOM.py draft-canvas --deal Fox
# Expected similar shape. Verify Fox-specific content in HTML.

# 6. Open both HTML files in browser
# Expected: header strip populated, 6 sections rendered, footnotes list non-empty on Cat,
#           Strategic Fit labeled as Repuro-Einschätzung, no placeholder lorem ipsum.

# 7. Orchestrator
python scripts/deal_update.py Cat
# Expected: 4 steps run (ingest-docs, extract, sync-granola placeholder, draft-canvas),
#           exit 0, canvas path printed.

# 8. Slash command (from Claude Code)
/deal-update Cat
# Expected: same output as step 7, surfaced in Claude Code.

# 9. Atomic-write regression
python -m pytest tests/test_canvas.py::test_atomic_write_subprocess_kill -v
# Expected: pass on Windows.
```

## AI Validation Results

_(filled by executor)_

---

## User Validation Walkthrough

1. `python DEALROOM.py draft-canvas --deal Cat --dry-run` — see the 7 queries the generator will run. Sanity-check that they reference Cat's services (Medizintechnik / Medizin & Service) and region.
2. `python DEALROOM.py draft-canvas --deal Cat` — first live run. Takes 3-5 minutes. Check stdout for "queries live: 7, queries cached: 0" and the output path.
3. Open the HTML file in browser. Verify:
   - Header strip shows Medizin & Service, Chemnitz, revenue + EBITDA from deal_data.
   - 6 sections render. Markt & Segment references German Medtech distribution. Wettbewerber table lists named competitors.
   - Strategic Fit explicitly labeled "Repuro-Einschätzung", maps to Cat thesis.
   - Footnote list at bottom is non-empty with real URLs.
   - Empty sections (if any) show "Keine belastbaren Quellen gefunden" — not hallucinated content.
4. Second run: `python DEALROOM.py draft-canvas --deal Cat`. Should complete in < 90 seconds (cache hit on all 7 queries, only Opus call).
5. `python scripts/deal_update.py Cat` — full orchestration. Verify: ingest-docs runs, extract runs, sync-granola placeholder line appears, draft-canvas writes canvas.
6. From Claude Code: `/deal-update Fox`. Same flow, different target. Verify canvas appears in Fox's OneDrive folder under `7_Repuro documents/`.
7. Dashboard: `python DEALROOM.py dashboard --deal Cat` — canvas registered in `deal_documents` as `doc_type='canvas'`, visible in Documents tab.

Pass criteria: one canvas per target, non-stub content, cached re-runs are fast, no corrupted HTML under kill-test.

---

## Open questions (for project owner)

1. **Model cost**: Opus at 5-10× Sonnet is a real delta. 5 targets × 1 canvas/week = ~20 canvas generations/month, plus cache-miss re-runs. Roughly $15–30/month incremental. Acceptable, or prefer Sonnet default with Opus opt-in via `--quality=opus`?
2. **WebSearch tool surface**: I've assumed Claude CLI exposes `web_search` via `--allowed-tools web_search`. If that flag name differs or the CLI currently doesn't support tool-scoping, the `src/web/search.py` implementation needs adjustment. Should I verify against a live CLI before coding Step 1, or proceed on the assumed contract and fix on first live run?
3. **Precedent transactions**: German Medtech distribution M&A comps are sparse and often private. Section 6 may render empty-state on most targets. Acceptable, or should the prompt include a fallback "list public Medtech distribution acquisitions in Europe if no German ones found"?

Recommend: default-Opus + "fix WebSearch contract on first live run" + allow European fallback for precedents. Course-correct after first 2-3 runs on real deals.
