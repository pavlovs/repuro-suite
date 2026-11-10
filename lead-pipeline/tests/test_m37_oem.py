"""M37: OEM profile (klass_oem D1/D2/C/D), OEM scrape, rescan selection, BA11 tagging.

Temp DBs and a mocked Claude CLI only. Never touches data/pipeline.db.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from src.config import settings
from src.config.profile import load_profile, resolve_profile_path
from src.pipeline import classify as classify_mod
from src.pipeline import db as pipeline_db
from src.pipeline import scrape as scrape_mod
from src.pipeline.dashboard import _WRITEBACK_FIELDS, _check_oem_value
from src.utils import web

ROOT = Path(__file__).resolve().parents[1]
OEM_PROFILE = load_profile(ROOT / "profiles" / "oem_germany.json")
AMB_PROFILE = load_profile(ROOT / "profiles" / "medtech_germany.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    return db_path


def _insert(db_path: Path, domain: str, **fields: object) -> None:
    row = {
        "id": domain,
        "domain": domain,
        "full_name": fields.pop("full_name", f"{domain} GmbH"),
        "profile_id": "medtech_germany",
        "source": fields.pop("source", "WLW"),
        "ingested_at": "2026-11-10T00:00:00+00:00",
    }
    row.update(fields)
    cols = ", ".join(row)
    qs = ", ".join("?" for _ in row)
    with pipeline_db.get_connection(db_path) as conn:
        conn.execute(f"INSERT INTO company_records ({cols}) VALUES ({qs})", list(row.values()))


def _get(db_path: Path, domain: str) -> sqlite3.Row:
    with pipeline_db.get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM company_records WHERE domain = ?", (domain,)).fetchone()


LONG_TEXT = "Wir sind ein Hersteller von Medizinprodukten. " * 10  # > 200 chars


# ---------------------------------------------------------------------------
# T1 schema, T2 profile
# ---------------------------------------------------------------------------


def test_schema_has_oem_columns(tmp_db: Path) -> None:
    with pipeline_db.get_connection(tmp_db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(company_records)")}
    assert {"klass_oem", "klass_oem_reason"} <= cols


def test_profile_alias_and_path_form() -> None:
    assert resolve_profile_path("oem").name == "oem_germany.json"
    assert resolve_profile_path("OEM").name == "oem_germany.json"
    assert resolve_profile_path("profiles/medtech_germany.json") == Path("profiles/medtech_germany.json")


def test_ambulatory_profile_defaults_unchanged() -> None:
    assert AMB_PROFILE.classification.mode == "ambulatory"
    assert AMB_PROFILE.classification.max_text_chars == 2000
    assert AMB_PROFILE.scrape.extra_paths is None
    assert AMB_PROFILE.scrape.max_chars == 2500
    assert OEM_PROFILE.classification.mode == "oem"
    assert OEM_PROFILE.scrape.max_chars == 4000
    assert OEM_PROFILE.classification.max_text_chars == 4000


def test_cli_default_profile_is_medtech_and_no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A7: `pipeline.py classify` keeps medtech_germany and passes model=None."""
    captured: dict = {}

    def fake_classify_cmd(profile, **kwargs):  # noqa: ANN001, ANN003
        captured["profile_id"] = profile.id
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(classify_mod, "classify_cmd", fake_classify_cmd)
    spec = importlib.util.spec_from_file_location("pipeline_cli", ROOT / "pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "classify", "--dry-run"])
    mod.main()
    assert captured["profile_id"] == "medtech_germany"
    assert captured["model"] is None
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "classify", "--profile", "oem", "--model", "haiku", "--dry-run"])
    mod.main()
    assert captured["profile_id"] == "oem_germany"
    assert captured["model"] == "haiku"


# ---------------------------------------------------------------------------
# T4 prompt, leave-one-out, parser, argv
# ---------------------------------------------------------------------------


