from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "club-fit"
AS_OF = date(2026, 7, 20)


ALLOWED_ACTIONS = {
    "ADVANCE_SCOUTING", "MONITOR_PRICE", "TACTICAL_REVIEW_ONLY", "ABSTAIN_DATA_GAP", "LOW_PRIORITY",
}


SOURCES = [
    {
        "source_id": "pl_needs_2026",
        "publisher": "Premier League",
        "title": "Summer 2026 transfer window: What do each Premier League club need?",
        "publication_date": "2026-07-09",
        "retrieval_date": str(AS_OF),
        "url": "https://www.premierleague.com/en/news/4674463/summer-2026-transfer-window-what-do-each-premier-league-club-needx/",
        "claim_supported": "Arsenal need anchor is direct left-winger; Chelsea need anchor is defender with back-three know-how.",
        "source_tier": "1",
    },
    {
        "source_id": "chelsea_official_transfers_2026",
        "publisher": "Chelsea FC",
        "title": "Summer transfers 2026: All the Chelsea ins, outs and new contracts so far",
        "publication_date": "",
        "retrieval_date": str(AS_OF),
        "url": "https://www.chelseafc.com/en/news/article/summer-transfers-2026-all-the-chelsea-ins-outs-and-new-contracts-so-far",
        "claim_supported": "Chelsea official summer transfer tracker lists completed ins and outs; it does not confirm the reviewed rumour players unless named there.",
        "source_tier": "1",
    },
    {
        "source_id": "tm_arsenal_rumour_attempt",
        "publisher": "Transfermarkt",
        "title": "Arsenal FC - Club transfer rumours",
        "publication_date": "",
        "retrieval_date": str(AS_OF),
        "url": "https://www.transfermarkt.co.uk/arsenal-fc/geruechte/verein/11",
        "claim_supported": "Unavailable in this environment: page returned JavaScript/anti-bot verification. No Rumour Mill player status recorded.",
        "source_tier": "3",
    },
    {
        "source_id": "tm_chelsea_rumour_attempt",
        "publisher": "Transfermarkt",
        "title": "Chelsea FC - Club transfer rumours",
        "publication_date": "",
        "retrieval_date": str(AS_OF),
        "url": "https://www.transfermarkt.com/fc-chelsea/geruechte/verein/631",
        "claim_supported": "Unavailable in this environment: page returned JavaScript/anti-bot verification. No Rumour Mill player status recorded.",
        "source_tier": "3",
    },
    {
        "source_id": "sky_tzolis_arsenal",
        "publisher": "Sky Sports",
        "title": "Christos Tzolis: Arsenal agree fee with Club Brugge to sign Greek winger as replacement for Leandro Trossard",
        "publication_date": "2026-07-17",
        "retrieval_date": str(AS_OF),
        "url": "https://www.skysports.com/transfer/news/12691/13564048/christos-tzolis-arsenal-agree-fee-with-club-brugge-to-sign-greek-winger-as-replacement-for-leandro-trossard",
        "claim_supported": "Arsenal agreed a deal for Christos Tzolis as a left-wing/Trossard replacement.",
        "source_tier": "2",
    },
    {
        "source_id": "guardian_tzolis_arsenal",
        "publisher": "The Guardian",
        "title": "Arsenal close in on £34m deal for Club Brugge forward Christos Tzolis",
        "publication_date": "2026-07-16",
        "retrieval_date": str(AS_OF),
        "url": "https://www.theguardian.com/football/2026/jul/16/arsenal-34m-deal-club-brugge-forward-christos-tzolis-premier-league",
        "claim_supported": "Arsenal close to Tzolis and interested in Alvarez and Barcola.",
        "source_tier": "2",
    },
    {
        "source_id": "transfermarkt_alvarez_arsenal",
        "publisher": "Transfermarkt / The Independent",
        "title": "Arsenal set Julián Alvarez transfer deadline as Mikel Arteta's €416m spree laid bare",
        "publication_date": "2026-07-12",
        "retrieval_date": str(AS_OF),
        "url": "https://www.transfermarkt.com/arsenal-set-julian-alvarez-transfer-deadline-as-mikel-artetas-euro-416m-spree-laid-bare/view/news/482823",
        "claim_supported": "Arsenal interest in Julián Alvarez; Barcelona deadline context reported.",
        "source_tier": "2",
    },
    {
        "source_id": "guardian_bruno_arsenal",
        "publisher": "The Guardian",
        "title": "Arsenal on alert after Bruno Guimarães tells Newcastle he wants to leave",
        "publication_date": "2026-07-08",
        "retrieval_date": str(AS_OF),
        "url": "https://www.theguardian.com/football/2026/jul/08/arsenal-on-alert-after-bruno-guimaraes-tells-newcastle-he-wants-to-leave",
        "claim_supported": "Bruno Guimarães wants Arsenal move; Arsenal preparing interest.",
        "source_tier": "2",
    },
    {
        "source_id": "sky_bruno_arsenal",
        "publisher": "Sky Sports",
        "title": "Bruno Guimaraes transfer news: Newcastle captain tells club he wants to join Arsenal",
        "publication_date": "2026-07-09",
        "retrieval_date": str(AS_OF),
        "url": "https://www.skysports.com/transfer/news/11095/13561780/bruno-guimaraes-transfer-news-newcastle-captain-tells-club-he-wants-to-join-arsenal-after-world-cup-exit-with-brazil",
        "claim_supported": "Sky reports Bruno Guimarães wants to join Arsenal, with no club-to-club contact.",
        "source_tier": "2",
    },
    {
        "source_id": "sun_stones_arsenal",
        "publisher": "The Sun",
        "title": "Arsenal transfer news LIVE: Chelsea hijack Morgan Rogers deal, John Stones targeted, Julian Alvarez boost",
        "publication_date": "2026-07-20",
        "retrieval_date": str(AS_OF),
        "url": "https://www.thesun.co.uk/sport/39415117/arsenal-transfer-news-live-morgan-rogers-stones-alvarez-updates/",
        "claim_supported": "Arsenal reported interest in John Stones and Julian Alvarez.",
        "source_tier": "4",
    },
    {
        "source_id": "guardian_rogers_chelsea",
        "publisher": "The Guardian",
        "title": "Chelsea poised to sign Morgan Rogers from Aston Villa in record-breaking £117m deal",
        "publication_date": "2026-07-18",
        "retrieval_date": str(AS_OF),
        "url": "https://www.theguardian.com/football/2026/jul/18/chelsea-morgan-rogers-aston-villa-117m",
        "claim_supported": "Chelsea poised to sign Morgan Rogers; Arsenal had targeted him.",
        "source_tier": "2",
    },
    {
        "source_id": "talksport_rogers_chelsea",
        "publisher": "talkSPORT",
        "title": "What £117m Morgan Rogers transfer means for Cole Palmer and Enzo Fernandez at Chelsea",
        "publication_date": "2026-07-20",
        "retrieval_date": str(AS_OF),
        "url": "https://talksport.com/football/4442898/morgan-rogers-transfer-cole-palmer-enzo-fernandez-chelsea/",
        "claim_supported": "Chelsea agreed Morgan Rogers deal; tactical integration questions remain.",
        "source_tier": "2",
    },
    {
        "source_id": "talksport_lacroix_chelsea",
        "publisher": "talkSPORT",
        "title": "Chelsea hold talks with Premier League rivals over signing £55m-rated World Cup star",
        "publication_date": "2026-07-20",
        "retrieval_date": str(AS_OF),
        "url": "https://talksport.com/football/4441021/chelsea-talks-crystal-palace-maxence-lacroix-transfer-news/",
        "claim_supported": "Chelsea held formal talks with Crystal Palace over Maxence Lacroix.",
        "source_tier": "2",
    },
    {
        "source_id": "as_carreras_chelsea",
        "publisher": "AS",
        "title": "El Chelsea se fija... ¡en Carreras!",
        "publication_date": "2026-06-16",
        "retrieval_date": str(AS_OF),
        "url": "https://as.com/futbol/primera/el-chelsea-se-fija-en-carreras-f202606-n/",
        "claim_supported": "Chelsea value Álvaro Carreras as an option to cover Marc Cucurella departure.",
        "source_tier": "2",
    },
    {
        "source_id": "teamtalk_cambiaso_chelsea",
        "publisher": "TEAMtalk",
        "title": "Chelsea swap deal ON for top Juventus star as talks held over mutually beneficial exchange",
        "publication_date": "2026-06-19",
        "retrieval_date": str(AS_OF),
        "url": "https://www.teamtalk.com/chelsea/chelsea-hold-andrea-cambiaso-transfer-talks-swap-deal-nicolas-jackson",
        "claim_supported": "Chelsea held talks with Juventus over Andrea Cambiaso as a Cucurella replacement option.",
        "source_tier": "4",
    },
    {
        "source_id": "bundesliga_tapsoba_extension",
        "publisher": "Bundesliga",
        "title": "Edmond Tapsoba signs Bayer Leverkusen contract extension",
        "publication_date": "2026-04-29",
        "retrieval_date": str(AS_OF),
        "url": "https://www.bundesliga.com/en/bundesliga/news/edmond-tapsoba-bayer-leverkusen-contract-extension-37130",
        "claim_supported": "Edmond Tapsoba extended with Bayer Leverkusen until 2031; no current Chelsea link corroborated.",
        "source_tier": "1",
    },
]


