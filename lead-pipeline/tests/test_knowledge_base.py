"""Tests for the SQLite knowledge base cache."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from src.utils.knowledge_base import KnowledgeBase


@pytest.fixture
def kb(tmp_path: Path) -> KnowledgeBase:
    return KnowledgeBase(tmp_path / "test_kb.db")


class TestInit:
    def test_creates_db_file(self, tmp_path: Path):
        path = tmp_path / "new.db"
        KnowledgeBase(path)
        assert path.exists()

    def test_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "sub" / "dir" / "kb.db"
        KnowledgeBase(path)
        assert path.exists()

    def test_tables_exist(self, kb: KnowledgeBase):
        s = kb.stats()
        assert "domains_cached" in s
        assert "ownership_cached" in s
        assert "documents" in s


class TestDomainCache:
    def test_save_and_get_scraped_text(self, kb: KnowledgeBase):
        kb.save_scraped_text("example.de", "Wir bieten Medizintechnik Services")
        result = kb.get_scraped_text("example.de")
        assert result == "Wir bieten Medizintechnik Services"

    def test_get_unknown_domain_returns_none(self, kb: KnowledgeBase):
        assert kb.get_scraped_text("unknown.de") is None

    def test_get_respects_ttl_fresh(self, kb: KnowledgeBase):
        kb.save_scraped_text("fresh.de", "fresh content")
        assert kb.get_scraped_text("fresh.de", max_age_days=90) is not None

    def test_get_respects_ttl_stale(self, kb: KnowledgeBase):
        """Simulate a stale entry by directly inserting old timestamp."""
        import sqlite3
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        with sqlite3.connect(kb.path) as conn:
            conn.execute(
                "INSERT INTO domain_cache (domain, scraped_text, scraped_at, http_status, source_urls) VALUES (?, ?, ?, ?, ?)",
                ("stale.de", "old content", old_date, 200, "[]"),
            )
        assert kb.get_scraped_text("stale.de", max_age_days=90) is None

    def test_upsert_updates_existing(self, kb: KnowledgeBase):
        kb.save_scraped_text("update.de", "old text")
        kb.save_scraped_text("update.de", "new text")
        assert kb.get_scraped_text("update.de") == "new text"

    def test_domain_already_seen_false(self, kb: KnowledgeBase):
        assert kb.domain_already_seen("never.de") is False

    def test_domain_already_seen_true(self, kb: KnowledgeBase):
        kb.save_scraped_text("seen.de", "text")
        assert kb.domain_already_seen("seen.de") is True

    def test_preserves_umlauts(self, kb: KnowledgeBase):
        text = "Sprechstundenbedarf für Ärzte — Müller GmbH & Co. KG"
        kb.save_scraped_text("umlaut.de", text)
        assert kb.get_scraped_text("umlaut.de") == text


class TestOwnershipCache:
    def test_save_and_get_ownership(self, kb: KnowledgeBase):
        data = {
            "hrb_number": "HRB 12345",
            "gesellschafter_name": "Max Mustermann",
            "gesellschafter_share_pct": 100.0,
            "gesellschafter_age": 55,
            "is_subsidiary": False,
            "is_pe_backed": False,
            "gf_name": "Max Mustermann",
        }
        kb.save_ownership("owner.de", data, source="openregister")
        result = kb.get_ownership("owner.de")
        assert result is not None
        assert result["gesellschafter_name"] == "Max Mustermann"
        assert result["gesellschafter_share_pct"] == 100.0
        assert result["source"] == "openregister"

    def test_get_unknown_returns_none(self, kb: KnowledgeBase):
        assert kb.get_ownership("nobody.de") is None

    def test_get_respects_ttl_stale(self, kb: KnowledgeBase):
        import sqlite3
        old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        with sqlite3.connect(kb.path) as conn:
            conn.execute(
                "INSERT INTO ownership_cache (domain, source, fetched_at) VALUES (?, ?, ?)",
                ("stale-owner.de", "offeneregister", old_date),
            )
        assert kb.get_ownership("stale-owner.de", max_age_days=180) is None

    def test_upsert_updates_existing(self, kb: KnowledgeBase):
        kb.save_ownership("upd.de", {"gf_name": "Old Name"}, source="offeneregister")
        kb.save_ownership("upd.de", {"gf_name": "New Name"}, source="openregister")
        result = kb.get_ownership("upd.de")
        assert result["gf_name"] == "New Name"
        assert result["source"] == "openregister"

    def test_boolean_stored_as_int(self, kb: KnowledgeBase):
        kb.save_ownership("bool.de", {"is_subsidiary": True, "is_pe_backed": False}, source="test")
        result = kb.get_ownership("bool.de")
        assert result["is_subsidiary"] == 1
        assert result["is_pe_backed"] == 0


class TestDocuments:
    def test_save_and_get_document(self, kb: KnowledgeBase):
        kb.save_document("doc.de", "HRB 999", "impressum", "Impressum content here")
        result = kb.get_document("doc.de", "impressum")
        assert result == "Impressum content here"

    def test_get_unknown_document_returns_none(self, kb: KnowledgeBase):
        assert kb.get_document("none.de", "impressum") is None

    def test_get_returns_most_recent(self, kb: KnowledgeBase):
        kb.save_document("multi.de", None, "impressum", "first version")
        kb.save_document("multi.de", None, "impressum", "second version")
        assert kb.get_document("multi.de", "impressum") == "second version"

    def test_different_doc_types_independent(self, kb: KnowledgeBase):
        kb.save_document("types.de", None, "impressum", "impressum text")
        kb.save_document("types.de", None, "handelsregister_excerpt", "HR text")
        assert kb.get_document("types.de", "impressum") == "impressum text"
        assert kb.get_document("types.de", "handelsregister_excerpt") == "HR text"


class TestStats:
    def test_stats_empty(self, kb: KnowledgeBase):
        s = kb.stats()
        assert s["domains_cached"] == 0
        assert s["with_text"] == 0
        assert s["ownership_cached"] == 0
        assert s["documents"] == 0

    def test_stats_counts_correctly(self, kb: KnowledgeBase):
        kb.save_scraped_text("a.de", "text a")
        kb.save_scraped_text("b.de", "text b")
        kb.save_scraped_text("c.de", "")  # empty text
        kb.save_ownership("a.de", {"gf_name": "X"}, "test")
        kb.save_document("a.de", None, "impressum", "content")
        s = kb.stats()
        assert s["domains_cached"] == 3
        assert s["with_text"] == 2  # only a.de and b.de have non-empty text
        assert s["ownership_cached"] == 1
        assert s["documents"] == 1