def test_oem_prompt_has_class_defs_and_d2_rule() -> None:
    prompt = classify_mod._build_oem_prompt(OEM_PROFILE, "X GmbH", "x.de", "Berlin", LONG_TEXT)
    for k in ("D1 = ", "D2 = ", "C = ", "D = "):
        assert k in prompt
    assert "Assign D2 only when the text states own production or a plant" in prompt
    assert "OEM-light (target)" in prompt and "OEM-heavy" in prompt


def test_oem_prompt_text_cap_4000() -> None:
    text = "a" * 6000
    prompt = classify_mod._build_oem_prompt(OEM_PROFILE, "X GmbH", "x.de", None, text)
    assert "a" * 4000 in prompt and "a" * 4001 not in prompt


def test_leave_one_out_drops_own_example() -> None:
    for dom in ("dr-mach.de", "www.dr-mach.de", "https://dr-mach.de/x"):
        chosen = classify_mod._select_oem_examples(
            OEM_PROFILE.classification.examples, exclude_domain=dom, per_class={"D2": 99}
        )
        assert chosen and all(e.domain != "dr-mach.de" for e in chosen)
    prompt = classify_mod._build_oem_prompt(OEM_PROFILE, "Dr. Mach", "dr-mach.de", None, LONG_TEXT)
    assert "Company: Dr. Mach GmbH & Co. KG (dr-mach.de)" not in prompt


def test_example_mix_per_prompt() -> None:
    chosen = classify_mod._select_oem_examples(
        OEM_PROFILE.classification.examples, "unrelated.de", OEM_PROFILE.classification.examples_per_class
    )
    by = [e.klass for e in chosen]
    assert by.count("D1") == 2 and by.count("D2") == 2 and by.count("C") == 1 and by.count("D") == 1


def test_parser_unknown_or_missing_maps_to_c() -> None:
    assert classify_mod._parse_oem_result({})["klass_oem"] == "C"
    assert classify_mod._parse_oem_result({"klass_oem": "A"})["klass_oem"] == "C"
    assert classify_mod._parse_oem_result({"klass_oem": "D3"})["klass_oem"] == "C"
    r = classify_mod._parse_oem_result(
        {"klass_oem": "d2", "reason_code": "Eigene_Fertigung", "reasoning": "Own CNC plant."}
    )
    assert r["klass_oem"] == "D2"
    assert r["klass_oem_reason"] == "Eigene_Fertigung: Own CNC plant."
    assert classify_mod._parse_oem_result({"klass_oem": "D1", "reason_code": "x"})["reason_code"] == "Produktionsmodell_unklar"


def test_argv_without_model_is_unchanged() -> None:
    assert classify_mod._cli_argv() == [settings.CLAUDE_CMD, "-p", "--output-format", "text"]


def test_model_lands_in_argv() -> None:
    fake = MagicMock(returncode=0, stdout='{"klass": "A"}', stderr="")
    with patch.object(classify_mod.subprocess, "run", return_value=fake) as run:
        classify_mod._call_claude_cli("p", model="haiku")
        argv = run.call_args.args[0]
        assert argv[-2:] == ["--model", "haiku"]
        classify_mod._call_claude_cli("p")
        assert "--model" not in run.call_args.args[0]
        assert run.call_args.args[0] == [settings.CLAUDE_CMD, "-p", "--output-format", "text"]


def test_lenient_json_only_when_asked() -> None:
    fake = MagicMock(returncode=0, stdout='Here: {"klass_oem": "D1"} done', stderr="")
    with patch.object(classify_mod.subprocess, "run", return_value=fake):
        assert classify_mod._call_claude_cli("p", lenient_json=True) == {"klass_oem": "D1"}
        with patch.object(classify_mod.time, "sleep"):
            with pytest.raises(RuntimeError):
                classify_mod._call_claude_cli("p")


# ---------------------------------------------------------------------------
# T4 writer, T5 rescan selection
# ---------------------------------------------------------------------------


