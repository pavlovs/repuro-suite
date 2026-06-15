"""Tests for M18 normalization functions."""

import pytest

from src.pipeline.normalize import (
    build_salutation,
    clean_gesellschafter_name,
    enrich_owner_name,
    fix_compliment_text,
    normalize_anrede,
    normalize_plz_ort,
    parse_impressum_address,
    restore_umlauts_german,
    restore_umlauts_name,
    restore_umlauts_pattern,
    title_case_german,
)


# ── title_case_german ────────────────────────────────────────────────────────


class TestTitleCaseGerman:
    def test_basic(self):
        assert (
            title_case_german("MÜLLER MEDIZINTECHNIK GMBH")
            == "Müller Medizintechnik GmbH"
        )

    def test_legal_gmbh(self):
        assert "GmbH" in title_case_german("TEST GMBH")

    def test_legal_kg(self):
        assert "KG" in title_case_german("TEST KG")

    def test_legal_gbr(self):
        assert "GbR" in title_case_german("TEST GBR")

    def test_legal_ug(self):
        assert "UG" in title_case_german("TEST UG")

    def test_legal_ag(self):
        assert "AG" in title_case_german("TEST AG")

    def test_legal_ohg(self):
        assert "OHG" in title_case_german("TEST OHG")

    def test_legal_ek(self):
        result = title_case_german("TEST E.K.")
        assert "e.K." in result

    def test_legal_kgaa(self):
        assert "KGaA" in title_case_german("TEST KGAA")

    def test_gmbh_co_kg(self):
        result = title_case_german("TEST GMBH & CO. KG")
        assert "GmbH" in result
        assert "Co." in result
        assert "KG" in result

    def test_prepositions_lowercase(self):
        assert title_case_german("HANDEL AM RHEIN") == "Handel am Rhein"

    def test_prepositions_first_word_stays_capitalized(self):
        result = title_case_german("AM RHEIN HANDEL")
        # "Am" is first word, should stay capitalized
        assert result.startswith("Am ")

    def test_von_lowercase(self):
        assert title_case_german("MEDIZIN VON BERLIN") == "Medizin von Berlin"

    def test_empty_string(self):
        assert title_case_german("") == ""

    def test_none_like(self):
        assert title_case_german("   ") == "   "

    def test_already_correct(self):
        assert title_case_german("Müller GmbH") == "Müller GmbH"


# ── restore_umlauts_pattern ──────────────────────────────────────────────────


class TestRestoreUmlautsPattern:
    def test_strasse_titlecase(self):
        result = restore_umlauts_pattern("Muellerstrasse")
        assert "straße" in result or "Straße" in result

    def test_strasse_allcaps(self):
        # After title-casing, "MUELLERSTRASSE" becomes "Muellerstrasse"
        result = restore_umlauts_pattern("Muellerstrasse 5")
        assert "straße" in result.lower()

    def test_no_false_positive_buer(self):
        # "Buer" is a real German city, not "Bür"
        result = restore_umlauts_pattern("Buer")
        assert result == "Buer"

    def test_aerzte(self):
        result = restore_umlauts_pattern("Aerzte")
        assert "ärzte" in result.lower()


# ── restore_umlauts_name ─────────────────────────────────────────────────────


class TestRestoreUmlautsName:
    def test_joerg(self):
        assert restore_umlauts_name("Joerg Mueller") == "Jörg Müller"

    def test_juergen(self):
        assert restore_umlauts_name("Juergen Schmidt") == "Jürgen Schmidt"

    def test_guenther(self):
        assert restore_umlauts_name("Guenther Braun") == "Günther Braun"

    def test_bruehl_city(self):
        assert restore_umlauts_name("50321 Bruehl") == "50321 Brühl"

    def test_duesseldorf(self):
        assert restore_umlauts_name("Duesseldorf") == "Düsseldorf"

    def test_unambiguous_surname_restored(self):
        assert restore_umlauts_name("Peter Mueller") == "Peter Müller"

    def test_empty(self):
        assert restore_umlauts_name("") == ""

    def test_none(self):
        assert restore_umlauts_name(None) is None


# ── normalize_anrede ─────────────────────────────────────────────────────────


