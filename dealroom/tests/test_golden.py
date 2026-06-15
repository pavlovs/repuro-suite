"""Tests for DR-GC: Golden Corpus loader and health check."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.golden import (
    _extract_text,
    check_golden_health,
    load_golden_corpus,
    load_golden_text,
)


def _make_golden(tmp_path: Path) -> Path:
    """Create a minimal golden corpus in tmp_path."""
    golden = tmp_path / "golden"
    (golden / "rfi").mkdir(parents=True)
    (golden / "offer").mkdir()
    (golden / "email").mkdir()

    (golden / "rfi" / "example.md").write_text(
        "# RFI Fragen\n\n1. Wie hoch war der Umsatz?\n2. EBITDA Margin?",
        encoding="utf-8",
    )
    (golden / "rfi" / "second.md").write_text(
        "# Weitere Fragen\n\n1. Kundenkonzentration?",
        encoding="utf-8",
    )
    (golden / "offer" / "example_offer.md").write_text(
        "Sehr geehrte Damen und Herren,\n\nwir unterbreiten Ihnen ein Angebot.",
        encoding="utf-8",
    )

    manifest = {
        "version": 1,
        "files": [
            {
                "path": "rfi/example.md",
                "doc_type": "rfi",
                "source_deal": "Cat",
                "format": "md",
                "usage": "test",
                "added": "2026-04-23",
            },
            {
                "path": "rfi/second.md",
                "doc_type": "rfi",
                "source_deal": "Wolf",
                "format": "md",
                "usage": "test",
                "added": "2026-04-23",
            },
            {
                "path": "offer/example_offer.md",
                "doc_type": "offer",
                "source_deal": "Octopus",
                "format": "md",
                "usage": "test",
                "added": "2026-04-23",
            },
        ],
        "gaps": [
            {"doc_type": "email", "note": "No email examples yet"},
        ],
    }
    (golden / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return golden


def test_extract_text_md(tmp_path):
    p = tmp_path / "test.md"
    p.write_text("# Hello\nWorld", encoding="utf-8")
    assert _extract_text(p) == "# Hello\nWorld"


def test_extract_text_unknown_suffix(tmp_path):
    p = tmp_path / "test.xyz"
    p.write_text("data", encoding="utf-8")
    assert _extract_text(p) == ""


def test_load_golden_corpus_filters_by_type(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        results = load_golden_corpus("rfi")
    assert len(results) == 2
    assert all("rfi" in r["path"] for r in results)


def test_load_golden_corpus_excludes_deal(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        results = load_golden_corpus("rfi", exclude_deal="Cat")
    assert len(results) == 1
    assert results[0]["metadata"]["source_deal"] == "Wolf"


def test_load_golden_corpus_respects_max_chars(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        results = load_golden_corpus("rfi", max_chars=30)
    total = sum(len(r["text"]) for r in results)
    assert total <= 30


def test_load_golden_text_returns_string(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        text = load_golden_text("rfi")
    assert isinstance(text, str)
    assert "Umsatz" in text
    assert "--- Cat" in text


def test_load_golden_text_empty_type(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        text = load_golden_text("email")
    assert text == ""


def test_health_check(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        health = check_golden_health()
    assert health["total"] == 3
    assert health["by_type"]["rfi"] == 2
    assert health["by_type"]["offer"] == 1
    assert "email" in health["gaps"]
    assert len(health["missing"]) == 0


def test_health_check_missing_file(tmp_path):
    golden = _make_golden(tmp_path)
    (golden / "rfi" / "example.md").unlink()
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        health = check_golden_health()
    assert health["total"] == 2
    assert "rfi/example.md" in health["missing"]


def test_manifest_gaps_reported(tmp_path):
    golden = _make_golden(tmp_path)
    with patch("src.golden.settings") as mock_settings:
        mock_settings.GOLDEN_CORPUS_DIR = golden
        health = check_golden_health()
    assert len(health["manifest_gaps"]) == 1
    assert health["manifest_gaps"][0]["doc_type"] == "email"