def test_oem_writer_leaves_ambulatory_fields(tmp_db: Path) -> None:
    _insert(
        tmp_db, "maker.de", klass="D", prio="Prio 2 (other)", classified_at="2026-01-01",
        pipeline_stage="classified", scraped_text=LONG_TEXT, reasoning="amb", services_score=3,
    )
    before = dict(_get(tmp_db, "maker.de"))
    with patch.object(
        classify_mod, "classify_oem_one",
        return_value={"klass_oem": "D1", "reason_code": "Eigenmarke_Zukauf", "klass_oem_reason": "Eigenmarke_Zukauf: x"},
    ):
        n = classify_mod.classify_cmd(OEM_PROFILE, db_path=tmp_db, rescan=True, model="haiku", workers=2)
    assert n == 1
    after = dict(_get(tmp_db, "maker.de"))
    assert after["klass_oem"] == "D1" and after["klass_oem_reason"] == "Eigenmarke_Zukauf: x"
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"klass_oem", "klass_oem_reason"}


def test_oem_mode_skips_auto_d_and_name_dupe(tmp_db: Path) -> None:
    # "fahrzeug" is an ambulatory auto-D keyword; a classified twin name would trigger name-dupe copy
    _insert(tmp_db, "twin-a.de", full_name="Twin Medical GmbH", klass="A", pipeline_stage="classified")
    _insert(tmp_db, "twin-b.de", full_name="Twin Medical GmbH", source="BA11_src",
            pipeline_stage="scraped", scraped_text=LONG_TEXT + " Fahrzeug")
    with patch.object(classify_mod, "_call_claude_cli", return_value={"klass_oem": "D2", "reason_code": "Eigene_Fertigung", "reasoning": "x"}) as cli:
        classify_mod.classify_oem_cmd(OEM_PROFILE, db_path=tmp_db)
    assert cli.call_count == 1
    assert _get(tmp_db, "twin-b.de")["klass_oem"] == "D2"
    assert _get(tmp_db, "twin-b.de")["klass"] is None


def test_rescan_selection_honours_exclusions(tmp_db: Path) -> None:
    _insert(tmp_db, "ok-null.de", scraped_text=LONG_TEXT)
    _insert(tmp_db, "ok-d.de", klass="D", scraped_text=LONG_TEXT)
    _insert(tmp_db, "ok-src.de", klass="A", source="BA11_src", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-klass-a.de", klass="A", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-approached.de", pipeline_stage="approached", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-already.de", already_approached=1, scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-batch.de", briefaktion="BA9", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-testbatch.de", briefaktion="testbatch", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-short.de", scraped_text="kurz")
    _insert(tmp_db, "x-done.de", klass_oem="D1", scraped_text=LONG_TEXT)
    rescan = {r["domain"] for r in pipeline_db.get_records_for_oem_classify(tmp_db, rescan=True)}
    assert rescan == {"ok-null.de", "ok-d.de", "ok-src.de"}
    new = {r["domain"] for r in pipeline_db.get_records_for_oem_classify(tmp_db, rescan=False)}
    assert new == {"ok-src.de"}


def test_oem_dry_run_writes_nothing(tmp_db: Path) -> None:
    _insert(tmp_db, "ok.de", source="BA11_src", scraped_text=LONG_TEXT)
    with patch.object(classify_mod, "_call_claude_cli") as cli:
        assert classify_mod.classify_oem_cmd(OEM_PROFILE, db_path=tmp_db, dry_run=True) == 0
    cli.assert_not_called()
    assert _get(tmp_db, "ok.de")["klass_oem"] is None


def test_update_oem_classify_rejects_bad_class(tmp_db: Path) -> None:
    _insert(tmp_db, "a.de")
    with pipeline_db.get_connection(tmp_db) as conn:
        with pytest.raises(ValueError):
            pipeline_db.update_oem_classify_result(conn, "a.de", "A", "x")


# ---------------------------------------------------------------------------
# T3 scrape
# ---------------------------------------------------------------------------


def _record_urls(profile_kwargs: dict) -> tuple[list[str], str]:
    urls: list[str] = []

    def fake_fetch(url: str, retries: int = 3, delay: float = 1.0) -> str:
        urls.append(url)
        return f"<html><body><p>{url} " + ("x" * 5000) + "</p></body></html>"

    with patch.object(web, "fetch_with_retry", side_effect=fake_fetch):
        text = web.extract_page_text("m.de", **profile_kwargs)
    return urls, text