class TestNormalizeAnrede:
    def test_mr_to_herr(self):
        assert normalize_anrede("MR") == "Herr"

    def test_mrs_to_frau(self):
        assert normalize_anrede("MRS") == "Frau"

    def test_ms_to_frau(self):
        assert normalize_anrede("MS") == "Frau"

    def test_herr_unchanged(self):
        assert normalize_anrede("Herr") == "Herr"

    def test_frau_unchanged(self):
        assert normalize_anrede("Frau") == "Frau"

    def test_empty_returns_none(self):
        assert normalize_anrede("") is None

    def test_none_returns_none(self):
        assert normalize_anrede(None) is None

    def test_mr_with_dot(self):
        assert normalize_anrede("MR.") == "Herr"

    def test_case_insensitive(self):
        assert normalize_anrede("mr") == "Herr"
        assert normalize_anrede("Mrs") == "Frau"


# ── clean_gesellschafter_name ────────────────────────────────────────────────


class TestCleanGesellschafterName:
    def test_strip_mr_prefix(self):
        result = clean_gesellschafter_name("MR KLAUS MUELLER")
        assert result == "Klaus Mueller"
        assert "MR" not in result

    def test_strip_mrs_prefix(self):
        result = clean_gesellschafter_name("MRS ANNA SCHMIDT")
        assert result == "Anna Schmidt"

    def test_preserve_dr_prefix(self):
        result = clean_gesellschafter_name("DR. ANNA SCHMIDT")
        assert result.startswith("Dr. ")
        assert "Anna" in result
        assert "Schmidt" in result

    def test_mr_dr_combo(self):
        result = clean_gesellschafter_name("MR DR. KLAUS MUELLER")
        assert result.startswith("Dr. ")
        assert "Klaus" in result

    def test_title_case_applied(self):
        result = clean_gesellschafter_name("MR PETER GROSS")
        assert result == "Peter Gross"

    def test_none_returns_none(self):
        assert clean_gesellschafter_name(None) is None

    def test_empty_returns_empty(self):
        assert clean_gesellschafter_name("") == ""


# ── enrich_owner_name ────────────────────────────────────────────────────────


class TestEnrichOwnerName:
    def test_single_word_enriched(self):
        result = enrich_owner_name("Mueller", "MR Klaus Mueller")
        assert result == "Klaus Mueller"

    def test_already_full_unchanged(self):
        result = enrich_owner_name("Klaus Mueller", "MR Klaus Mueller")
        assert result == "Klaus Mueller"

    def test_no_gesellschafter(self):
        result = enrich_owner_name("Mueller", None)
        assert result == "Mueller"

    def test_no_owner_name(self):
        result = enrich_owner_name(None, "Klaus Mueller")
        assert result is None

    def test_mismatch_lastname(self):
        result = enrich_owner_name("Schmidt", "MR Klaus Mueller")
        assert result == "Schmidt"


# ── build_salutation ─────────────────────────────────────────────────────────


class TestBuildSalutation:
    def test_herr(self):
        result = build_salutation("Herr", "Klaus Mueller")
        assert result == "Sehr geehrter Herr Mueller"

    def test_frau(self):
        result = build_salutation("Frau", "Anna Schmidt")
        assert result == "Sehr geehrte Frau Schmidt"

    def test_missing_anrede(self):
        assert build_salutation(None, "Klaus Mueller") is None

    def test_missing_gf_name(self):
        assert build_salutation("Herr", None) is None

    def test_invalid_anrede(self):
        assert build_salutation("MR", "Klaus Mueller") is None

    def test_multi_part_name(self):
        result = build_salutation("Herr", "Klaus von Mueller")
        assert result == "Sehr geehrter Herr Mueller"


# ── normalize_plz_ort ────────────────────────────────────────────────────────


class TestNormalizePlzOrt:
    def test_basic(self):
        assert normalize_plz_ort("12345 BERLIN") == "12345 Berlin"

    def test_preserves_plz(self):
        result = normalize_plz_ort("01234 DRESDEN")
        assert result.startswith("01234")

    def test_no_city(self):
        assert normalize_plz_ort("12345") == "12345"

    def test_none(self):
        assert normalize_plz_ort(None) is None

    def test_empty(self):
        assert normalize_plz_ort("") == ""

    def test_already_correct(self):
        assert normalize_plz_ort("12345 Berlin") == "12345 Berlin"


# ── restore_umlauts_german (M23) ────────────────────────────────────────────


