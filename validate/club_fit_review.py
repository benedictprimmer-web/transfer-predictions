"""Validate Chelsea + Arsenal 10-player club-fit review artifacts.

Run:
    python3 -m validate.club_fit_review
"""
from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from pypdf import PdfReader
from scripts.generate_club_fit_review import derive_reporting_evidence
from validate.club_fit_review_policy import main as run_policy_checks


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "club-fit"
PREVIEWS = OUT / "design-previews"
RENDERED = OUT / "rendered-pages"
AS_OF = "2026-07-20"
PL_NEEDS_URL = "https://www.premierleague.com/en/news/4674463/summer-2026-transfer-window-what-does-each-premier-league-club-need"

EXPECTED = {
    ("Arsenal", "Christos Tzolis"),
    ("Arsenal", "Julián Alvarez"),
    ("Arsenal", "Bradley Barcola"),
    ("Arsenal", "John Stones"),
    ("Arsenal", "Bruno Guimarães"),
    ("Chelsea", "Morgan Rogers"),
    ("Chelsea", "Maxence Lacroix"),
    ("Chelsea", "Andrea Cambiaso"),
    ("Chelsea", "Álvaro Carreras"),
    ("Chelsea", "Edmond Tapsoba"),
}

CONTROLLED = {
    "tm_match_status": {"MATCHED", "UNMATCHED", "AMBIGUOUS"},
    "local_data_status": {"SUPPORTED", "PARTIAL", "ABSTAIN"},
    "fit_rating": {"HIGH", "MEDIUM", "LOW", "NOT_ASSESSED"},
    "latest_report_status": {"CONFIRMED", "ADVANCED_REPORT", "REPORTED_INTEREST", "RUMOUR_ONLY", "NO_CURRENT_CORROBORATION"},
    "reporting_confidence": {"HIGH", "MEDIUM", "LOW", "UNVERIFIED"},
    "price_risk": {"HIGH", "MEDIUM", "LOW", "UNKNOWN"},
    "recommended_action": {"ADVANCE_SCOUTING", "MONITOR_PRICE", "TACTICAL_REVIEW_ONLY", "ABSTAIN_DATA_GAP", "LOW_PRIORITY"},
    "official_confirmation_status": {"OFFICIAL_CONFIRMED", "OFFICIAL_NOT_CONFIRMED", "NO_OFFICIAL_CONFIRMATION"},
    "reporting_evidence_status": {"OFFICIAL_CONFIRMED", "MULTIPLE_VERIFIED_REPORTS", "SINGLE_VERIFIED_REPORT", "UNVERIFIED_REPORT_ONLY", "NO_CURRENT_CORROBORATION", "HUMAN_CHECK_REQUIRED"},
}
SOURCE_STATUSES = {"VERIFIED", "NOT_VERIFIED", "HUMAN_CHECK_REQUIRED"}
SOURCE_METHODS = {"HTTP_FETCH_AND_TITLE_MATCH", "MANUAL_BROWSER_CHECK", "OFFICIAL_PAGE_INSPECTION", "HUMAN_CHECK_REQUIRED", "NOT_VERIFIED"}

FORBIDDEN = [
    "validated sporting-quality ranking",
    "buyer-specific npv model",
    "expected surplus",
    "undervalued ranking",
    "true value ranking",
]


