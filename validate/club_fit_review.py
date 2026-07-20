"""Validate Chelsea + Arsenal 10-player club-fit review artifacts.

Run:
    python3 -m validate.club_fit_review
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from pypdf import PdfReader
import unicodedata


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "club-fit"
AS_OF = "2026-07-20"

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
    "recommended_action": {"ADVANCE_SCOUTING", "MONITOR_PRICE", "TACTICAL_REVIEW_ONLY", "ABSTAIN_DATA_GAP", "LOW_PRIORITY"},
}

FORBIDDEN = [
    "validated sporting prediction",
    "validated sporting-quality ranking",
    "buyer-specific npv",
    "surplus ranking",
    "expected fee",
    "fair value",
    "undervalued ranking",
]


def norm_text(s: str) -> str:
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    for marker in ("*", "`", "_"):
        s = s.replace(marker, "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    normalized = " ".join(s.lower().split())
    return normalized.replace("pre diction", "prediction")


def main() -> int:
    csv_path = OUT / "chelsea-arsenal-player-review.csv"
    md_path = OUT / "chelsea-arsenal-player-review.md"
    pdf_path = OUT / "chelsea-arsenal-player-review.pdf"
    source_path = OUT / "source-register.csv"

    df = pd.read_csv(csv_path, keep_default_na=False)
    sources = pd.read_csv(source_path, keep_default_na=False)
    md = md_path.read_text()
    pdf = PdfReader(str(pdf_path))
    pdf_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
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
    for col, allowed in CONTROLLED.items():
        bad = set(df[col]) - allowed
        assert not bad, (col, bad)
    assert not ((df.local_metrics_used == "0") | (df.local_metrics_used == "0.0")).any()
    assert df.as_of_date.eq(AS_OF).all()
    assert AS_OF in md
    assert AS_OF in pdf_text

    source_urls = set(sources.url)
    for urls in df.source_urls:
        for url in urls.split(" | "):
            assert url in source_urls, url

    for _, r in df.iterrows():
        assert f"### {r.player}" in md
        assert norm_text(r.player) in pdf_norm
    assert "not a validated sporting prediction" in md_norm
    assert "not a validated sporting prediction" in pdf_norm
    assert "Transfermarkt Rumour Mill direct status is unavailable" in md
    assert len(pdf.pages) > 0
    low = md_norm + "\n" + pdf_norm
    for phrase in FORBIDDEN:
        assert phrase not in low or f"not a {phrase}" in low or f"not {phrase}" in low, phrase
    print("ok - club-fit review artifacts validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
