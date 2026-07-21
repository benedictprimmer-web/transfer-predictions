from __future__ import annotations

import csv
import unicodedata
from datetime import date
from pathlib import Path
from html import escape
from urllib.parse import urlparse

import matplotlib.pyplot as plt
import pandas as pd
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "club-fit"
PREVIEWS = OUT / "design-previews"
AS_OF = date(2026, 7, 20)
PL_NEEDS_URL = "https://www.premierleague.com/en/news/4674463/summer-2026-transfer-window-what-does-each-premier-league-club-need"


SOURCES = [
    {"source_id": "pl_needs_2026", "publisher": "Premier League", "title": "Summer 2026 transfer window: What do each Premier League club need?", "publication_date": "2026-07-09", "url": PL_NEEDS_URL, "claim_supported": "Arsenal need anchor is direct left-winger; Chelsea need anchor is defender with back-three know-how.", "source_tier": "1"},
    {"source_id": "chelsea_official_transfers_2026", "publisher": "Chelsea FC", "title": "Summer transfers 2026: All the Chelsea ins, outs and new contracts so far", "publication_date": "", "url": "https://www.chelseafc.com/en/news/article/summer-transfers-2026-all-the-chelsea-ins-outs-and-new-contracts-so-far", "claim_supported": "Chelsea official transfer tracker checked; reviewed rumour players are not confirmed unless explicitly named.", "source_tier": "1"},
    {"source_id": "tm_arsenal_rumour_attempt", "publisher": "Transfermarkt", "title": "Arsenal FC - Club transfer rumours", "publication_date": "", "url": "https://www.transfermarkt.co.uk/arsenal-fc/geruechte/verein/11", "claim_supported": "HUMAN_CHECK_REQUIRED: page required JavaScript/anti-bot verification; no bypass attempted.", "source_tier": "3"},
    {"source_id": "tm_chelsea_rumour_attempt", "publisher": "Transfermarkt", "title": "Chelsea FC - Club transfer rumours", "publication_date": "", "url": "https://www.transfermarkt.com/fc-chelsea/geruechte/verein/631", "claim_supported": "HUMAN_CHECK_REQUIRED: page required JavaScript/anti-bot verification; no bypass attempted.", "source_tier": "3"},
    {"source_id": "sky_tzolis_arsenal", "publisher": "Sky Sports", "title": "Christos Tzolis: Arsenal agree fee with Club Brugge to sign Greek winger as replacement for Leandro Trossard", "publication_date": "2026-07-17", "url": "https://www.skysports.com/transfer/news/12691/13564048/christos-tzolis-arsenal-agree-fee-with-club-brugge-to-sign-greek-winger-as-replacement-for-leandro-trossard", "claim_supported": "Arsenal agreement reported for Tzolis as a left-wing/Trossard replacement.", "source_tier": "2"},
    {"source_id": "guardian_tzolis_arsenal", "publisher": "The Guardian", "title": "Arsenal close in on £34m deal for Club Brugge forward Christos Tzolis", "publication_date": "2026-07-16", "url": "https://www.theguardian.com/football/2026/jul/16/arsenal-34m-deal-club-brugge-forward-christos-tzolis-premier-league", "claim_supported": "Arsenal close to Tzolis and have monitored Alvarez and Barcola.", "source_tier": "2"},
    {"source_id": "independent_alvarez_arsenal", "publisher": "The Independent", "title": "Arsenal set Julian Alvarez transfer deadline as Mikel Arteta's spree laid bare", "publication_date": "2026-07-12", "url": "https://www.independent.co.uk/sport/football/arsenal-julian-alvarez-transfer-deadline-b2790584.html", "claim_supported": "Arsenal interest in Julian Alvarez reported; not official confirmation.", "source_tier": "2"},
    {"source_id": "guardian_bruno_arsenal", "publisher": "The Guardian", "title": "Arsenal on alert after Bruno Guimarães tells Newcastle he wants to leave", "publication_date": "2026-07-08", "url": "https://www.theguardian.com/football/2026/jul/08/arsenal-on-alert-after-bruno-guimaraes-tells-newcastle-he-wants-to-leave", "claim_supported": "Bruno Guimaraes Arsenal interest/availability reporting.", "source_tier": "2"},
    {"source_id": "sky_bruno_arsenal", "publisher": "Sky Sports", "title": "Bruno Guimaraes transfer news: Newcastle captain tells club he wants to join Arsenal", "publication_date": "2026-07-09", "url": "https://www.skysports.com/transfer/news/11095/13561780/bruno-guimaraes-transfer-news-newcastle-captain-tells-club-he-wants-to-join-arsenal-after-world-cup-exit-with-brazil", "claim_supported": "Sky reports Bruno wants Arsenal move, with no completed deal.", "source_tier": "2"},
    {"source_id": "sun_stones_arsenal", "publisher": "The Sun", "title": "Arsenal transfer news LIVE: John Stones targeted", "publication_date": "2026-07-20", "url": "https://www.thesun.co.uk/sport/39415117/arsenal-transfer-news-live-morgan-rogers-stones-alvarez-updates/", "claim_supported": "Low-tier reporting of Arsenal interest in John Stones.", "source_tier": "4"},
    {"source_id": "guardian_rogers_chelsea", "publisher": "The Guardian", "title": "Chelsea poised to sign Morgan Rogers from Aston Villa in record-breaking £117m deal", "publication_date": "2026-07-18", "url": "https://www.theguardian.com/football/2026/jul/18/chelsea-morgan-rogers-aston-villa-117m", "claim_supported": "Chelsea advanced reporting for Morgan Rogers; not official completion.", "source_tier": "2"},
    {"source_id": "talksport_rogers_chelsea", "publisher": "talkSPORT", "title": "What £117m Morgan Rogers transfer means for Cole Palmer and Enzo Fernandez at Chelsea", "publication_date": "2026-07-20", "url": "https://talksport.com/football/4442898/morgan-rogers-transfer-cole-palmer-enzo-fernandez-chelsea/", "claim_supported": "Morgan Rogers integration and price-risk context.", "source_tier": "2"},
    {"source_id": "talksport_lacroix_chelsea", "publisher": "talkSPORT", "title": "Chelsea hold talks with Premier League rivals over signing £55m-rated World Cup star", "publication_date": "2026-07-20", "url": "https://talksport.com/football/4441021/chelsea-talks-crystal-palace-maxence-lacroix-transfer-news/", "claim_supported": "Chelsea talks with Crystal Palace over Maxence Lacroix reported.", "source_tier": "2"},
    {"source_id": "as_carreras_chelsea", "publisher": "AS", "title": "El Chelsea se fija... en Carreras", "publication_date": "2026-06-16", "url": "https://as.com/futbol/primera/el-chelsea-se-fija-en-carreras-f202606-n/", "claim_supported": "Chelsea interest in Alvaro Carreras reported.", "source_tier": "2"},
    {"source_id": "teamtalk_cambiaso_chelsea", "publisher": "TEAMtalk", "title": "Chelsea swap deal ON for top Juventus star", "publication_date": "2026-06-19", "url": "https://www.teamtalk.com/chelsea/chelsea-hold-andrea-cambiaso-transfer-talks-swap-deal-nicolas-jackson", "claim_supported": "Low-tier reporting of Chelsea talks for Andrea Cambiaso.", "source_tier": "4"},
    {"source_id": "bundesliga_tapsoba_extension", "publisher": "Bundesliga", "title": "Edmond Tapsoba signs Bayer Leverkusen contract extension", "publication_date": "2026-04-29", "url": "https://www.bundesliga.com/en/bundesliga/news/edmond-tapsoba-bayer-leverkusen-contract-extension-37130", "claim_supported": "Tapsoba extension to 2031; no current Chelsea corroboration.", "source_tier": "1"},
]