CANDIDATES = [
    {
        "club": "Arsenal", "player": "Christos Tzolis", "target_role": "Direct left-wing solution",
        "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH",
        "source_ids": "pl_needs_2026;sky_tzolis_arsenal;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "MEDIUM", "recommended_action": "ADVANCE_SCOUTING",
        "data_warning": "Local evidence is identity and Transfermarkt market-consensus only; no validated Arsenal-specific sporting prediction.",
    },
    {
        "club": "Arsenal", "player": "Julián Alvarez", "target_role": "Forward-ceiling option",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM",
        "source_ids": "pl_needs_2026;transfermarkt_alvarez_arsenal;sun_stones_arsenal;tm_arsenal_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE",
        "data_warning": "Strong role fit but local evidence cannot price buyer-specific contribution; market-consensus value is not expected fee.",
    },
    {
        "club": "Arsenal", "player": "Bradley Barcola", "target_role": "Direct left-wing solution",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM",
        "source_ids": "pl_needs_2026;guardian_tzolis_arsenal;tm_arsenal_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE",
        "data_warning": "Included from current reporting as an interest option; no local validated scoring edge.",
    },
    {
        "club": "Arsenal", "player": "John Stones", "target_role": "Saliba-cover/backline contingency",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "LOW",
        "source_ids": "pl_needs_2026;sun_stones_arsenal;tm_arsenal_rumour_attempt",
        "fit_rating": "MEDIUM", "price_risk": "LOW", "recommended_action": "TACTICAL_REVIEW_ONLY",
        "data_warning": "Defender review abstains from attacking/shot-value metrics; live link comes from lower-confidence reporting.",
    },
    {
        "club": "Arsenal", "player": "Bruno Guimarães", "target_role": "Midfield-control option",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH",
        "source_ids": "pl_needs_2026;guardian_bruno_arsenal;sky_bruno_arsenal;tm_arsenal_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE",
        "data_warning": "Control profile is editorial/tactical; no buyer-specific value or validated ranking is produced.",
    },
    {
        "club": "Chelsea", "player": "Morgan Rogers", "target_role": "Rogers integration and price-risk review",
        "latest_report_status": "ADVANCED_REPORT", "reporting_confidence": "HIGH",
        "source_ids": "chelsea_official_transfers_2026;guardian_rogers_chelsea;talksport_rogers_chelsea;tm_chelsea_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "TACTICAL_REVIEW_ONLY",
        "data_warning": "Strong reporting but this is integration review, not discovery; Chelsea official tracker did not confirm Rogers as completed in the retrieved page.",
    },
    {
        "club": "Chelsea", "player": "Maxence Lacroix", "target_role": "Back-three defensive need",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "HIGH",
        "source_ids": "pl_needs_2026;talksport_lacroix_chelsea;tm_chelsea_rumour_attempt",
        "fit_rating": "HIGH", "price_risk": "HIGH", "recommended_action": "ADVANCE_SCOUTING",
        "data_warning": "Centre-back quality is not assessed by attacking metrics; local status is identity and market-consensus only.",
    },
    {
        "club": "Chelsea", "player": "Andrea Cambiaso", "target_role": "Left-side defensive/wing-back need",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "LOW",
        "source_ids": "pl_needs_2026;teamtalk_cambiaso_chelsea;tm_chelsea_rumour_attempt",
        "fit_rating": "MEDIUM", "price_risk": "MEDIUM", "recommended_action": "TACTICAL_REVIEW_ONLY",
        "data_warning": "Chelsea link is lower-confidence; no validated local wing-back fit model.",
    },
    {
        "club": "Chelsea", "player": "Álvaro Carreras", "target_role": "Left-side defensive/wing-back need",
        "latest_report_status": "REPORTED_INTEREST", "reporting_confidence": "MEDIUM",
        "source_ids": "pl_needs_2026;as_carreras_chelsea;tm_chelsea_rumour_attempt",
        "fit_rating": "MEDIUM", "price_risk": "HIGH", "recommended_action": "MONITOR_PRICE",
        "data_warning": "Current-club and price context make availability uncertain; no validated local wing-back fit model.",
    },
    {
        "club": "Chelsea", "player": "Edmond Tapsoba", "target_role": "Back-three defensive need",
        "latest_report_status": "NO_CURRENT_CORROBORATION", "reporting_confidence": "UNVERIFIED",
        "source_ids": "pl_needs_2026;bundesliga_tapsoba_extension;tm_chelsea_rumour_attempt",
        "fit_rating": "NOT_ASSESSED", "price_risk": "HIGH", "recommended_action": "LOW_PRIORITY",
        "data_warning": "No current Chelsea reporting corroborated; Leverkusen extension through 2031 materially weakens availability.",
    },
]


