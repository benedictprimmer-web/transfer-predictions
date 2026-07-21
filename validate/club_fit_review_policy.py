"""Data-independent policy tests for the Chelsea + Arsenal club-fit review.

Run:
    python3 -m validate.club_fit_review_policy
"""
from __future__ import annotations

from scripts.generate_club_fit_review import (
    CANDIDATES,
    PLAYER_SOURCE_CLAIMS,
    SOURCE_VALIDATION,
    SOURCES,
    derive_reporting_evidence,
)


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


def candidate(player: str) -> dict:
    matches = [c for c in CANDIDATES if c["player"] == player]
    assert len(matches) == 1, player
    return matches[0]


def status_for(player: str) -> dict:
    c = candidate(player)
    return derive_reporting_evidence(player, c["source_ids"].split(";"))


def fixture_validation(status: str = "NOT_VERIFIED", method: str = "NOT_VERIFIED") -> dict[str, dict]:
    return {
        "general_need": {"http_status": "200", "verification_status": "VERIFIED", "verification_method": "MANUAL_BROWSER_CHECK"},
        "official_page": {"http_status": "200", "verification_status": "VERIFIED", "verification_method": "OFFICIAL_PAGE_INSPECTION"},
        "player_a_report": {"http_status": "200", "verification_status": status, "verification_method": method},
        "player_b_report": {"http_status": "200", "verification_status": status, "verification_method": method},
    }


def assert_fixed_candidates() -> None:
    pairs = {(c["club"], c["player"]) for c in CANDIDATES}
    assert pairs == EXPECTED
    assert sum(c["club"] == "Arsenal" for c in CANDIDATES) == 5
    assert sum(c["club"] == "Chelsea" for c in CANDIDATES) == 5


def assert_explicit_source_validation() -> None:
    source_ids = {s["source_id"] for s in SOURCES}
    assert set(SOURCE_VALIDATION) == source_ids
    assert not any(v["verification_status"] == "VERIFIED" and v["verification_method"] == "NOT_VERIFIED" for v in SOURCE_VALIDATION.values())
    for sid, validation in SOURCE_VALIDATION.items():
        assert "http_status" in validation and "verification_status" in validation and "verification_method" in validation, sid
    tm = [sid for sid in source_ids if sid.startswith("tm_")]
    assert tm
    for sid in tm:
        assert SOURCE_VALIDATION[sid]["verification_status"] == "HUMAN_CHECK_REQUIRED"
        assert SOURCE_VALIDATION[sid]["verification_method"] == "HUMAN_CHECK_REQUIRED"


def assert_actual_candidate_policy() -> None:
    for c in CANDIDATES:
        evidence = status_for(c["player"])
        assert evidence["reporting_evidence_status"], c["player"]
        assert evidence["reporting_confidence"], c["player"]
        if evidence["reporting_confidence"] == "HIGH":
            assert (
                evidence["official_confirmation_status"] == "OFFICIAL_CONFIRMED"
                or evidence["independent_verified_corroboration_count"] >= 2
            ), c["player"]
        if evidence["latest_report_status"] == "ADVANCED_REPORT":
            assert evidence["player_specific_verified_source_count"] >= 1, c["player"]
        assert c["fit_rating"] in {"HIGH", "MEDIUM", "LOW", "NOT_ASSESSED"}
        assert "reporting_confidence" not in c["fit_rating"].lower()

    assert status_for("Morgan Rogers")["latest_report_status"] == "RUMOUR_ONLY"
    assert status_for("Morgan Rogers")["reporting_confidence"] == "UNVERIFIED"
    assert status_for("Maxence Lacroix")["reporting_confidence"] == "UNVERIFIED"
    assert status_for("Bruno Guimarães")["reporting_confidence"] == "MEDIUM"
    assert status_for("Christos Tzolis")["reporting_confidence"] == "MEDIUM"


def assert_adversarial_policy_fixtures() -> None:
    http_200_uninspected = derive_reporting_evidence(
        "Player A",
        ["player_a_report"],
        source_validation=fixture_validation(status="NOT_VERIFIED", method="NOT_VERIFIED"),
        player_source_claims={("Player A", "player_a_report"): {"verified_player_claim": False, "official_confirmation": False, "independent": True}},
        desired_status="ADVANCED_REPORT",
    )
    assert http_200_uninspected["reporting_confidence"] != "HIGH"
    assert http_200_uninspected["latest_report_status"] != "ADVANCED_REPORT"

    two_unverified = derive_reporting_evidence(
        "Player A",
        ["player_a_report", "player_b_report"],
        source_validation=fixture_validation(status="NOT_VERIFIED", method="NOT_VERIFIED"),
        player_source_claims={
            ("Player A", "player_a_report"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
            ("Player A", "player_b_report"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
        },
        desired_status="REPORTED_INTEREST",
    )
    assert two_unverified["reporting_evidence_status"] != "MULTIPLE_VERIFIED_REPORTS"

    official_without_player = derive_reporting_evidence(
        "Player A",
        ["official_page"],
        source_validation=fixture_validation(status="VERIFIED", method="OFFICIAL_PAGE_INSPECTION"),
        player_source_claims={("Player A", "official_page"): {"verified_player_claim": False, "official_confirmation": False, "independent": False}},
        desired_status="ADVANCED_REPORT",
    )
    assert official_without_player["official_confirmation_status"] != "OFFICIAL_CONFIRMED"
    assert official_without_player["reporting_confidence"] != "HIGH"

    general_need_only = derive_reporting_evidence(
        "Player A",
        ["general_need"],
        source_validation=fixture_validation(status="VERIFIED", method="MANUAL_BROWSER_CHECK"),
        player_source_claims={},
        desired_status="REPORTED_INTEREST",
    )
    assert general_need_only["player_specific_verified_source_count"] == 0
    assert general_need_only["latest_report_status"] != "REPORTED_INTEREST"

    player_a_does_not_verify_b = derive_reporting_evidence(
        "Player B",
        ["player_a_report"],
        source_validation=fixture_validation(status="VERIFIED", method="MANUAL_BROWSER_CHECK"),
        player_source_claims={("Player A", "player_a_report"): {"verified_player_claim": True, "official_confirmation": False, "independent": True}},
        desired_status="REPORTED_INTEREST",
    )
    assert player_a_does_not_verify_b["player_specific_verified_source_count"] == 0
    assert player_a_does_not_verify_b["reporting_confidence"] != "HIGH"

    assert ("Bradley Barcola", "sky_tzolis_arsenal") not in PLAYER_SOURCE_CLAIMS
    assert ("Morgan Rogers", "chelsea_official_transfers_2026") in PLAYER_SOURCE_CLAIMS


def main() -> int:
    assert_fixed_candidates()
    assert_explicit_source_validation()
    assert_actual_candidate_policy()
    assert_adversarial_policy_fixtures()
    print("ok - club-fit source-confidence policy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