SOURCE_VALIDATION = {
    "pl_needs_2026": {
        "http_status": "200",
        "verification_status": "VERIFIED",
        "verification_method": "MANUAL_BROWSER_CHECK",
        "claim_checked": "Premier League need anchor checked: Arsenal direct left-winger first; Chelsea defender with back-three know-how first.",
        "verification_warning": "",
    },
    "chelsea_official_transfers_2026": {
        "http_status": "200",
        "verification_status": "VERIFIED",
        "verification_method": "OFFICIAL_PAGE_INSPECTION",
        "claim_checked": "Official Chelsea tracker checked only for confirmation status; it did not confirm Morgan Rogers as completed in retrieved content.",
        "verification_warning": "No publication date visible in source register; retrieval date controls this tracker check.",
    },
    "tm_arsenal_rumour_attempt": {
        "http_status": "403",
        "verification_status": "HUMAN_CHECK_REQUIRED",
        "verification_method": "HUMAN_CHECK_REQUIRED",
        "claim_checked": "Rumour Mill status could not be verified.",
        "verification_warning": "JavaScript/anti-bot verification; no bypass attempted.",
    },
    "tm_chelsea_rumour_attempt": {
        "http_status": "403",
        "verification_status": "HUMAN_CHECK_REQUIRED",
        "verification_method": "HUMAN_CHECK_REQUIRED",
        "claim_checked": "Rumour Mill status could not be verified.",
        "verification_warning": "JavaScript/anti-bot verification; no bypass attempted.",
    },
    "sky_tzolis_arsenal": {
        "http_status": "200",
        "verification_status": "VERIFIED",
        "verification_method": "MANUAL_BROWSER_CHECK",
        "claim_checked": "Title/date and Tzolis left-wing/Trossard-replacement claim checked.",
        "verification_warning": "",
    },
    "guardian_tzolis_arsenal": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as a dated supporting report, but not reverified in this final pass.",
        "verification_warning": "Retained as lower-weight corroboration; do not treat as independently verified here.",
    },
    "independent_alvarez_arsenal": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated interest reporting, but not reverified in this final pass.",
        "verification_warning": "Treat as cited reporting, not verified claim inspection.",
    },
    "guardian_bruno_arsenal": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated interest/availability reporting, but not reverified in this final pass.",
        "verification_warning": "Treat as cited reporting, not verified claim inspection.",
    },
    "sky_bruno_arsenal": {
        "http_status": "200",
        "verification_status": "VERIFIED",
        "verification_method": "MANUAL_BROWSER_CHECK",
        "claim_checked": "Title/date and Bruno-to-Arsenal reporting status checked.",
        "verification_warning": "",
    },
    "sun_stones_arsenal": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Low-tier Stones item retained as unverified reporting only.",
        "verification_warning": "Low source tier; fit remains NOT_ASSESSED and action TACTICAL_REVIEW_ONLY.",
    },
    "guardian_rogers_chelsea": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated advanced reporting, but not reverified in this final pass.",
        "verification_warning": "Not official confirmation.",
    },
    "talksport_rogers_chelsea": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated integration context, but not reverified in this final pass.",
        "verification_warning": "Treat as cited reporting, not verified claim inspection.",
    },
    "talksport_lacroix_chelsea": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated Lacroix interest reporting, but not reverified in this final pass.",
        "verification_warning": "Fit downgraded because source does not prove Chelsea tactical suitability.",
    },
    "as_carreras_chelsea": {
        "http_status": "200",
        "verification_status": "VERIFIED",
        "verification_method": "MANUAL_BROWSER_CHECK",
        "claim_checked": "Title/date and Chelsea interest claim checked.",
        "verification_warning": "",
    },
    "teamtalk_cambiaso_chelsea": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Low-tier Cambiaso item retained as unverified reporting only.",
        "verification_warning": "Low source tier; fit remains NOT_ASSESSED and action TACTICAL_REVIEW_ONLY.",
    },
    "bundesliga_tapsoba_extension": {
        "http_status": "200",
        "verification_status": "NOT_VERIFIED",
        "verification_method": "NOT_VERIFIED",
        "claim_checked": "Used as dated contract-extension context, but not reverified in this final pass.",
        "verification_warning": "Treat as availability caution, not live Chelsea reporting.",
    },
}

REPORTING_EVIDENCE_STATUSES = {
    "OFFICIAL_CONFIRMED",
    "MULTIPLE_VERIFIED_REPORTS",
    "SINGLE_VERIFIED_REPORT",
    "UNVERIFIED_REPORT_ONLY",
    "NO_CURRENT_CORROBORATION",
    "HUMAN_CHECK_REQUIRED",
}
OFFICIAL_CONFIRMATION_STATUSES = {
    "OFFICIAL_CONFIRMED",
    "OFFICIAL_NOT_CONFIRMED",
    "NO_OFFICIAL_CONFIRMATION",
}