def norm_name(s: str) -> str:
    return (s.lower().replace("á", "a").replace("ã", "a").replace("é", "e")
            .replace("í", "i").replace("ú", "u").replace("ü", "u").replace("ø", "o"))


def load_tm() -> tuple[pd.DataFrame, pd.DataFrame]:
    players = pd.read_csv(REPO / "data" / "transfermarkt" / "players.csv.gz")
    vals = pd.read_csv(REPO / "data" / "transfermarkt" / "player_valuations.csv.gz")
    vals["date"] = pd.to_datetime(vals["date"], errors="coerce")
    latest_vals = vals.sort_values("date").groupby("player_id", as_index=False).tail(1)
    return players, latest_vals


def player_lookup(players: pd.DataFrame, latest_vals: pd.DataFrame, name: str) -> dict:
    s = players["name"].fillna("").map(norm_name)
    match = players[s.eq(norm_name(name))]
    if len(match) != 1:
        return {
            "tm_player_id": "",
            "tm_match_status": "UNMATCHED" if len(match) == 0 else "AMBIGUOUS",
            "date_of_birth": "",
            "age_as_of_date": "",
            "current_club": "",
            "position": "",
            "transfermarkt_market_value_eur": "",
            "market_value_snapshot_date": "",
        }
    row = match.iloc[0]
    dob = pd.to_datetime(row.date_of_birth, errors="coerce")
    age = ""
    if pd.notna(dob):
        age = round((pd.Timestamp(AS_OF) - dob).days / 365.25, 1)
    val = latest_vals[latest_vals.player_id.eq(row.player_id)]
    mv = row.market_value_in_eur
    snap = ""
    if len(val):
        snap = val.iloc[0].date.date().isoformat()
        mv = int(val.iloc[0].market_value_in_eur)
    return {
        "tm_player_id": int(row.player_id),
        "tm_match_status": "MATCHED",
        "date_of_birth": "" if pd.isna(row.date_of_birth) else str(row.date_of_birth)[:10],
        "age_as_of_date": age,
        "current_club": row.current_club_name,
        "position": row.sub_position if pd.notna(row.sub_position) else row.position,
        "transfermarkt_market_value_eur": int(mv) if pd.notna(mv) else "",
        "market_value_snapshot_date": snap,
    }


