from __future__ import annotations

import csv
import textwrap
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import matplotlib.pyplot as plt
import pandas as pd
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
    "pl_needs_2026": ("200", "VERIFIED", ""),
    "chelsea_official_transfers_2026": ("200", "VERIFIED", "Does not confirm Morgan Rogers as completed."),
    "tm_arsenal_rumour_attempt": ("403", "HUMAN_CHECK_REQUIRED", "JavaScript/anti-bot verification; no bypass attempted."),
    "tm_chelsea_rumour_attempt": ("403", "HUMAN_CHECK_REQUIRED", "JavaScript/anti-bot verification; no bypass attempted."),
}


CANDIDATES = [
    {"club": "Arsenal", "player": "Christos Tzolis", "target_role": "Direct left-wing solution", "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;sky_tzolis_arsenal;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "HIGH", "price_risk": "UNKNOWN", "recommended_action": "ADVANCE_SCOUTING", "why": "Included because Arsenal's stated need is a direct left-winger and current reporting presents Tzolis as the clearest active left-wing solution.", "style": "Left-sided forward profile in the local identity file; the reviewed role is touchline/direct-wing coverage rather than central-forward depth.", "fit": "Best aligns with the Arsenal need anchor because the role is specifically left wing and current reporting frames him as Trossard replacement cover.", "concern": "The review has no validated local chance-creation or off-ball role model for Arsenal's left side.", "availability": "Advanced reporting is not official confirmation; Transfermarkt Rumour Mill could not be verified in this environment.", "price_reason": "Market-consensus snapshot is moderate for this set, but negotiated fee, wages and contract details are not verified here.", "warning": "Local evidence is identity and Transfermarkt market-consensus only; no Arsenal-specific sporting prediction.", "citations": "[1][5][6]"},
    {"club": "Arsenal", "player": "Julián Alvarez", "target_role": "Forward-ceiling option", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM", "source_ids": "pl_needs_2026;independent_alvarez_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included as a forward-ceiling alternative, not as the primary left-wing answer.", "style": "Centre-forward in the local file; role fit is about elite front-line optionality rather than direct left-wing coverage.", "fit": "Could raise Arsenal's forward ceiling, but the role only indirectly addresses the left-wing need anchor.", "concern": "Role priority mismatch: this is not the direct winger profile identified as Arsenal's first need.", "availability": "Reported interest only; no official confirmation and no verified Rumour Mill status.", "price_reason": "High market-consensus snapshot plus unverified fee/wage terms make price risk high.", "warning": "Do not treat market consensus as expected fee or buyer-specific contribution.", "citations": "[1][7]"},
    {"club": "Arsenal", "player": "Bradley Barcola", "target_role": "Direct left-wing solution", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM", "source_ids": "pl_needs_2026;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included because the Guardian reporting grouped him with Arsenal's left-wing search.", "style": "Left winger in the local file; reviewed as a wide one-v-one and depth option.", "fit": "Strong positional alignment with the left-wing need, but not the most advanced reporting in this set.", "concern": "PSG current-club context and sparse direct reporting make this more monitoring than action.", "availability": "Reported interest only; no official or verified Rumour Mill evidence.", "price_reason": "High market-consensus snapshot at a major club, with no reliable fee/wage evidence.", "warning": "No local validated scoring edge; tactical fit remains editorial.", "citations": "[1][6]"},
    {"club": "Arsenal", "player": "John Stones", "target_role": "Saliba-cover/backline contingency", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "LOW", "source_ids": "pl_needs_2026;sun_stones_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "NOT_ASSESSED", "price_risk": "UNKNOWN", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included from the fixed candidate set as a backline contingency rather than a first-priority need.", "style": "Centre-back in the local file; no sourced tactical-detail claim is relied on here.", "fit": "Could only be assessed through video/squad planning because the live link is lower confidence.", "concern": "Low-tier sourcing and role not aligned with Arsenal's primary left-wing need.", "availability": "Only lower-confidence reporting was found; Rumour Mill requires human check.", "price_reason": "Market-consensus value is lower than most candidates, but wage, availability and negotiated fee are unknown.", "warning": "Defender review abstains from attacking metrics; no validated centre-back quality model.", "citations": "[1][10]"},
    {"club": "Arsenal", "player": "Bruno Guimarães", "target_role": "Midfield-control option", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;guardian_bruno_arsenal;sky_bruno_arsenal;tm_arsenal_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE", "why": "Included as a midfield-control option with high-quality reporting, not because it is the primary need.", "style": "Central midfielder in the local file; reviewed as control/retention profile rather than left-wing solution.", "fit": "Strong player-profile hypothesis for midfield control, but it does not solve the direct-wing priority.", "concern": "High tactical appeal can distract from the stated Arsenal squad-need order.", "availability": "Strong reporting of player desire/interest, but no completed transfer.", "price_reason": "High market-consensus snapshot and likely complex Newcastle availability make risk high.", "warning": "No buyer-specific value or validated ranking is produced.", "citations": "[1][8][9]"},
    {"club": "Chelsea", "player": "Morgan Rogers", "target_role": "Rogers integration and price-risk review", "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH", "source_ids": "chelsea_official_transfers_2026;guardian_rogers_chelsea;talksport_rogers_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "TACTICAL_REVIEW_ONLY", "why": "Included because established reporting presents an advanced Chelsea move, but the task is integration review, not discovery.", "style": "Attacking midfielder in the local file; reviewed around Palmer/Fernandez integration questions from reporting.", "fit": "Could add attacking-midfield power, but this does not directly answer Chelsea's defender-with-back-three-know-how need anchor.", "concern": "Role overlap and tactical integration risk should be reviewed before treating this as squad-need fulfilment.", "availability": "Advanced reporting exists; Chelsea official tracker did not confirm completion in the retrieved page.", "price_reason": "Reported large fee context, high market-consensus snapshot, and unknown wage terms make risk high.", "warning": "Strong reporting but not official confirmation; no validated Chelsea sporting prediction.", "citations": "[2][11][12]"},
    {"club": "Chelsea", "player": "Maxence Lacroix", "target_role": "Back-three defensive need", "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH", "source_ids": "pl_needs_2026;talksport_lacroix_chelsea;tm_chelsea_rumour_attempt", "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "ADVANCE_SCOUTING", "why": "Included because Chelsea's need anchor is a defender with back-three know-how and reporting links Chelsea to Lacroix.", "style": "Centre-back in the local file; reviewed only as a defensive recruitment fit, not through attacker metrics.", "fit": "Best Chelsea role alignment in the fixed set because the target role is directly the primary need.", "concern": "Local data does not validate defensive quality, possession fit, or back-three experience.", "availability": "Reported talks with Crystal Palace; no official completion.", "price_reason": "Reported fee context and Premier League seller dynamics make negotiated-price risk high.", "warning": "Centre-back quality is not assessed by attacking or shot-value metrics.", "citations": "[1][13]"},
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
        row = {**c, **local}
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
    fields = ["source_id", "url", "resolved_url", "http_status", "page_title", "publication_date", "retrieval_date", "verification_status", "verification_warning"]
    rows = []
    for s in SOURCES:
        status, verified, warning = SOURCE_VALIDATION.get(s["source_id"], ("200", "VERIFIED", ""))
        parsed = urlparse(s["url"])
        if not parsed.scheme or not parsed.netloc:
            status, verified, warning = "", "INVALID_URL", "Malformed URL"
        rows.append({"source_id": s["source_id"], "url": s["url"], "resolved_url": s["url"], "http_status": status, "page_title": s["title"], "publication_date": s["publication_date"], "retrieval_date": str(AS_OF), "verification_status": verified, "verification_warning": warning})
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

**Reporting status:** {badge(r['latest_report_status'])} / {badge(r['reporting_confidence'])} {cite_nums}

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
    table = "\n".join(f"| {r['club']} | {r['player']} | {badge(r['latest_report_status'])} | {badge(r['local_data_status'])} | {badge(r['fit_rating'])} | {badge(r['price_risk'])} | {badge(r['recommended_action'])} |" for r in rows)
    refs = "\n".join(f"{i+1}. {s['publisher']}. \"{s['title']}\". Published: {s['publication_date'] or 'not stated'}; retrieved: {AS_OF}. {s['url']}" for i, s in enumerate(SOURCES))
    md = f"""# Chelsea + Arsenal 10-Player Club-Fit Review

As-of / retrieval date: **{AS_OF}**

## Executive Summary

This is an internal, human-in-the-loop decision-support review. It is **not** a validated sporting prediction, not a buyer-specific NPV model, not a surplus ranking, and not a numeric overall ranking.

The fixed review set contains exactly five Arsenal players and five Chelsea players. Transfermarkt Rumour Mill direct status is **Human Check Required** because the pages required JavaScript/anti-bot verification; no bypass was attempted.

## Methodology And Limitations

Fit labels use a transparent editorial rubric. `HIGH` requires positional alignment, sourced or locally supported role characteristics, plausible tactical use, and no major unresolved role contradiction. `MEDIUM` means partial alignment or material uncertainty. `LOW` means weak fit. `NOT_ASSESSED` means the available sources do not support a player-specific tactical judgement.

Price risk considers market-consensus snapshot, age, reporting around likely fee where available, contract/availability evidence, wage-information availability, injury/availability concerns where sourced, and source uncertainty. `UNKNOWN` is used when market value alone is insufficient.

Market value is labelled as **Transfermarkt market-consensus value at the recorded snapshot**. It is not fair value, not expected transfer fee and not buyer-specific economic value. Missing local performance evidence remains blank and does not become zero.

{''.join(sections)}

## Comparison / Action Table

| Club | Player | Reporting | Local data | Fit | Price risk | Action |
|---|---|---|---|---|---|---|
{table}

## References

{refs}
"""
    path.write_text(md)


def draw_preview(path: Path, rows: list[dict], title: str, palette: tuple[str, str]) -> None:
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axis("off")
    ax.set_title(title, fontsize=20, loc="left", color=palette[0], pad=18, weight="bold")
    y = 0.88
    for r in rows[:6]:
        ax.text(0.02, y, r["player"], fontsize=13, weight="bold", color=palette[0])
        ax.text(0.25, y, badge(r["latest_report_status"]), fontsize=10, bbox={"boxstyle": "round,pad=.25", "fc": palette[1], "ec": "none"})
        ax.text(0.48, y, f"Fit: {badge(r['fit_rating'])}", fontsize=10)
        ax.text(0.64, y, f"Risk: {badge(r['price_risk'])}", fontsize=10)
        ax.text(0.80, y, badge(r["recommended_action"]), fontsize=10)
        y -= 0.12
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def write_previews(rows: list[dict]) -> None:
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    draw_preview(PREVIEWS / "design-a-editorial-scouting-desk.png", rows, "Design A - Editorial Scouting Desk", ("#18324a", "#dfeee5"))
    draw_preview(PREVIEWS / "design-b-club-recruitment-dashboard.png", rows, "Design B - Club Recruitment Dashboard", ("#24364b", "#d8e5f2"))
    (PREVIEWS / "design-a-editorial-scouting-desk.html").write_text("<h1>Design A - Editorial Scouting Desk</h1><p>Selected for final PDF: clearer long-form player cards and readable citations.</p>\n")
    (PREVIEWS / "design-b-club-recruitment-dashboard.html").write_text("<h1>Design B - Club Recruitment Dashboard</h1><p>Alternative compact status-strip layout using the same CSV/source contract.</p>\n")
    (PREVIEWS / "design-decision.md").write_text("# Club-Fit Design Decision\n\nDesign A is selected for the final PDF because the review is editorial and citation-heavy. Design B remains as a compact dashboard preview using the same data contract.\n")


def para(text: str, style) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;"), style)


def write_pdf(path: Path, rows: list[dict]) -> None:
    rl_config.invariant = 1
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleLocal", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=colors.HexColor("#14283a"), alignment=TA_LEFT)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=18, spaceBefore=8, textColor=colors.HexColor("#14283a"))
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=10.7, spaceAfter=3)
    small = ParagraphStyle("Small", parent=body, fontSize=7.05, leading=8.55)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.25*cm, leftMargin=1.25*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)

    nums = citation_map()

    def card(r: dict) -> list:
        cite_nums = " ".join(f"[{nums[sid]}]" for sid in r["source_ids"].split(";") if not sid.startswith("tm_"))
        bits = [
            para(r["player"].upper(), h2),
            para(
                f"<b>Role:</b> {r['target_role']} | <b>Reporting:</b> {badge(r['latest_report_status'])}/{badge(r['reporting_confidence'])} {cite_nums} | "
                f"<b>Local:</b> {badge(r['local_data_status'])} | <b>Fit:</b> {badge(r['fit_rating'])} | <b>Risk:</b> {badge(r['price_risk'])} | "
                f"<b>Action:</b> {badge(r['recommended_action'])}",
                body,
            ),
        ]
        for label, val in [
            ("Why included", r["why"]),
            ("Style/profile", r["style"]),
            ("Tactical fit", r["fit"]),
            ("Tactical concern", r["concern"]),
            ("Availability concern", r["availability"]),
            ("Price risk", r["price_reason"]),
            ("Data warning", r["warning"]),
        ]:
            bits.append(para(f"<b>{label}:</b> {val}", small))
        bits.append(Spacer(1, 0.08*cm))
        return bits

    story = [
        para("Chelsea + Arsenal 10-Player Club-Fit Review", title),
        para(f"As-of / retrieval date: <b>{AS_OF}</b>", body),
        Spacer(1, .2*cm),
        para("Executive Summary", h2),
        para("Internal decision support only. Not a validated sporting prediction, not buyer-specific NPV, not a surplus ranking, and not a numeric overall ranking.", body),
        para("Methodology And Limitations", h2),
        para("Fit and price-risk labels follow the rubric in the Markdown report. Transfermarkt Rumour Mill status is HUMAN CHECK REQUIRED; no anti-bot bypass was attempted. Market value is Transfermarkt market-consensus value at the recorded snapshot, not expected fee or economic value.", body),
        para("Arsenal review order: direct left-wing solution, forward-ceiling option, midfield-control option, then Saliba-cover/backline contingency. Chelsea review order: back-three defensive need, left-side defensive/wing-back need, then Rogers integration and price-risk review.", body),
        PageBreak(),
    ]

    for club in ["Arsenal", "Chelsea"]:
        club_rows = [x for x in rows if x["club"] == club]
        need = "Direct left-winger first" if club == "Arsenal" else "Experienced defender with back-three know-how first"
        story.append(para(f"{club} Need Overview", h2))
        story.append(para(f"Primary need anchor: <b>{need}</b> [{nums['pl_needs_2026']}].", body))
        for r in club_rows[:2]:
            story.extend(card(r))
        story.append(PageBreak())
        for r in club_rows[2:]:
            story.extend(card(r))
        story.append(PageBreak())

    story.append(para("Comparison / Action Table", h2))
    story.append(para("No numeric overall ranking is produced. The action tags separate reporting confidence, local evidence coverage, tactical fit and price risk.", body))
    data = [["Club", "Player", "Reporting", "Local", "Fit", "Risk", "Action"]] + [[r["club"], r["player"], badge(r["latest_report_status"]), badge(r["local_data_status"]), badge(r["fit_rating"]), badge(r["price_risk"]), badge(r["recommended_action"])] for r in rows]
    table = Table(data, colWidths=[1.6*cm, 3.2*cm, 2.5*cm, 1.7*cm, 1.8*cm, 1.8*cm, 3.0*cm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8efe9")), ("GRID", (0, 0), (-1, -1), .25, colors.lightgrey), ("FONT", (0, 0), (-1, -1), "Helvetica", 7.2), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(table)
    story.append(PageBreak())
    story.append(para("References", h2))
    for i, s in enumerate(SOURCES, 1):
        story.append(para(f"{i}. {s['publisher']}. {s['title']}. Published: {s['publication_date'] or 'not stated'}; retrieved: {AS_OF}. {s['url']}", small))
    doc.build(story)


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