# Only these source-player pairs can count as player-specific reporting evidence.
# General squad-need anchors, Transfermarkt human-check rows, and official pages
# that do not name/confirm a candidate are intentionally excluded.
PLAYER_SOURCE_CLAIMS = {
    ("Christos Tzolis", "sky_tzolis_arsenal"): {"verified_player_claim": True, "official_confirmation": False, "independent": True},
    ("Christos Tzolis", "guardian_tzolis_arsenal"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Julián Alvarez", "independent_alvarez_arsenal"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Bradley Barcola", "guardian_tzolis_arsenal"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("John Stones", "sun_stones_arsenal"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Bruno Guimarães", "guardian_bruno_arsenal"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Bruno Guimarães", "sky_bruno_arsenal"): {"verified_player_claim": True, "official_confirmation": False, "independent": True},
    ("Morgan Rogers", "chelsea_official_transfers_2026"): {"verified_player_claim": False, "official_confirmation": False, "independent": False},
    ("Morgan Rogers", "guardian_rogers_chelsea"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Morgan Rogers", "talksport_rogers_chelsea"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Maxence Lacroix", "talksport_lacroix_chelsea"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Andrea Cambiaso", "teamtalk_cambiaso_chelsea"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
    ("Álvaro Carreras", "as_carreras_chelsea"): {"verified_player_claim": True, "official_confirmation": False, "independent": True},
    ("Edmond Tapsoba", "bundesliga_tapsoba_extension"): {"verified_player_claim": False, "official_confirmation": False, "independent": True},
}

DESIRED_REPORT_STATUS = {
    "Christos Tzolis": "ADVANCED_REPORT",
    "Julián Alvarez": "REPORTED_INTEREST",
    "Bradley Barcola": "REPORTED_INTEREST",
    "John Stones": "REPORTED_INTEREST",
    "Bruno Guimarães": "REPORTED_INTEREST",
    "Morgan Rogers": "ADVANCED_REPORT",
    "Maxence Lacroix": "REPORTED_INTEREST",
    "Andrea Cambiaso": "REPORTED_INTEREST",
    "Álvaro Carreras": "REPORTED_INTEREST",
    "Edmond Tapsoba": "NO_CURRENT_CORROBORATION",
}


def derive_reporting_evidence(
    player: str,
    source_ids: list[str],
    source_validation: dict[str, dict] | None = None,
    player_source_claims: dict[tuple[str, str], dict] | None = None,
    desired_status: str | None = None,
) -> dict:
    validation = source_validation or SOURCE_VALIDATION
    claim_map = player_source_claims or PLAYER_SOURCE_CLAIMS
    desired = desired_status or DESIRED_REPORT_STATUS.get(player, "REPORTED_INTEREST")

    official_confirmed = False
    official_checked_not_confirmed = False
    verified_sources: list[str] = []
    unverified_sources: list[str] = []
    independent_verified: set[str] = set()

    for sid in source_ids:
        source_status = validation[sid]["verification_status"]
        claim = claim_map.get((player, sid))
        if sid == "chelsea_official_transfers_2026" and claim and not claim["official_confirmation"]:
            official_checked_not_confirmed = True
        if not claim:
            continue
        if claim["official_confirmation"] and source_status == "VERIFIED":
            official_confirmed = True
            verified_sources.append(sid)
            continue
        if claim["verified_player_claim"] and source_status == "VERIFIED":
            verified_sources.append(sid)
            if claim["independent"]:
                independent_verified.add(sid)
        elif source_status in {"NOT_VERIFIED", "HUMAN_CHECK_REQUIRED"}:
            unverified_sources.append(sid)

    verified_count = len(verified_sources)
    unverified_count = len(unverified_sources)
    independent_count = len(independent_verified)

    if official_confirmed:
        official_status = "OFFICIAL_CONFIRMED"
        evidence_status = "OFFICIAL_CONFIRMED"
        confidence = "HIGH"
        latest_status = "CONFIRMED"
    else:
        official_status = "OFFICIAL_NOT_CONFIRMED" if official_checked_not_confirmed else "NO_OFFICIAL_CONFIRMATION"
        if verified_count >= 2 and independent_count >= 2:
            evidence_status = "MULTIPLE_VERIFIED_REPORTS"
            confidence = "HIGH"
        elif verified_count == 1:
            evidence_status = "SINGLE_VERIFIED_REPORT"
            confidence = "MEDIUM"
        elif desired == "NO_CURRENT_CORROBORATION":
            evidence_status = "NO_CURRENT_CORROBORATION"
            confidence = "UNVERIFIED"
        elif unverified_count:
            evidence_status = "UNVERIFIED_REPORT_ONLY"
            confidence = "UNVERIFIED"
        else:
            evidence_status = "HUMAN_CHECK_REQUIRED"
            confidence = "UNVERIFIED"

        if desired == "NO_CURRENT_CORROBORATION":
            latest_status = "NO_CURRENT_CORROBORATION"
        elif desired == "ADVANCED_REPORT" and verified_count:
            latest_status = "ADVANCED_REPORT"
        elif verified_count:
            latest_status = "REPORTED_INTEREST"
        elif unverified_count:
            latest_status = "RUMOUR_ONLY"
        else:
            latest_status = "NO_CURRENT_CORROBORATION"

    if official_confirmed:
        reason = "Official source confirmed the candidate-specific transfer status."
    elif verified_count >= 2 and independent_count >= 2:
        reason = "Two or more inspected independent player-specific sources support the status claim."
    elif verified_count == 1:
        reason = "One inspected player-specific source; no second verified independent corroboration."
    elif unverified_count:
        reason = "Only unverified player-specific reporting is retained; HTTP/headline metadata does not verify claims."
    elif desired == "NO_CURRENT_CORROBORATION":
        reason = "No current club-specific corroboration was verified."
    else:
        reason = "Player-specific reporting could not be inspected; human verification is required."

    return {
        "player_specific_verified_source_count": verified_count,
        "player_specific_unverified_source_count": unverified_count,
        "official_confirmation_status": official_status,
        "independent_verified_corroboration_count": independent_count,
        "reporting_evidence_status": evidence_status,
        "reporting_confidence_reason": reason,
        "latest_report_status": latest_status,
        "reporting_confidence": confidence,
    }


CANDIDATES = [
    {"club": "Arsenal", "player": "Christos Tzolis", "target_role": "Direct left-wing solution", "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;sky_tzolis_arsenal;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "HIGH", "price_risk": "UNKNOWN", "recommended_action": "ADVANCE_SCOUTING", "why": "Included because Arsenal's stated need is a direct left-winger and current reporting presents Tzolis as the clearest active left-wing solution.", "style": "Left-sided forward profile in the local identity file; the reviewed role is touchline/direct-wing coverage rather than central-forward depth.", "fit": "Best aligns with the Arsenal need anchor because the role is specifically left wing and current reporting frames him as Trossard replacement cover.", "concern": "The review has no validated local chance-creation or off-ball role model for Arsenal's left side.", "availability": "Advanced reporting is not official confirmation; Transfermarkt Rumour Mill could not be verified in this environment.", "price_reason": "Market-consensus snapshot is moderate for this set, but negotiated fee, wages and contract details are not verified here.", "warning": "Local evidence is identity and Transfermarkt market-consensus only; no Arsenal-specific sporting prediction.", "citations": "[1][5][6]"},
    {"club": "Arsenal", "player": "Julián Alvarez", "target_role": "Forward-ceiling option", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM", "source_ids": "pl_needs_2026;independent_alvarez_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included as a forward-ceiling alternative, not as the primary left-wing answer.", "style": "Centre-forward in the local file; role fit is about elite front-line optionality rather than direct left-wing coverage.", "fit": "Could raise Arsenal's forward ceiling, but the role only indirectly addresses the left-wing need anchor.", "concern": "Role priority mismatch: this is not the direct winger profile identified as Arsenal's first need.", "availability": "Reported interest only; no official confirmation and no verified Rumour Mill status.", "price_reason": "High market-consensus snapshot plus unverified fee/wage terms make price risk high.", "warning": "Do not treat market consensus as expected fee or buyer-specific contribution.", "citations": "[1][7]"},
    {"club": "Arsenal", "player": "Bradley Barcola", "target_role": "Direct left-wing solution", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM", "source_ids": "pl_needs_2026;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included because the Guardian reporting grouped him with Arsenal's left-wing search.", "style": "Left winger in the local file; reviewed as a wide one-v-one and depth option.", "fit": "Partial positional alignment with the left-wing need, but the current evidence does not prove tactical suitability beyond the broad role.", "concern": "PSG current-club context and sparse direct reporting make this more monitoring than action.", "availability": "Reported interest only; no official or verified Rumour Mill evidence.", "price_reason": "High market-consensus snapshot at a major club, with no reliable fee/wage evidence.", "warning": "No local validated scoring edge; tactical fit remains editorial.", "citations": "[1][6]"},
    {"club": "Arsenal", "player": "John Stones", "target_role": "Saliba-cover/backline contingency", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "LOW", "source_ids": "pl_needs_2026;sun_stones_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "NOT_ASSESSED", "price_risk": "UNKNOWN", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included from the fixed candidate set as a backline contingency rather than a first-priority need.", "style": "Centre-back in the local file; no sourced tactical-detail claim is relied on here.", "fit": "Could only be assessed through video/squad planning because the live link is lower confidence.", "concern": "Low-tier sourcing and role not aligned with Arsenal's primary left-wing need.", "availability": "Only lower-confidence reporting was found; Rumour Mill requires human check.", "price_reason": "Market-consensus value is lower than most candidates, but wage, availability and negotiated fee are unknown.", "warning": "Defender review abstains from attacking metrics; no validated centre-back quality model.", "citations": "[1][10]"},
    {"club": "Arsenal", "player": "Bruno Guimarães", "target_role": "Midfield-control option", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;guardian_bruno_arsenal;sky_bruno_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included as a midfield-control option with high-quality reporting, not because it is the primary need.", "style": "Central midfielder in the local file; reviewed as control/retention profile rather than left-wing solution.", "fit": "Strong player-profile hypothesis for midfield control, but it does not solve the direct-wing priority.", "concern": "High tactical appeal can distract from the stated Arsenal squad-need order.", "availability": "Strong reporting of player desire/interest, but no completed transfer.", "price_reason": "High market-consensus snapshot and likely complex Newcastle availability make risk high.", "warning": "No buyer-specific value or validated ranking is produced.", "citations": "[1][8][9]"},
    {"club": "Chelsea", "player": "Morgan Rogers", "target_role": "Rogers integration and price-risk review", "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH", "source_ids": "chelsea_official_transfers_2026;guardian_rogers_chelsea;talksport_rogers_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included because established reporting presents an advanced Chelsea move, but the task is integration review, not discovery.", "style": "Attacking midfielder in the local file; reviewed around Palmer/Fernandez integration questions from reporting.", "fit": "Could add attacking-midfield power, but this does not directly answer Chelsea's defender-with-back-three-know-how need anchor.", "concern": "Role overlap and tactical integration risk should be reviewed before treating this as squad-need fulfilment.", "availability": "Advanced reporting exists; Chelsea official tracker did not confirm completion in the retrieved page.", "price_reason": "Reported large fee context, high market-consensus snapshot, and unknown wage terms make risk high.", "warning": "Strong reporting but not official confirmation; no validated Chelsea sporting prediction.", "citations": "[2][11][12]"},
    {"club": "Chelsea", "player": "Maxence Lacroix", "target_role": "Back-three defensive need", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;talksport_lacroix_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included because Chelsea's need anchor is a defender with back-three know-how and reporting links Chelsea to Lacroix, but suitability remains unproven.", "style": "Centre-back in the local file; reviewed only as a defensive recruitment fit, not through attacker metrics.", "fit": "Broad centre-back role alignment is useful, but the cited reporting does not prove back-three experience, possession fit, or defensive quality for Chelsea.", "concern": "Local data does not validate defensive quality, possession fit, or back-three experience.", "availability": "Reported talks with Crystal Palace; no official completion.", "price_reason": "Reported fee context and Premier League seller dynamics make negotiated-price risk high.", "warning": "Centre-back quality is not assessed by attacking or shot-value metrics.", "citations": "[1][13]"},
    {"club": "Chelsea", "player": "Andrea Cambiaso", "target_role": "Left-side defensive/wing-back need", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "LOW", "source_ids": "pl_needs_2026;teamtalk_cambiaso_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "NOT_ASSESSED", "price_risk": "UNKNOWN", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included from the fixed set as a left-side defensive/wing-back option.", "style": "Left-back in the local file; wing-back suitability is not validated locally.", "fit": "Possible positional relevance, but the Chelsea link is low-tier and tactical facts are not independently sourced.", "concern": "TEAMtalk is retained only as lower-confidence reporting; no stronger source was used for a tactical claim.", "availability": "Reported interest only and requires Rumour Mill human check.", "price_reason": "Market-consensus snapshot is moderate, but fee, wage and Juventus availability are unknown.", "warning": "Low-confidence link; no validated local wing-back fit model.", "citations": "[1][15]"},
    {"club": "Chelsea", "player": "Álvaro Carreras", "target_role": "Left-side defensive/wing-back need", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM", "source_ids": "pl_needs_2026;as_carreras_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included as a left-side defensive option connected to Chelsea reporting.", "style": "Left-back in the local file; reviewed for defensive/wing-back cover rather than primary centre-back need.", "fit": "Positional fit is plausible for left-side cover but it is secondary to the back-three centre-back anchor.", "concern": "Current club and role context create availability and price questions.", "availability": "Reported interest only; no official confirmation.", "price_reason": "High market-consensus snapshot at Real Madrid plus unknown fee/wage terms makes price risk high.", "warning": "No validated local wing-back model; current-club timing is the latest local file value.", "citations": "[1][14]"},
    {"club": "Chelsea", "player": "Edmond Tapsoba", "target_role": "Back-three defensive need", "latest_report_status": "NO_CURRENT_CORROBORATION", "reporting_confidence": "UNVERIFIED", "source_ids": "pl_needs_2026;bundesliga_tapsoba_extension;tm_chelsea_rumour_attempt", "fit_rating": "NOT_ASSESSED", "price_risk": "HIGH", "recommended_action": "LOW_PRIORITY", "why": "Retained because the fixed set required him, not because current Chelsea reporting corroborated the move.", "style": "Centre-back in the local file; no current Chelsea-specific tactical claim is made.", "fit": "Back-three defensive role would match the need category, but no current Chelsea link is corroborated.", "concern": "Availability evidence points away from a live move because of the Leverkusen extension.", "availability": "Bundesliga reports a contract extension through 2031; no current Chelsea corroboration found.", "price_reason": "Contract extension materially raises availability and price risk; fee/wage information is unknown.", "warning": "No current Chelsea reporting corroborated; keep as low priority.", "citations": "[1][16]"},
]


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def load_tm() -> tuple[pd.DataFrame, pd.DataFrame]:
    players = pd.read_csv(REPO / "data" / "transfermarkt" / "players.csv.gz")
    vals = pd.read_csv(REPO / "data" / "transfermarkt" / "player_valuations.csv.gz")
    vals["date"] = pd.to_datetime(vals["date"], errors="coerce")
    return players, vals.sort_values("date").groupby("player_id", as_index=False).tail(1)


def player_lookup(players: pd.DataFrame, latest_vals: pd.DataFrame, name: str) -> dict:
    match = players[players["name"].fillna("").map(norm_name).eq(norm_name(name))]
    if len(match) != 1:
        return {"tm_player_id": "", "tm_match_status": "UNMATCHED" if len(match) == 0 else "AMBIGUOUS", "date_of_birth": "", "age_as_of_date": "", "current_club": "", "position": "", "transfermarkt_market_value_eur": "", "market_value_snapshot_date": "", "player_record_snapshot_date": "", "current_club_observation_date": ""}
    row = match.iloc[0]
    dob = pd.to_datetime(row.date_of_birth, errors="coerce")
    age = round((pd.Timestamp(AS_OF) - dob).days / 365.25, 1) if pd.notna(dob) else ""
    val = latest_vals[latest_vals.player_id.eq(row.player_id)]
    mv = row.market_value_in_eur
    snap = ""
    if len(val):
        snap = val.iloc[0].date.date().isoformat()
        mv = int(val.iloc[0].market_value_in_eur)
    return {"tm_player_id": int(row.player_id), "tm_match_status": "MATCHED", "date_of_birth": "" if pd.isna(row.date_of_birth) else str(row.date_of_birth)[:10], "age_as_of_date": age, "current_club": row.current_club_name, "position": row.sub_position if pd.notna(row.sub_position) else row.position, "transfermarkt_market_value_eur": int(mv) if pd.notna(mv) else "", "market_value_snapshot_date": snap, "player_record_snapshot_date": "latest row in local players.csv.gz; exact extraction date unavailable", "current_club_observation_date": "latest value in local players.csv.gz; exact observation date unavailable"}


def source_index() -> dict[str, dict]:
    return {s["source_id"]: {**s, "retrieval_date": str(AS_OF)} for s in SOURCES}


def build_rows() -> list[dict]:
    players, latest_vals = load_tm()
    idx = source_index()
    rows = []
    for c in CANDIDATES:
        local = player_lookup(players, latest_vals, c["player"])
        ids = c["source_ids"].split(";")
        evidence = derive_reporting_evidence(c["player"], ids)
        row = {**c, **local}
        row.update(evidence)
        row.update({
            "as_of_date": str(AS_OF),
            "transfermarkt_rumour_status": "HUMAN_CHECK_REQUIRED",
            "source_urls": " | ".join(idx[sid]["url"] for sid in ids),
            "local_data_status": "PARTIAL" if local["tm_match_status"] == "MATCHED" else "ABSTAIN",
            "local_file_loaded_date": str(AS_OF),
            "local_data_vintage": "players.csv.gz latest row; exact source observation date unavailable",
            "local_metrics_used": "identity; date of birth; current club latest local-file value; position; Transfermarkt market-consensus value at recorded snapshot",
        })
        rows.append(row)
    return rows


CSV_FIELDS = [
    "club", "player", "tm_player_id", "tm_match_status", "date_of_birth",
    "age_as_of_date", "current_club", "position", "target_role",
    "as_of_date", "transfermarkt_rumour_status",
    "transfermarkt_market_value_eur", "market_value_snapshot_date",
    "latest_report_status", "reporting_confidence", "source_urls",
    "player_specific_verified_source_count",
    "player_specific_unverified_source_count",
    "official_confirmation_status",
    "independent_verified_corroboration_count",
    "reporting_evidence_status",
    "reporting_confidence_reason",
    "source_ids", "local_data_status", "local_file_loaded_date",
    "player_record_snapshot_date", "current_club_observation_date",
    "local_data_vintage", "local_metrics_used", "why_included",
    "style_profile", "tactical_fit", "tactical_concern",
    "availability_concern", "fit_rating", "price_risk",
    "price_risk_reasoning", "data_warning", "recommended_action",
]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows([
            {
                **r,
                "why_included": r["why"],
                "style_profile": r["style"],
                "tactical_fit": r["fit"],
                "tactical_concern": r["concern"],
                "availability_concern": r["availability"],
                "price_risk_reasoning": r["price_reason"],
                "data_warning": r["warning"],
            }
            for r in rows
        ])


def write_sources(path: Path) -> None:
    fields = ["source_id", "publisher", "title", "publication_date", "retrieval_date", "url", "claim_supported", "source_tier"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{**s, "retrieval_date": str(AS_OF)} for s in SOURCES])


def write_source_validation(path: Path) -> None:
    fields = [
        "source_id", "url", "resolved_url", "http_status", "page_title",
        "publication_date", "retrieval_date", "verification_status",
        "verification_method", "claim_checked", "verification_warning",
    ]
    rows = []
    source_ids = {s["source_id"] for s in SOURCES}
    if set(SOURCE_VALIDATION) != source_ids:
        missing = source_ids - set(SOURCE_VALIDATION)
        extra = set(SOURCE_VALIDATION) - source_ids
        raise AssertionError(f"source validation records must be explicit for every source; missing={missing}, extra={extra}")
    for s in SOURCES:
        validation = SOURCE_VALIDATION[s["source_id"]]
        parsed = urlparse(s["url"])
        status = validation["http_status"]
        verified = validation["verification_status"]
        method = validation["verification_method"]
        claim = validation["claim_checked"]
        warning = validation["verification_warning"]
        if not parsed.scheme or not parsed.netloc:
            status, verified, method, claim, warning = "", "NOT_VERIFIED", "NOT_VERIFIED", "URL syntax check failed.", "Malformed URL"
        rows.append({
            "source_id": s["source_id"],
            "url": s["url"],
            "resolved_url": s["url"],
            "http_status": status,
            "page_title": s["title"],
            "publication_date": s["publication_date"],
            "retrieval_date": str(AS_OF),
            "verification_status": verified,
            "verification_method": method,
            "claim_checked": claim,
            "verification_warning": warning,
        })
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def badge(value: str) -> str:
    return value.replace("_", " ").title()


def citation_map() -> dict[str, int]:
    return {s["source_id"]: i + 1 for i, s in enumerate(SOURCES)}


def write_markdown(path: Path, rows: list[dict]) -> None:
    nums = citation_map()
    sections = []
    for club in ["Arsenal", "Chelsea"]:
        need = "direct left-winger first" if club == "Arsenal" else "experienced defender with back-three know-how first"
        sections.append(f"## {club} Need Overview\n\nPrimary need anchor: **{need}** [{nums['pl_needs_2026']}]. This is a sourced squad-needs frame, not a model output.\n")
        for r in [x for x in rows if x["club"] == club]:
            mv = f"EUR {int(r['transfermarkt_market_value_eur']):,}" if r["transfermarkt_market_value_eur"] != "" else "unavailable"
            cite_nums = " ".join(f"[{nums[sid]}]" for sid in r["source_ids"].split(";") if not sid.startswith("tm_"))
            sections.append(f"""### {r['player']}

**Target role:** {r['target_role']}

**Reporting evidence:** {badge(r['reporting_evidence_status'])}

**Reporting status:** {badge(r['latest_report_status'])} / {badge(r['reporting_confidence'])} {cite_nums}

**Reporting-confidence reason:** {r['reporting_confidence_reason']}

**Local data status:** {badge(r['local_data_status'])}

**Fit rating:** {badge(r['fit_rating'])}

**Price risk:** {badge(r['price_risk'])}

**Action:** {badge(r['recommended_action'])}

Why included: {r['why']}

Style/profile summary: {r['style']}

Specific tactical fit: {r['fit']}

Specific tactical concern: {r['concern']}

Availability/competition concern: {r['availability']}

Local evidence genuinely available: {r['local_metrics_used']}. Date of birth `{r['date_of_birth']}`, age `{r['age_as_of_date']}` as of `{r['as_of_date']}`, current club `{r['current_club']}`, position `{r['position']}`. Current-club timing is `{r['current_club_observation_date']}`.

Market-consensus snapshot: {mv} at recorded snapshot `{r['market_value_snapshot_date']}`. This is **not** fair value, not expected fee, not surplus and not buyer-specific economic value.

Price-risk reasoning: {r['price_reason']}

Data warning: {r['warning']}
""")
    table = "\n".join(f"| {r['club']} | {r['player']} | {badge(r['reporting_evidence_status'])} | {badge(r['latest_report_status'])} / {badge(r['reporting_confidence'])} | {badge(r['local_data_status'])} | {badge(r['fit_rating'])} | {badge(r['price_risk'])} | {badge(r['recommended_action'])} |" for r in rows)
    refs = "\n".join(f"{i+1}. {s['publisher']}. \"{s['title']}\". Published: {s['publication_date'] or 'not stated'}; retrieved: {AS_OF}. {s['url']}" for i, s in enumerate(SOURCES))
    md = f"""# Chelsea + Arsenal 10-Player Club-Fit Review

As-of / retrieval date: **{AS_OF}**

## Executive Summary

This is an internal, human-in-the-loop decision-support review. It is **not** a validated sporting prediction, not a buyer-specific NPV model, not a surplus ranking, not an underpriced-player claim, and not a numeric overall ranking.

The fixed review set contains exactly five Arsenal players and five Chelsea players. Transfermarkt Rumour Mill direct status is **Human Check Required** because the pages required JavaScript/anti-bot verification; no bypass was attempted.

## Methodology And Limitations

Fit labels use a transparent editorial rubric. `HIGH` requires positional alignment, sourced or locally supported role characteristics, plausible tactical use, and no major unresolved role contradiction. `MEDIUM` means partial alignment or material uncertainty. `LOW` means weak fit. `NOT_ASSESSED` means the available sources do not support a player-specific tactical judgement.

Reporting confidence is generated by a deterministic evidence policy. `VERIFIED` means the source identity/title/date and the player-specific material claim were inspected and recorded. `NOT_VERIFIED` means the source is retained only as cited reporting and does not count as substantive corroboration. `HUMAN_CHECK_REQUIRED` means access restrictions or manual-only verification prevented inspection. `HIGH` reporting confidence requires official confirmation or at least two inspected independent player-specific sources; `MEDIUM` requires one inspected credible player-specific source; `UNVERIFIED` is used where no player-specific claim was inspected successfully. HTTP 200 status, matching page titles, general squad-needs articles and articles about other players do not verify candidate-specific transfer claims.

Price risk considers market-consensus snapshot, age, reporting around likely fee where available, contract/availability evidence, wage-information availability, injury/availability concerns where sourced, and source uncertainty. `UNKNOWN` is used when market value alone is insufficient.

Market value is labelled as **Transfermarkt market-consensus value at the recorded snapshot**. It is not fair value, not expected transfer fee and not buyer-specific economic value. Missing local performance evidence remains blank and does not become zero.

The HTML/CSS previews are design prototypes using the same structured player records. The final PDF is generated by a deterministic ReportLab implementation that mirrors the selected Design A card hierarchy; it is not browser-printed from the preview HTML.

{''.join(sections)}

## Comparison / Action Table

| Club | Player | Reporting evidence | Reporting | Local data | Fit | Price risk | Action |
|---|---|---|---|---|---|---|---|
{table}

## References

{refs}
"""
    path.write_text(md)


def design_html(rows: list[dict], design: str) -> str:
    accent_a = "#b7192b"
    accent_c = "#1455a0"
    if design == "A":
        title = "Editorial Scouting Desk"
        body = "#fbfaf6"
        panel = "#ffffff"
        layout = "cards"
    else:
        title = "Club Recruitment Dashboard"
        body = "#f4f7fa"
        panel = "#ffffff"
        layout = "dashboard"
    cards = []
    for r in rows:
        accent = accent_a if r["club"] == "Arsenal" else accent_c
        mv = f"EUR {int(r['transfermarkt_market_value_eur']):,}" if r["transfermarkt_market_value_eur"] != "" else "Unavailable"
        cards.append(f"""
<article class="card" style="--accent:{accent}">
  <div class="card-head">
    <div><span class="club">{escape(r['club'])}</span><h2>{escape(r['player'])}</h2><p>{escape(r['target_role'])}</p></div>
    <div class="action">{badge(r['recommended_action'])}</div>
  </div>
  <div class="badges">
    <span>Evidence: {badge(r['reporting_evidence_status'])}</span><span>Report: {badge(r['latest_report_status'])}</span><span>Confidence: {badge(r['reporting_confidence'])}</span><span>Local: {badge(r['local_data_status'])}</span><span>Fit: {badge(r['fit_rating'])}</span><span>Risk: {badge(r['price_risk'])}</span>
  </div>
  <p><b>Reporting reason:</b> {escape(r['reporting_confidence_reason'])}</p>
  <p><b>Why:</b> {escape(r['why'])}</p>
  <p><b>Tactical summary:</b> {escape(r['fit'])}</p>
  <p><b>Concern:</b> {escape(r['concern'])}</p>
  <div class="warning"><b>Data warning:</b> {escape(r['warning'])}</div>
  <div class="market">Market-consensus snapshot: <b>{mv}</b> on {escape(str(r['market_value_snapshot_date']))}</div>
  <div class="cite">Sources: {escape(r['source_ids'])}</div>
</article>""")
    if layout == "dashboard":
        content = "".join(f"<section><h3>{club}</h3>{''.join(cards[i:i+5])}</section>" for i, club in [(0, "Arsenal"), (5, "Chelsea")])
    else:
        content = "".join(cards)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Design {design} - {title}</title>
<style>
@page {{ size:A4; margin:18mm; }}
body {{ margin:0; background:{body}; color:#172333; font:10pt/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; }}
main {{ max-width:1120px; margin:0 auto; padding:34px; }}
header {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom:2px solid #d9ded8; padding-bottom:18px; margin-bottom:22px; }}
h1 {{ font-family:Georgia,serif; font-size:34px; margin:0; letter-spacing:0; }}
h2 {{ margin:0; font-size:20px; }}
h3 {{ border-left:5px solid #667; padding-left:10px; font-size:22px; }}
.deck {{ max-width:680px; color:#52606d; }}
.grid {{ display:grid; grid-template-columns:{'1fr 1fr' if layout == 'dashboard' else 'repeat(2,minmax(0,1fr))'}; gap:16px; }}
.card {{ background:{panel}; border:1px solid #d8ddd8; border-top:5px solid var(--accent); border-radius:10px; padding:15px; break-inside:avoid; box-shadow:0 8px 20px rgba(20,35,50,.06); }}
.card-head {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
.club {{ color:var(--accent); font-weight:700; text-transform:uppercase; font-size:10px; }}
.action {{ background:#edf3ec; border:1px solid #cfdccc; border-radius:999px; padding:5px 8px; font-weight:700; white-space:nowrap; }}
.badges {{ display:flex; flex-wrap:wrap; gap:6px; margin:10px 0; }}
.badges span {{ background:#eef1f4; border:1px solid #d8dde3; border-radius:999px; padding:3px 7px; font-size:9px; }}
.warning {{ background:#fff6e5; border-left:4px solid #d39b2a; padding:8px; margin:8px 0; }}
.market,.cite {{ color:#596774; font-size:9px; margin-top:7px; }}
section {{ display:flex; flex-direction:column; gap:12px; }}
</style></head>
<body><main>
<header><div><h1>Design {design}: {title}</h1><p class="deck">As-of {AS_OF}. Editorial decision support only: no validated sporting prediction, no NPV, no surplus, no underpriced-player claim, no ranking.</p></div></header>
<div class="grid">{content}</div>
</main></body></html>"""


def draw_preview(path: Path, rows: list[dict], title: str, palette: tuple[str, str]) -> None:
    fig, ax = plt.subplots(figsize=(11, 15))
    ax.axis("off")
    ax.set_title(title, fontsize=20, loc="left", color=palette[0], pad=18, weight="bold")
    y = 0.93
    for r in rows:
        ax.add_patch(plt.Rectangle((0.02, y - 0.075), 0.96, 0.07, color="white", ec="#d7dde2", lw=1))
        accent = "#b7192b" if r["club"] == "Arsenal" else "#1455a0"
        ax.add_patch(plt.Rectangle((0.02, y - 0.075), 0.01, 0.07, color=accent, ec=accent))
        ax.text(0.04, y - 0.022, r["player"], fontsize=12, weight="bold", color=palette[0])
        ax.text(0.04, y - 0.052, r["target_role"], fontsize=8.5, color="#596774")
        ax.text(0.34, y - 0.025, badge(r["reporting_evidence_status"]), fontsize=7.7, bbox={"boxstyle": "round,pad=.22", "fc": palette[1], "ec": "none"})
        ax.text(0.52, y - 0.025, badge(r["reporting_confidence"]), fontsize=8.0)
        ax.text(0.63, y - 0.025, f"Fit {badge(r['fit_rating'])}", fontsize=8.0)
        ax.text(0.74, y - 0.025, f"Risk {badge(r['price_risk'])}", fontsize=8.0)
        ax.text(0.84, y - 0.025, badge(r["recommended_action"]), fontsize=7.7)
        y -= 0.085
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def write_previews(rows: list[dict]) -> None:
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    draw_preview(PREVIEWS / "design-a-editorial-scouting-desk.png", rows, "Design A - Editorial Scouting Desk", ("#18324a", "#dfeee5"))
    draw_preview(PREVIEWS / "design-b-club-recruitment-dashboard.png", rows, "Design B - Club Recruitment Dashboard", ("#24364b", "#d8e5f2"))
    (PREVIEWS / "design-a-editorial-scouting-desk.html").write_text(design_html(rows, "A"))
    (PREVIEWS / "design-b-club-recruitment-dashboard.html").write_text(design_html(rows, "B"))
    (PREVIEWS / "design-decision.md").write_text("# Club-Fit Design Decision\n\nDesign A remains the selected editorial direction because the review is citation-heavy and caveat-sensitive. The final visual MVP uses an 8-page deterministic ReportLab implementation: cover/decision frame, two Arsenal candidate pages, two Chelsea candidate pages, a cross-candidate evidence/workflow page, and two methodology/reference pages.\n\nThe fixed ten-player set and accepted evidence classifications are preserved. The redesign changes presentation only: structured card headers, six badge dimensions per player, restrained Arsenal/Chelsea accents, non-ranking comparison table, workflow panel, readable references and rendered-page QA artifacts.\n\nThe committed HTML/CSS files are design prototypes. The final PDF is generated by the deterministic ReportLab renderer in `scripts/generate_club_fit_review.py`; it is not browser-printed from the HTML prototypes. Rendered PNG pages and the contact sheet are generated with `python3 scripts/render_club_fit_pdf.py` under `reports/club-fit/rendered-pages/` for human visual inspection.\n")


def para(text: str, style) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;"), style)


BADGE_STYLES = {
    "OFFICIAL_CONFIRMED": ("#dfeee5", "#2f7d46"),
    "MULTIPLE_VERIFIED_REPORTS": ("#dfeee5", "#2f7d46"),
    "SINGLE_VERIFIED_REPORT": ("#dfeee5", "#2f7d46"),
    "HIGH": ("#dfeee5", "#2f7d46"),
    "ADVANCE_SCOUTING": ("#dfeee5", "#2f7d46"),
    "MEDIUM": ("#fff3cf", "#9a6a00"),
    "PARTIAL": ("#fff3cf", "#9a6a00"),
    "MONITOR_PRICE": ("#e5eef8", "#1455a0"),
    "TACTICAL_REVIEW_ONLY": ("#e5eef8", "#1455a0"),
    "LOW": ("#fde1dc", "#b33a2b"),
    "UNVERIFIED": ("#fde1dc", "#b33a2b"),
    "UNVERIFIED_REPORT_ONLY": ("#fde1dc", "#b33a2b"),
    "NO_CURRENT_CORROBORATION": ("#f0f2f4", "#586270"),
    "NOT_ASSESSED": ("#f0f2f4", "#586270"),
    "UNKNOWN": ("#f0f2f4", "#586270"),
    "LOW_PRIORITY": ("#f0f2f4", "#586270"),
    "ABSTAIN": ("#f0f2f4", "#586270"),
}


def euro(value: object) -> str:
    return "Unavailable" if value == "" else f"EUR {int(value):,}"


def first_sentence(text: str) -> str:
    parts = text.split(". ")
    return parts[0].rstrip(".") + "." if parts else text


def badge_table(items: list[tuple[str, str]], style: ParagraphStyle, width: float) -> Table:
    cols = 3
    rows = []
    for i in range(0, len(items), cols):
        row = []
        for label, value in items[i:i + cols]:
            fill, stroke = BADGE_STYLES.get(value, ("#eef1f4", "#607080"))
            row.append(para(f"<b>{label}:</b> {badge(value)}", style))
        while len(row) < cols:
            row.append("")
        rows.append(row)
    table = Table(rows, colWidths=[width / cols] * cols, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_idx, row_items in enumerate(rows):
        for col_idx, _ in enumerate(row_items):
            if row_items[col_idx] == "":
                continue
            value = items[row_idx * cols + col_idx][1]
            fill, stroke = BADGE_STYLES.get(value, ("#eef1f4", "#607080"))
            commands.extend([
                ("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor(fill)),
                ("BOX", (col_idx, row_idx), (col_idx, row_idx), 0.55, colors.HexColor(stroke)),
            ])
    table.setStyle(TableStyle(commands))
    return table


def write_pdf(path: Path, rows: list[dict]) -> None:
    rl_config.invariant = 1
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleLocal", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#14283a"), alignment=TA_LEFT)
    subtitle = ParagraphStyle("SubtitleLocal", parent=styles["BodyText"], fontName="Helvetica", fontSize=11, leading=14, textColor=colors.HexColor("#44515e"), spaceAfter=5)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=18, spaceBefore=4, spaceAfter=6, textColor=colors.HexColor("#14283a"))
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=3, spaceAfter=3, textColor=colors.HexColor("#14283a"))
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.8, leading=12, spaceAfter=4, textColor=colors.HexColor("#26323d"))
    small = ParagraphStyle("Small", parent=body, fontSize=9.5, leading=11, spaceAfter=2)
    tiny = ParagraphStyle("Tiny", parent=body, fontSize=9.5, leading=10.5, spaceAfter=1)
    badge_style = ParagraphStyle("Badge", parent=body, fontName="Helvetica-Bold", fontSize=9.5, leading=10.5, textColor=colors.HexColor("#1c2732"), alignment=TA_CENTER)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.15*cm, leftMargin=1.15*cm, topMargin=1.05*cm, bottomMargin=1.15*cm)

    nums = citation_map()

    page_w, _ = A4
    content_w = page_w - doc.leftMargin - doc.rightMargin
    arsenal = [x for x in rows if x["club"] == "Arsenal"]
    chelsea = [x for x in rows if x["club"] == "Chelsea"]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9.5)
        canvas.setFillColor(colors.HexColor("#66717d"))
        canvas.drawString(doc.leftMargin, 0.55 * cm, f"Internal evidence-review MVP | Retrieved {AS_OF}")
        canvas.drawRightString(page_w - doc.rightMargin, 0.55 * cm, f"Page {_doc.page}")
        canvas.restoreState()

    def panel(title_text: str, paragraphs: list[str], accent: str = "#d8dee6", width: float | None = None) -> Table:
        bits = [para(title_text, h3)] + [para(p, small) for p in paragraphs]
        table = Table([[bits]], colWidths=[width or content_w], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.65, colors.HexColor("#cfd7df")),
            ("LINEABOVE", (0, 0), (-1, 0), 3, colors.HexColor(accent)),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def card(r: dict, compact: bool = False) -> list:
        cite_nums = " ".join(f"[{nums[sid]}]" for sid in r["source_ids"].split(";") if not sid.startswith("tm_"))
        accent_hex = "#b7192b" if r["club"] == "Arsenal" else "#1455a0"
        accent = colors.HexColor(accent_hex)
        header = Table(
            [[
                para(f"<b>{r['player']}</b><br/><font size='9.5'>{r['position']} | {r['current_club']} -> {r['club']}</font>", h3),
                para(f"<b>{euro(r['transfermarkt_market_value_eur'])}</b><br/><font size='9.5'>Market-consensus snapshot<br/>{r['market_value_snapshot_date']}</font>", tiny),
            ]],
            colWidths=[11.35 * cm, 4.2 * cm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        badges = badge_table([
            ("Evidence", r["reporting_evidence_status"]),
            ("Confidence", r["reporting_confidence"]),
            ("Local", r["local_data_status"]),
            ("Fit", r["fit_rating"]),
            ("Price risk", r["price_risk"]),
            ("Action", r["recommended_action"]),
        ], badge_style, 15.55 * cm)
        bits = [header, Spacer(1, 0.08 * cm), badges, Spacer(1, 0.08 * cm)]
        card_rows = [
            ("Why the club is linked", r["why"]),
            ("Tactical fit", r["fit"]),
            ("Evidence limitations", f"{first_sentence(r['reporting_confidence_reason'])} {first_sentence(r['warning'])}"),
            ("Next action", f"{badge(r['recommended_action'])}: {first_sentence(r['price_reason'])}"),
        ]
        if compact:
            card_rows = [(label, first_sentence(val)) for label, val in card_rows]
        for label, val in card_rows:
            bits.append(para(f"<b>{label}:</b> {val}", small))
        bits.append(para(f"<b>Citations:</b> {cite_nums or 'None'}", tiny))
        box = Table([[bits]], colWidths=[18.2*cm])
        box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#cfd7df")),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEABOVE", (0, 0), (-1, 0), 3, accent),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ]))
        return [KeepTogether([box, Spacer(1, 0.16*cm)])]

    def counts_table() -> Table:
        def counts(field: str) -> str:
            vals = pd.Series([r[field] for r in rows]).value_counts().sort_index()
            return "; ".join(f"{badge(k)} {v}" for k, v in vals.items())
        table = Table([
            [para("<b>Reporting evidence</b>", small), para(counts("reporting_evidence_status"), small)],
            [para("<b>Reporting confidence</b>", small), para(counts("reporting_confidence"), small)],
            [para("<b>Recommended actions</b>", small), para(counts("recommended_action"), small)],
        ], colWidths=[4.2 * cm, 13.9 * cm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd7df")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dce2e8")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f5f7")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def comparison_table() -> Table:
        data = [[
            para("<b>Player</b>", tiny),
            para("<b>Club</b>", tiny),
            para("<b>Evidence</b>", tiny),
            para("<b>Conf.</b>", tiny),
            para("<b>Local</b>", tiny),
            para("<b>Fit</b>", tiny),
            para("<b>Risk</b>", tiny),
            para("<b>Action</b>", tiny),
        ]] + [[
            para(r["player"], tiny),
            para(r["club"], tiny),
            para(badge(r["reporting_evidence_status"]), tiny),
            para(badge(r["reporting_confidence"]), tiny),
            para(badge(r["local_data_status"]), tiny),
            para(badge(r["fit_rating"]), tiny),
            para(badge(r["price_risk"]), tiny),
            para(badge(r["recommended_action"]), tiny),
        ] for r in rows]
        table = Table(data, colWidths=[2.5*cm, 1.7*cm, 3.2*cm, 2.15*cm, 1.5*cm, 1.9*cm, 1.8*cm, 3.35*cm], repeatRows=1)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#14283a")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfd7df")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for row_idx, r in enumerate(rows, 1):
            commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#fff8f8" if r["club"] == "Arsenal" else "#f5f9ff")))
        table.setStyle(TableStyle(commands))
        return table

    def reference_table(start: int = 1, end: int | None = None) -> Table:
        validation = SOURCE_VALIDATION
        cells = []
        for i, s in enumerate(SOURCES, 1):
            if i < start or (end is not None and i > end):
                continue
            status = validation[s["source_id"]]["verification_status"]
            warn = validation[s["source_id"]]["verification_warning"]
            url = s["url"].replace("/", "/<wbr/>").replace("-", "-<wbr/>")
            marker = " HUMAN CHECK REQUIRED" if status == "HUMAN_CHECK_REQUIRED" else ""
            warning = f"<br/><b>Note:</b> {warn}" if warn else ""
            cells.append(para(
                f"<b>[{i}] {s['publisher']}</b> | {badge(status)}{marker}<br/>"
                f"{s['title']}<br/>Published: {s['publication_date'] or 'not stated'}; retrieved: {AS_OF}<br/>"
                f"<font color='#44515e'>{url}</font>{warning}",
                tiny,
            ))
        rows_out = []
        for i in range(0, len(cells), 2):
            rows_out.append([cells[i], cells[i + 1] if i + 1 < len(cells) else ""])
        table = Table(rows_out, colWidths=[8.9*cm, 8.9*cm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#cfd7df")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e7ec")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    story = [
        para("Chelsea + Arsenal 10-Player Club-Fit Review", title),
        para(f"Retrieval date: <b>{AS_OF}</b> | Internal evidence-review MVP", subtitle),
        panel("Decision Frame", [
            "This product turns a fixed ten-player candidate set into a recruitment evidence dossier for human review.",
            "It separates transfer-link reporting, local-data coverage, tactical-fit assessment, price-risk classification and recommended next action.",
        ], "#14283a"),
        Spacer(1, 0.18 * cm),
        panel("Limitation Banner", [
            "Not a ranking, not a validated scouting model, not a validated sporting prediction, not buyer-specific NPV, not a surplus claim, and not an underpriced-player claim.",
            "Market-consensus values are context snapshots only. They are not expected fees or economic valuations.",
        ], "#b33a2b"),
        Spacer(1, 0.18 * cm),
        para("Evidence Status Legend", h2),
        badge_table([
            ("Verified", "SINGLE_VERIFIED_REPORT"),
            ("Partial", "MEDIUM"),
            ("Unverified", "UNVERIFIED_REPORT_ONLY"),
            ("Human check", "TACTICAL_REVIEW_ONLY"),
            ("Unavailable", "UNKNOWN"),
            ("Follow-up", "MONITOR_PRICE"),
        ], badge_style, content_w),
        Spacer(1, 0.2 * cm),
        panel("Club-Level Needs", [
            f"Arsenal: direct left-winger first [{nums['pl_needs_2026']}]. Candidate pages preserve the fixed review set and show non-wing alternatives as secondary or contingency reviews.",
            f"Chelsea: defender with back-three know-how first [{nums['pl_needs_2026']}]. Attacking or left-side profiles remain integration or monitoring reviews where evidence requires it.",
        ], "#6f7781"),
        Spacer(1, 0.2 * cm),
        counts_table(),
        PageBreak(),
    ]

    story.extend([para("Arsenal Candidates", h2), para("Page 1 of the Arsenal review: two full cards, using Arsenal red as the section accent.", body)])
    for r in arsenal[:2]:
        story.extend(card(r))
    story.append(PageBreak())
    story.extend([para("Arsenal Candidates", h2), para("Page 2 of the Arsenal review: remaining candidates plus the needs-control panel; this is not an ordered shortlist.", body)])
    for r in arsenal[2:]:
        story.extend(card(r, compact=True))
    story.append(panel("Arsenal Comparison Lens", [
        "Tzolis and Barcola are the direct left-wing profiles in this fixed set. Alvarez and Bruno Guimaraes remain secondary quality/context reviews. Stones stays tactical-review-only because the link is lower confidence and the role is a contingency.",
    ], "#b7192b"))
    story.append(PageBreak())

    story.extend([para("Chelsea Candidates", h2), para("Page 1 of the Chelsea review: two full cards, using Chelsea blue as the section accent.", body)])
    for r in chelsea[:2]:
        story.extend(card(r))
    story.append(PageBreak())
    story.extend([para("Chelsea Candidates", h2), para("Page 2 of the Chelsea review: remaining candidates plus the needs-control panel; this is not an ordered shortlist.", body)])
    for r in chelsea[2:]:
        story.extend(card(r, compact=True))
    story.append(panel("Chelsea Comparison Lens", [
        "Lacroix and Tapsoba are centre-back need-category names, but neither has a validated Chelsea fit model here. Carreras and Cambiaso are left-side defensive reviews. Rogers is an integration and price-risk review, not evidence that the defensive need has been solved.",
    ], "#1455a0"))
    story.append(PageBreak())

    story.extend([
        para("Cross-Candidate Evidence And Workflow", h2),
        para("The table below is deliberately not a ranking. It preserves the fixed branch order and compares evidence dimensions only.", body),
        comparison_table(),
        Spacer(1, 0.25 * cm),
        panel("Next Workflow By Action Category", [
            "Advance Scouting: video, role-specific scout notes and medical/availability checks before any recruitment recommendation.",
            "Monitor Price: keep the name live only while fee, wage and availability context remain unresolved.",
            "Tactical Review Only: do not progress on link strength alone; require staff review of role fit and source corroboration.",
            "Low Priority: retain for audit trail, but do not treat as active work without fresh corroboration.",
        ], "#6f7781"),
        PageBreak(),
    ])

    story.extend([
        para("Methodology, Limitations And References", h2),
        panel("Evidence Policy Summary", [
            "Reporting confidence is generated by deterministic source rules. HIGH requires official confirmation or at least two inspected independent player-specific sources; MEDIUM requires one inspected player-specific source; UNVERIFIED means no inspected player-specific claim was available.",
            "Tactical fit is separate from reporting confidence. A strong link can still require tactical review, and a plausible role can still lack source corroboration.",
            "Local data is limited to identity, current-club/position context and Transfermarkt market-consensus values. Missing performance evidence is not treated as zero.",
            "Human checks are still required for restricted Rumour Mill pages, tactical video review, medical availability, wage detail, contract clauses and any deal-confirmation workflow.",
        ], "#14283a"),
        Spacer(1, 0.16 * cm),
        para("References 1-8", h2),
        reference_table(1, 8),
        PageBreak(),
        para("References 9-16 And Human Checks", h2),
        para("Verification status is shown for each source. Human-check-required rows are explicitly marked; no unsupported claim is made that every cited source was verified.", body),
        reference_table(9, 16),
        Spacer(1, 0.16 * cm),
        panel("Human Checks Still Required", [
            "Restricted Rumour Mill pages require manual review. Staff review is also required for video fit, medical availability, wage detail, contract clauses and deal confirmation before any recruitment decision.",
        ], "#b33a2b"),
    ])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    write_csv(OUT / "chelsea-arsenal-player-review.csv", rows)
    write_sources(OUT / "source-register.csv")
    write_source_validation(OUT / "source-validation.csv")
    write_markdown(OUT / "chelsea-arsenal-player-review.md", rows)
    write_previews(rows)
    write_pdf(OUT / "chelsea-arsenal-player-review.pdf", rows)
    for p in ["chelsea-arsenal-player-review.csv", "source-register.csv", "source-validation.csv", "chelsea-arsenal-player-review.md", "chelsea-arsenal-player-review.pdf"]:
        print(OUT / p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