def source_urls(source_ids: str) -> str:
    idx = {s["source_id"]: s for s in SOURCES}
    return " | ".join(idx[sid]["url"] for sid in source_ids.split(";"))


def build_rows() -> list[dict]:
    players, latest_vals = load_tm()
    rows = []
    for c in CANDIDATES:
        local = player_lookup(players, latest_vals, c["player"])
        row = {
            "club": c["club"],
            "player": c["player"],
            **local,
            "target_role": c["target_role"],
            "as_of_date": str(AS_OF),
            "transfermarkt_rumour_status": "UNAVAILABLE_ANTI_BOT_NOT_BYPASSED",
            "latest_report_status": c["latest_report_status"],
            "reporting_confidence": c["reporting_confidence"],
            "source_urls": source_urls(c["source_ids"]),
            "local_data_status": "PARTIAL" if local["tm_match_status"] == "MATCHED" else "ABSTAIN",
            "local_data_vintage": "Transfermarkt local players/valuations files loaded 2026-07-20",
            "local_metrics_used": "identity; current club; Transfermarkt market-consensus value at recorded snapshot",
            "fit_rating": c["fit_rating"],
            "price_risk": c["price_risk"],
            "data_warning": c["data_warning"],
            "recommended_action": c["recommended_action"],
        }
        if c["player"] in {"John Stones", "Maxence Lacroix", "Edmond Tapsoba"}:
            row["local_data_status"] = "PARTIAL"
            row["local_metrics_used"] = "identity; current club; Transfermarkt market-consensus value at recorded snapshot"
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "club", "player", "tm_player_id", "tm_match_status", "date_of_birth", "age_as_of_date",
        "current_club", "position", "target_role", "as_of_date", "transfermarkt_rumour_status",
        "transfermarkt_market_value_eur", "market_value_snapshot_date", "latest_report_status",
        "reporting_confidence", "source_urls", "local_data_status", "local_data_vintage",
        "local_metrics_used", "fit_rating", "price_risk", "data_warning", "recommended_action",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_sources(path: Path) -> None:
    fields = ["source_id", "publisher", "title", "publication_date", "retrieval_date",
              "url", "claim_supported", "source_tier"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(SOURCES)


def write_markdown(path: Path, rows: list[dict]) -> None:
    def label(value: str) -> str:
        return value.replace("_", " ").title()

    sections = []
    for club in ["Arsenal", "Chelsea"]:
        club_rows = [r for r in rows if r["club"] == club]
        need = "direct left-winger first" if club == "Arsenal" else "experienced defender with back-three know-how first"
        sections.append(f"## {club} Need Overview\n\nPrimary need anchor: **{need}**. This is from the Premier League squad-needs analysis, not a model output.\n")
        for r in club_rows:
            mv = f"EUR {int(r['transfermarkt_market_value_eur']):,}" if r["transfermarkt_market_value_eur"] != "" else "unavailable"
            sections.append(f"""### {r['player']}

**Target role:** {r['target_role']}  
**Reporting status:** `{r['latest_report_status']}` / `{r['reporting_confidence']}`  
**Local data status:** `{r['local_data_status']}`  
**Fit rating:** `{r['fit_rating']}`  
**Action:** `{r['recommended_action']}`

Why included: fixed candidate set for the internal Chelsea + Arsenal review, cross-checked against the source register where current corroboration exists.

Local evidence genuinely available: {r['local_metrics_used']}. Date of birth `{r['date_of_birth']}`, age `{r['age_as_of_date']}` as of `{r['as_of_date']}`, current club `{r['current_club']}`, position `{r['position']}`.

Market-consensus value: {mv} at recorded snapshot `{r['market_value_snapshot_date']}`. This is **not** fair value, not expected fee, not surplus and not buyer-specific economic value.

Main tactical concern: role fit is editorial and must be checked by a human scout/video analyst.

Data caveat: {r['data_warning']}
""")
    table = "\n".join(
        f"| {r['club']} | {r['player']} | {label(r['latest_report_status'])} | {label(r['local_data_status'])} | {label(r['fit_rating'])} | {label(r['recommended_action'])} |"
        for r in rows
    )
    md = f"""# Chelsea + Arsenal 10-Player Club-Fit Review

As-of / retrieval date: **{AS_OF}**

## Executive Summary

This is an internal, human-in-the-loop decision-support review. It is **not** a validated sporting prediction, not a buyer-specific NPV model, not a surplus ranking, and not a numeric overall ranking.

The fixed review set contains exactly five Arsenal players and five Chelsea players. Transfermarkt Rumour Mill pages were checked, but both returned JavaScript/anti-bot verification in this environment; the report records that field as unavailable and does not reconstruct Rumour Mill status from snippets.

## Methodology And Limitations

The report combines official/competition need anchors, established reporting, and local Transfermarkt identity/value fields. The local data layer is mostly `PARTIAL`: identity, current club, date of birth, position and Transfermarkt market-consensus value at the recorded snapshot. No local metric is treated as sporting quality, expected fee or economic value.

Market value is labelled as **Transfermarkt market-consensus value at the recorded snapshot**. It is not fair value, not expected transfer fee and not buyer-specific economic value. Missing local performance evidence remains blank and does not become zero.

{''.join(sections)}

## Comparison / Action Table

| Club | Player | Reporting | Local data | Fit | Action |
|---|---|---|---|---|---|
{table}

## Source Notes

All current factual claims map to `reports/club-fit/source-register.csv`. Transfermarkt Rumour Mill direct status is unavailable because the pages required JavaScript/anti-bot verification; no bypass was attempted.
"""
    path.write_text(md)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    write_csv(OUT / "chelsea-arsenal-player-review.csv", rows)
    write_sources(OUT / "source-register.csv")
    write_markdown(OUT / "chelsea-arsenal-player-review.md", rows)
    print(OUT / "chelsea-arsenal-player-review.csv")
    print(OUT / "source-register.csv")
    print(OUT / "chelsea-arsenal-player-review.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