class TestRestoreUmlautsGerman:
    def test_pruefung(self):
        assert restore_umlauts_german("Pruefung") == "Prüfung"

    def test_roentgen(self):
        assert restore_umlauts_german("Roentgen") == "Röntgen"

    def test_compound_sentence(self):
        result = restore_umlauts_german("herstellerunabhaengige Pruefungen")
        assert result == "herstellerunabhängige Prüfungen"

    def test_preserves_valid_german(self):
        # "Dauer" contains "auer" but should not be replaced
        assert restore_umlauts_german("Dauer") == "Dauer"

    def test_preserves_punctuation(self):
        assert restore_umlauts_german("Pruefung.") == "Prüfung."

    def test_all_caps_preserved(self):
        assert restore_umlauts_german("PRUEFUNG") == "PRÜFUNG"

    def test_empty_string(self):
        assert restore_umlauts_german("") == ""

    def test_none(self):
        # Should handle None gracefully (returns as-is)
        assert restore_umlauts_german(None) is None

    def test_mixed_sentence(self):
        result = restore_umlauts_german(
            "zuverlaessige Qualitaetssicherung fuer Geraete"
        )
        assert "zuverlässig" in result
        assert "Qualitätssicherung" in result
        assert "für" in result
        assert "Geräte" in result


# ── fix_compliment_text (M23) ───────────────────────────────────────────────


class TestFixComplimentText:
    def test_k1_strips_besonders(self):
        k1, _ = fix_compliment_text("Besonders Ihre langjährige Erfahrung", None)
        assert k1.startswith("ihre")
        assert "Besonders" not in k1

    def test_k1_strips_trailing_period(self):
        k1, _ = fix_compliment_text("die Erfahrung im Bereich.", None)
        assert not k1.endswith(".")

    def test_k2_strips_auch(self):
        _, k2 = fix_compliment_text(None, "Auch hat uns der Service überzeugt")
        assert not k2.startswith("Auch")

    def test_k2_strips_trailing_period(self):
        _, k2 = fix_compliment_text(None, "hat uns der Service überzeugt.")
        assert not k2.endswith(".")

    def test_k2_warns_missing_verb(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            _, k2 = fix_compliment_text(None, "der umfangreiche Service")
        assert "missing verb" in caplog.text.lower() or "hat" in caplog.text.lower()

    def test_none_passthrough(self):
        k1, k2 = fix_compliment_text(None, None)
        assert k1 is None
        assert k2 is None

    def test_k1_strips_auch(self):
        k1, _ = fix_compliment_text("Auch die Innovation beeindruckt", None)
        assert not k1.startswith("Auch")


# ── parse_impressum_address ─────────────────────────────────────────────────


class TestParseImpressumAddress:
    def test_standard_address(self):
        text = "Firma GmbH\nOtto-Schott-Strasse 21\n73431 Aalen\nTel: 07361/123"
        street, plz_ort = parse_impressum_address(text)
        assert street == "Otto-Schott-Strasse 21"
        assert plz_ort == "73431 Aalen"

    def test_strasse_with_eszett(self):
        text = "Hauptstraße 5\n10115 Berlin"
        street, plz_ort = parse_impressum_address(text)
        assert street == "Hauptstraße 5"
        assert plz_ort == "10115 Berlin"

    def test_abbreviated_str(self):
        text = "Max-Otten-Str. 14\n39104 Magdeburg"
        street, plz_ort = parse_impressum_address(text)
        assert street == "Max-Otten-Str. 14"
        assert plz_ort == "39104 Magdeburg"

    def test_weg_suffix(self):
        text = "Am Birkenweg 3a\n21075 Hamburg"
        street, plz_ort = parse_impressum_address(text)
        assert "Birkenweg 3a" in street
        assert plz_ort == "21075 Hamburg"

    def test_compound_city(self):
        text = "Industriestr. 7\n09356 St. Egidien"
        street, plz_ort = parse_impressum_address(text)
        assert plz_ort == "09356 St. Egidien"

    def test_no_address(self):
        text = "Willkommen auf unserer Webseite. Wir bieten Medizintechnik."
        street, plz_ort = parse_impressum_address(text)
        assert street is None
        assert plz_ort is None

    def test_empty_input(self):
        street, plz_ort = parse_impressum_address("")
        assert street is None
        assert plz_ort is None

    def test_phone_not_matched_as_plz(self):
        text = "Tel: (05341) 31137\nFax: 05341/31138"
        _, plz_ort = parse_impressum_address(text)
        assert plz_ort is None