def test_scrape_oem_paths_and_cap_only_for_oem() -> None:
    amb_urls, amb_text = _record_urls(scrape_mod._page_kwargs(AMB_PROFILE.scrape))
    oem_urls, oem_text = _record_urls(scrape_mod._page_kwargs(OEM_PROFILE.scrape))
    assert len(amb_text) == 2500 and amb_urls == ["https://m.de"]  # homepage fills the cap, old behaviour
    assert len(oem_text) == 4000
    assert any(u.endswith("/produktion") for u in oem_urls)
    assert not any("/produktion" in u for u in amb_urls)


def test_ambulatory_page_kwargs_match_old_defaults() -> None:
    kw = scrape_mod._page_kwargs(AMB_PROFILE.scrape)
    assert kw["extra_paths"] is None and kw["max_chars"] == 2500 and kw["homepage_min_chars"] == 800
    assert kw["homepage_max_chars"] is None and kw["path_max_chars"] is None
    assert kw["skip_duplicate_pages"] is False and kw["link_keywords"] is None


def test_keyword_links_skip_oembed_and_foreign() -> None:
    html = (
        '<a href="/de/stema/unsere-lieferanten">L</a><a href="https://other.de/produktion">x</a>'
        '<a href="/wp-json/oembed/1.0/embed">e</a><a href="/oem">o</a><a href="/datei.pdf">p</a>'
    )
    links = web._keyword_links(html, "m.de", ["lieferant", "oem"])
    assert links == ["https://m.de/de/stema/unsere-lieferanten", "https://m.de/oem"]


def test_oem_scrape_selection_and_stage(tmp_db: Path, tmp_path: Path) -> None:
    _insert(tmp_db, "ing.de", pipeline_stage="ingested")
    _insert(tmp_db, "fail.de", pipeline_stage="scrape_failed", scraped_text="")
    _insert(tmp_db, "src.de", source="BA11_src", pipeline_stage="classified", scraped_text="kurz")
    _insert(tmp_db, "x-has-text.de", pipeline_stage="ingested", scraped_text=LONG_TEXT)
    _insert(tmp_db, "x-filtered.de", pipeline_stage="filtered")
    _insert(tmp_db, "x-approached.de", pipeline_stage="approached")
    _insert(tmp_db, "x-already.de", pipeline_stage="ingested", already_approached=1)
    _insert(tmp_db, "x-batch.de", pipeline_stage="scrape_failed", briefaktion="BA3")
    sel = {r["domain"] for r in pipeline_db.get_records_for_oem_scrape(tmp_db)}
    assert sel == {"ing.de", "fail.de", "src.de"}

    def fake_fetch(domain: str, cfg: object) -> str:
        return "" if domain == "fail.de" else LONG_TEXT

    with patch.object(scrape_mod, "fetch_site_text", side_effect=fake_fetch), \
         patch.object(scrape_mod, "fetch_impressum_text", return_value=""), \
         patch.object(scrape_mod, "_POLITE_DELAY_S", 0):
        stats = scrape_mod.scrape_oem_targets_cmd(
            OEM_PROFILE, db_path=tmp_db, kb_path=tmp_path / "kb.db", workers=3
        )
    assert stats["scraped"] == 2 and stats["failed"] == 1
    assert _get(tmp_db, "ing.de")["pipeline_stage"] == "scraped"
    assert _get(tmp_db, "fail.de")["pipeline_stage"] == "scrape_failed"
    assert _get(tmp_db, "src.de")["pipeline_stage"] == "classified"  # only ingested/scrape_failed move
    assert _get(tmp_db, "src.de")["scraped_text"] == LONG_TEXT