def norm_text(s: str) -> str:
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    for marker in ("*", "`", "_"):
        s = s.replace(marker, "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split()).replace("pre diction", "prediction")


def assert_url(url: str) -> None:
    parsed = urlparse(url)
    assert parsed.scheme in {"http", "https"}, url
    assert parsed.netloc, url
    assert "needx/" not in url, url


def card_section(md: str, player: str) -> str:
    marker = f"### {player}"
    assert marker in md, player
    tail = md.split(marker, 1)[1]
    return tail.split("\n### ", 1)[0]


def main() -> int:
    run_policy_checks()
    subprocess.run(["python3", "scripts/generate_club_fit_review.py"], cwd=REPO, check=True)

    csv_path = OUT / "chelsea-arsenal-player-review.csv"
    md_path = OUT / "chelsea-arsenal-player-review.md"
    pdf_path = OUT / "chelsea-arsenal-player-review.pdf"
    source_path = OUT / "source-register.csv"
    source_validation_path = OUT / "source-validation.csv"

    df = pd.read_csv(csv_path, keep_default_na=False)
    sources = pd.read_csv(source_path, keep_default_na=False)
    source_validation = pd.read_csv(source_validation_path, keep_default_na=False)
    md = md_path.read_text()
    pdf = PdfReader(str(pdf_path))
    page_texts = [page.extract_text() or "" for page in pdf.pages]
    pdf_text = "\n".join(page_texts)
    md_norm = norm_text(md)
    pdf_norm = norm_text(pdf_text)

    assert len(df) == 10, len(df)
    assert set(zip(df.club, df.player)) == EXPECTED
    assert (df.club == "Arsenal").sum() == 5
    assert (df.club == "Chelsea").sum() == 5
    assert not df.duplicated(["club", "player"]).any()
    assert (df.tm_player_id.ne("") | df.tm_match_status.ne("MATCHED")).all()
    assert df.data_warning.ne("").all()
    assert df.recommended_action.ne("").all()
    assert df.source_ids.ne("").all()
    for field in [
        "player_specific_verified_source_count",
        "player_specific_unverified_source_count",
        "official_confirmation_status",
        "independent_verified_corroboration_count",
        "reporting_evidence_status",
        "reporting_confidence_reason",
    ]:
        assert field in df.columns, field
    assert df.reporting_confidence_reason.str.len().gt(35).all()
    assert df.tactical_concern.str.len().gt(35).all()
    assert df.price_risk_reasoning.str.len().gt(35).all()
    assert df.local_file_loaded_date.eq(AS_OF).all()
    assert df.player_record_snapshot_date.ne("").all()
    assert df.current_club_observation_date.ne("").all()

    for col, allowed in CONTROLLED.items():
        bad = set(df[col]) - allowed
        assert not bad, (col, bad)
    assert not ((df.local_metrics_used == "0") | (df.local_metrics_used == "0.0")).any()
    assert not ((df.transfermarkt_market_value_eur == "0") | (df.transfermarkt_market_value_eur == "0.0")).any()

    assert df.as_of_date.eq(AS_OF).all()
    assert AS_OF in md
    assert AS_OF in pdf_text
    assert AS_OF in source_path.read_text()
    assert AS_OF in source_validation_path.read_text()

    assert not sources.source_id.duplicated().any()
    assert not source_validation.source_id.duplicated().any()
    assert set(sources.source_id) == set(source_validation.source_id)
    assert set(source_validation.verification_status) <= SOURCE_STATUSES
    assert set(source_validation.verification_method) <= SOURCE_METHODS
    assert source_validation.claim_checked.ne("").all()
    assert not (
        source_validation.http_status.astype(str).eq("200")
        & source_validation.verification_status.eq("VERIFIED")
        & source_validation.verification_method.eq("NOT_VERIFIED")
    ).any()
    assert not (
        source_validation.http_status.astype(str).eq("200")
        & source_validation.verification_status.eq("VERIFIED")
        & source_validation.claim_checked.str.contains("not reverified", case=False)
    ).any()
    assert PL_NEEDS_URL in set(sources.url)
    assert PL_NEEDS_URL in set(source_validation.url)

    for url in sources.url:
        assert_url(url)
    for url in source_validation.url:
        assert_url(url)

    source_ids = set(sources.source_id)
    source_urls = set(sources.url)
    for _, r in df.iterrows():
        ids = r.source_ids.split(";")
        assert all(sid in source_ids for sid in ids), r.player
        for url in r.source_urls.split(" | "):
            assert url in source_urls, url
        section = card_section(md, r.player)
        assert "[" in section and "]" in section, r.player
        assert r.recommended_action.replace("_", " ").title() in section, r.player
        assert r.reporting_evidence_status.replace("_", " ").title() in section, r.player
        assert r.reporting_confidence_reason in section, r.player
        assert norm_text(r.player) in pdf_norm, r.player
        assert r.recommended_action.replace("_", " ").title().lower() in pdf_norm, r.player
        assert r.reporting_evidence_status.replace("_", " ").title().lower() in pdf_norm, r.player
        derived = derive_reporting_evidence(r.player, ids)
        assert r.reporting_evidence_status == derived["reporting_evidence_status"], r.player
        assert r.reporting_confidence == derived["reporting_confidence"], r.player
        if r.reporting_confidence == "HIGH":
            assert r.official_confirmation_status == "OFFICIAL_CONFIRMED" or int(r.independent_verified_corroboration_count) >= 2, r.player
        if r.latest_report_status == "ADVANCED_REPORT":
            assert int(r.player_specific_verified_source_count) >= 1, r.player

    tm_validation = source_validation[source_validation.source_id.str.startswith("tm_")]
    assert set(tm_validation.verification_status) == {"HUMAN_CHECK_REQUIRED"}
    assert set(tm_validation.verification_method) == {"HUMAN_CHECK_REQUIRED"}
    assert tm_validation.verification_warning.str.contains("no bypass", case=False).all()
    assert df.transfermarkt_rumour_status.eq("HUMAN_CHECK_REQUIRED").all()
    assert df.loc[df.player.eq("Bradley Barcola"), "fit_rating"].iloc[0] == "MEDIUM"
    assert df.loc[df.player.eq("Maxence Lacroix"), "fit_rating"].iloc[0] in {"MEDIUM", "NOT_ASSESSED"}
    assert df.loc[df.player.eq("Maxence Lacroix"), "recommended_action"].iloc[0] != "ADVANCE_SCOUTING"
    assert df.loc[df.player.eq("Christos Tzolis"), "fit_rating"].iloc[0] == "HIGH"
    assert df.loc[df.player.eq("Morgan Rogers"), "latest_report_status"].iloc[0] == "RUMOUR_ONLY"
    assert df.loc[df.player.eq("Morgan Rogers"), "reporting_confidence"].iloc[0] == "UNVERIFIED"
    assert df.loc[df.player.eq("Maxence Lacroix"), "reporting_confidence"].iloc[0] == "UNVERIFIED"

    dated_sources = sources[
        ~sources.source_id.str.startswith("tm_")
        & sources.source_id.ne("chelsea_official_transfers_2026")
    ]
    assert dated_sources.publication_date.ne("").all()
    assert sources.loc[
        sources.source_id.eq("chelsea_official_transfers_2026"),
        "retrieval_date",
    ].eq(AS_OF).all()
    assert "References" in md
    assert "references" in pdf_norm
    assert "not a validated sporting prediction" in md_norm
    assert "not a validated sporting prediction" in pdf_norm
    assert "underpriced-player claim" in md_norm
    assert "human check required" in md_norm
    assert "human check required" in pdf_norm
    assert "http 200 status" in md_norm
    assert "not browser-printed from the preview html" in md_norm
    assert "needx/" not in md
    assert "needx/" not in pdf_text

    assert 6 <= len(pdf.pages) <= 8, len(pdf.pages)
    assert "Market-consensus snapshot" in pdf_text

    for preview in [
        PREVIEWS / "design-a-editorial-scouting-desk.png",
        PREVIEWS / "design-b-club-recruitment-dashboard.png",
        PREVIEWS / "design-a-editorial-scouting-desk.html",
        PREVIEWS / "design-b-club-recruitment-dashboard.html",
        PREVIEWS / "design-decision.md",
    ]:
        assert preview.exists() and preview.stat().st_size > 100, preview
    for html in [
        PREVIEWS / "design-a-editorial-scouting-desk.html",
        PREVIEWS / "design-b-club-recruitment-dashboard.html",
    ]:
        text = html.read_text()
        for _, r in df.iterrows():
            assert r.player in text, (html, r.player)
        assert "Market-consensus snapshot" in text
        assert "Data warning" in text
    rendered_pages = sorted(RENDERED.glob("page-*.pdf.png"))
    if rendered_pages:
        assert len(rendered_pages) == len(pdf.pages), (len(rendered_pages), len(pdf.pages))
        assert (RENDERED / "contact-sheet.png").exists()
        assert all(p.stat().st_size > 20_000 for p in rendered_pages)

    low = md_norm + "\n" + pdf_norm
    for phrase in FORBIDDEN:
        if phrase in low:
            assert f"not {phrase}" in low or f"not a {phrase}" in low, phrase

    print("ok - club-fit review artifacts regenerated and validated")
    print(f"rows={len(df)} arsenal={(df.club == 'Arsenal').sum()} chelsea={(df.club == 'Chelsea').sum()} pdf_pages={len(pdf.pages)} sources={len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