def test_empty_oem_scrape_keeps_old_text(tmp_db: Path) -> None:
    _insert(tmp_db, "a.de", pipeline_stage="scrape_failed", scraped_text="old short text")
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_oem_scrape_result(conn, "a.de", "", "2026-11-10")
    row = _get(tmp_db, "a.de")
    assert row["scraped_text"] == "old short text" and row["pipeline_stage"] == "scrape_failed"


# ---------------------------------------------------------------------------
# T6 dashboard, T7 enrich selection
# ---------------------------------------------------------------------------


def test_dashboard_klass_oem_whitelist_and_values() -> None:
    assert "klass_oem" in _WRITEBACK_FIELDS
    for good in ("D1", "D2", "C", "D", "d2"):
        u = {"klass_oem": good}
        assert _check_oem_value(u) is None and u["klass_oem"] == good.upper()
    for empty in ("", None, "  "):
        u = {"klass_oem": empty}
        assert _check_oem_value(u) is None and u["klass_oem"] is None
    for bad in ("A", "D3", "S", 1):
        assert _check_oem_value({"klass_oem": bad}) is not None
    assert _check_oem_value({"prio": "Prio 1"}) is None


def test_oem_reason_in_dashboard_payload(tmp_db: Path) -> None:
    from src.pipeline.dashboard import _load_data

    _insert(tmp_db, "a.de", klass_oem="D1", klass_oem_reason="Eigenmarke_Zukauf: x", scraped_text=LONG_TEXT)
    rec = next(r for r in _load_data(tmp_db)["records"] if r["domain"] == "a.de")
    assert rec["klass_oem"] == "D1" and rec["klass_oem_reason"].startswith("Eigenmarke_Zukauf")
    assert len(rec["scraped_text"]) <= settings.DASHBOARD_SCRAPED_EXCERPT_CHARS


def test_enrich_selection_accepts_oem_d1_c(tmp_db: Path) -> None:
    _insert(tmp_db, "amb.de", pipeline_stage="classified", prio="Prio 1")
    _insert(tmp_db, "d1.de", pipeline_stage="scraped", klass_oem="D1")
    _insert(tmp_db, "c.de", pipeline_stage="ingested", klass_oem="C")
    _insert(tmp_db, "x-d2.de", pipeline_stage="scraped", klass_oem="D2")
    _insert(tmp_db, "x-enriched.de", pipeline_stage="ownership_enriched", klass_oem="D1")
    _insert(tmp_db, "x-contacted.de", pipeline_stage="scraped", klass_oem="D1", already_approached=1)
    # Prio 1 record that also carries an OEM D1 label: default path must not reach it
    _insert(tmp_db, "prio1-d1.de", pipeline_stage="classified", prio="Prio 1", klass_oem="D1")
    # default (run-all, ensure-enrich, plain enrich): no OEM D1/C records, no credits spent on them
    assert {r.domain for r in pipeline_db.get_records_for_enrich(tmp_db)} == {"amb.de"}
    # opt-in: D1 and C reach enrichment without the ambulatory Prio 1 path
    got = {r.domain for r in pipeline_db.get_records_for_enrich(tmp_db, include_oem=True)}
    assert got == {"amb.de", "d1.de", "c.de", "prio1-d1.de"}


def test_ambulatory_classify_skips_ba11_src(tmp_db: Path) -> None:
    _insert(tmp_db, "amb2.de", pipeline_stage="scraped")
    _insert(tmp_db, "maker.de", pipeline_stage="scraped", source="BA11_src")
    assert {r.domain for r in pipeline_db.get_records_for_classify(tmp_db)} == {"amb2.de"}


# ---------------------------------------------------------------------------
# T8 raw-lead ingest, T10 BA11 tagging
# ---------------------------------------------------------------------------


def test_raw_lead_ingest(tmp_db: Path, tmp_path: Path) -> None:
    from src.pipeline.ingest import _ingest_raw_leads

    _insert(tmp_db, "exists.de", klass="B")
    xlsx = tmp_path / "src.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BA11_src"
    ws.append(["title"])
    ws.append(["Nr", "Source", "File", "Domain", "Name", "City", "Cat", "Klass", "Note"])
    ws.append([1, "Targets", "f", "https://www.neu-medizin.de/x", "Neu Medizin GmbH", "Köln", "", None, "contact: none"])
    ws.append([2, "AV", "f", "exists.de", "", "", "", None, ""])
    ws.append([3, "AV", "f", "neu-medizin.de", "", "", "", None, ""])
    ws.append([4, "AV", "f", None, "Kein Web", "", "", None, ""])
    wb.save(xlsx)

    dry = _ingest_raw_leads(xlsx, "BA11_src", "BA11_src", dry_run=True, col_note=8, db_path=tmp_db)
    assert dry["would_insert"] == 1 and dry["inserted"] == 0
    assert dry["skipped_existing"] == 1 and dry["skipped_duplicate"] == 1 and dry["skipped_no_domain"] == 1
    assert _get(tmp_db, "neu-medizin.de") is None

    res = _ingest_raw_leads(xlsx, "BA11_src", "BA11_src", col_note=8, db_path=tmp_db)
    assert res["inserted"] == 1
    row = _get(tmp_db, "neu-medizin.de")
    assert row["source"] == "BA11_src" and row["klass"] is None and row["pipeline_stage"] == "ingested"
    assert row["briefaktion"] is None and row["full_name"] == "Neu Medizin GmbH"
    assert row["manual_note"] == "BA11_src Targets | contact: none"
    assert _get(tmp_db, "exists.de")["klass"] == "B"


def _load_tag_script():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("m37_tag_ba11", ROOT / "scripts" / "m37_tag_ba11.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_ba11_tagging_exclusions(tmp_db: Path) -> None:
    tag = _load_tag_script()
    _insert(tmp_db, "ok-d1.de", klass_oem="D1")
    _insert(tmp_db, "ok-c.de", klass_oem="C", manual_note="05.11 class: x; contact: never contacted")
    _insert(tmp_db, "x-d2.de", klass_oem="D2")
    _insert(tmp_db, "x-approached.de", klass_oem="D1", pipeline_stage="approached")
    _insert(tmp_db, "x-already.de", klass_oem="D1", already_approached=1)
    _insert(tmp_db, "x-batched.de", klass_oem="D1", briefaktion="BA7")
    _insert(tmp_db, "baaske-medical.de", klass_oem="D1")
    _insert(tmp_db, "x-letter.de", klass_oem="C", manual_note="contact: Letter 10/2025, no reply")
    _insert(tmp_db, "x-loi.de", klass_oem="D1", manual_note="contact: LOI v3 built")
    _insert(tmp_db, "x-declined.de", klass_oem="D1", manual_note="28.10 grade B; contact: declined")
    with sqlite3.connect(tmp_db) as conn:
        domains, excluded, already = tag.plan_tagging(conn)
    assert set(domains) == {"ok-d1.de", "ok-c.de"}
    assert excluded == {"approached": 1, "already_approached": 1, "live_deal": 1, "contact_note": 3}
    assert already == 1
    conn = sqlite3.connect(tmp_db)
    try:
        assert tag.apply_tagging(conn, domains) == 2
        conn.commit()
    finally:
        conn.close()
    assert _get(tmp_db, "ok-d1.de")["briefaktion"] == "BA11"
    assert _get(tmp_db, "x-batched.de")["briefaktion"] == "BA7"
    assert _get(tmp_db, "baaske-medical.de")["briefaktion"] is None


def test_fixture_file_shape() -> None:
    import json

    data = json.loads((ROOT / "tests" / "fixtures" / "oem_fixture.json").read_text(encoding="utf-8"))
    comps = data["companies"]
    assert len(comps) == 15
    assert sum(c["label"] == "D1" for c in comps) == 8 and sum(c["label"] == "D2" for c in comps) == 7
    doms = {c["domain"] for c in comps}
    assert "gruppe-provita.de" not in doms and "schmitz-soehne.com" not in doms
    ex_doms = {e.domain for e in OEM_PROFILE.classification.examples}
    assert doms <= ex_doms  # every fixture name is a few-shot example (leave-one-out keeps it honest)
