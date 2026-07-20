"""Club-name crosswalk between transfers_canonical (Transfermarkt-style full
legal names, e.g. "SV Werder Bremen") and fbref_perf (FBref's short display
names, e.g. "Werder Bremen"). No stable club ID exists anywhere in this
repo's tracked data (only player-level crosswalks — `crosswalk_players`,
`crosswalk_matches`) — task's "don't use names alone where stable IDs
exist" doesn't apply here; there is no stable ID to use instead. This is a
best-effort deterministic name match with an explicit confidence tier, not
silently trusted.

Method: normalize both names (lowercase, strip diacritics/punctuation, drop
a curated set of generic club-entity tokens and standalone founding-year
numbers), then match within the same (competition, season) group by:
1. exact normalized string match -> "exact"
2. one normalized name's token set is a subset of the other's -> "high"
3. difflib similarity ratio >= HIGH_RATIO on the normalized strings -> "high"
4. difflib similarity ratio >= LOW_RATIO -> "low"
5. otherwise -> unmatched (never guessed)

This must not be trusted as ground truth without the self-check's named
cases passing, and every downstream join carries the confidence tier as an
explicit column so a "low" match can be filtered out or displayed with a
visible caveat rather than silently treated as equal to an "exact" one.

    python3 -m ingest.club_crosswalk      # offline self-check
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

HIGH_RATIO = 0.90
LOW_RATIO = 0.72

# Generic club-entity tokens that appear in the fuller Transfermarkt-style
# names but are dropped from FBref's short names. Curated by inspection of
# the actual to_club_name / Squad value lists in this repo's warehouse, not
# a generic football-name library.
_STOPWORDS = {
    "fc", "cf", "sv", "vfb", "vfl", "sc", "ac", "afc", "ssc", "ss", "us",
    "ud", "cd", "rc", "ce", "ub", "og", "ogc", "asd", "as", "calcio", "club",
    "de", "deportivo", "association", "football",
    "1899", "1900", "1904", "1907", "1913", "1919", "05", "07", "04", "98",
    "96",
}

# "utd" is a meaningful, distinguishing token (Manchester UNITED vs
# Manchester City; Newcastle/West Ham/Leeds UNITED) -- it must NOT be
# stopword-stripped, but the two spellings need to collapse to one token
# or "Manchester United" vs "Manchester Utd" fails to match at all.
_SYNONYMS = {"utd": "united", "munchen": "munich", "internazionale": "inter"}

# Single tokens too common across multiple real clubs to trust as the SOLE
# basis for a subset match (e.g. "AC Milan" -> {milan} must not
# single-token-match "Inter" via some transitive path, and "as monaco"'s
# "as" must not by itself imply a match to anything containing it).
_AMBIGUOUS_SOLO_TOKENS = {"real", "city", "united", "athletic", "sporting",
                           "milan", "county", "town", "rovers", "as", "no"}

# A small curated alias table for well-known abbreviated forms that share no
# useful substring with the full name (pure token/ratio matching cannot find
# these -- e.g. "M'Gladbach" vs "Mönchengladbach" share almost no characters
# in the same order). Extend as new mismatches are found; never silently
# assumed to be complete.
CURATED_ALIASES = {
    "borussia monchengladbach": "M'Gladbach",
    "paris saint germain": "Paris S-G",
    "internazionale milano": "Inter",
    "manchester city": "Man City",
}

_FOUNDING_YEAR_RE = re.compile(r"^\d{1,4}$")


def normalize_club(name: str) -> str:
    if not isinstance(name, str) or not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    tokens = [_SYNONYMS.get(t, t) for t in n.split()
              if t not in _STOPWORDS and not _FOUNDING_YEAR_RE.match(t)]
    return " ".join(tokens)


def _match_one(tm_norm: str, fb_candidates: dict[str, str]) -> tuple[str | None, str]:
    """fb_candidates: normalized_fbref_name -> original_fbref_name."""
    if not tm_norm:
        return None, "unmatched"
    if tm_norm in CURATED_ALIASES and CURATED_ALIASES[tm_norm] in fb_candidates.values():
        return CURATED_ALIASES[tm_norm], "alias"
    if tm_norm in fb_candidates:
        return fb_candidates[tm_norm], "exact"
    tm_tokens = set(tm_norm.split())
    # exact token-set match (order-independent) beats fuzzy ratio and must
    # be unambiguous: if more than one fbref candidate has the identical
    # token set as tm, refuse rather than guess (this is what caught the
    # Manchester City / Manchester Utd near-miss during development).
    exact_token_matches = [fb_orig for fb_norm, fb_orig in fb_candidates.items()
                            if set(fb_norm.split()) == tm_tokens]
    if len(exact_token_matches) == 1:
        return exact_token_matches[0], "high"
    # proper-subset match: fbref's short name's tokens are entirely
    # contained in TM's fuller name (e.g. tm {borussia,dortmund} ⊃ fb
    # {dortmund}). Refuse if the fbref side is a single token AND that
    # token is on the ambiguous list (shared by multiple real clubs) --
    # e.g. fb {milan} alone must not subset-match every "X Milan" TM name.
    subset_matches = [
        fb_orig for fb_norm, fb_orig in fb_candidates.items()
        if (fb_tokens := set(fb_norm.split())) and fb_tokens < tm_tokens
        and not (len(fb_tokens) == 1 and fb_tokens <= _AMBIGUOUS_SOLO_TOKENS)
    ]
    if len(subset_matches) == 1:
        return subset_matches[0], "high"

    best_name, best_ratio = None, 0.0
    for fb_norm, fb_orig in fb_candidates.items():
        ratio = difflib.SequenceMatcher(None, tm_norm, fb_norm).ratio()
        if ratio > best_ratio:
            best_ratio, best_name = ratio, fb_orig
    if best_ratio >= HIGH_RATIO:
        return best_name, "high"
    if best_ratio >= LOW_RATIO:
        return best_name, "low"
    return None, "unmatched"


def build_crosswalk(tm_names: list[str], fbref_names: list[str]) -> pd.DataFrame:
    """Global (not season-scoped) crosswalk — callers that need
    (competition, season)-scoped matching should pre-filter fbref_names to
    the relevant Comp/season before calling, since the same short name can
    legitimately mean different clubs across eras in principle (rare, but
    the caller controls scope, this function does not assume it)."""
    fb_norm_map: dict[str, str] = {}
    for fb in fbref_names:
        fb_norm_map[normalize_club(fb)] = fb
    rows = []
    for tm in sorted(set(tm_names)):
        tm_norm = normalize_club(tm)
        match, confidence = _match_one(tm_norm, fb_norm_map)
        rows.append({"tm_club_name": tm, "fbref_squad": match, "confidence": confidence})
    return pd.DataFrame(rows)


def _check():
    fbref_names = [
        "Werder Bremen", "Real Madrid", "Manchester Utd", "M'Gladbach",
        "Paris S-G", "Monaco", "Dortmund", "Man City", "Bayern Munich",
        "Inter", "Milan", "Köln",
    ]
    named_cases = {
        "SV Werder Bremen": "Werder Bremen",
        "Real Madrid CF": "Real Madrid",
        "Manchester United": "Manchester Utd",
        "Borussia Mönchengladbach": "M'Gladbach",
        "Paris Saint-Germain": "Paris S-G",
        "AS Monaco": "Monaco",
        "Borussia Dortmund": "Dortmund",
        "Manchester City": "Man City",
        "FC Bayern München": "Bayern Munich",
        "Inter Milan": "Inter",
        "AC Milan": "Milan",
        "1.FC Köln": "Köln",
    }
    cw = build_crosswalk(list(named_cases.keys()), fbref_names)
    lookup = cw.set_index("tm_club_name").fbref_squad.to_dict()
    conf = cw.set_index("tm_club_name").confidence.to_dict()
    failures = []
    for tm, expected in named_cases.items():
        got = lookup.get(tm)
        if got != expected:
            failures.append((tm, expected, got, conf.get(tm)))
    assert not failures, f"club crosswalk failed named cases: {failures}"
    assert all(c in ("exact", "high", "alias") for c in conf.values()), \
        f"named cases should all resolve at exact/high/alias confidence: {conf}"

    # deliberately unrelated names must NOT match (false-positive guard)
    unrelated = build_crosswalk(["Totally Fictional FC 1999"], fbref_names)
    assert unrelated.iloc[0].confidence == "unmatched", \
        "a name with no real counterpart must not be force-matched"

    # AC Milan vs Inter Milan must resolve to DIFFERENT clubs, not collide
    # on the shared "Milan" token
    milan_cw = build_crosswalk(["AC Milan", "Inter Milan"], ["Milan", "Inter"])
    m = milan_cw.set_index("tm_club_name").fbref_squad.to_dict()
    assert m["AC Milan"] == "Milan" and m["Inter Milan"] == "Inter", m

    # REGRESSION: real false positives found by inspecting the full
    # production tm/fbref name lists (2026-07-13). These pairs are real,
    # DIFFERENT clubs that the ratio-matcher confused when both candidates
    # were present in the same pool. The invariant is not "never appears in
    # the low tier" (fuzzy matching will always have near-misses) -- it's
    # "never resolves at exact/high/alias", because
    # validate.v3_sporting_target's join policy discards anything below
    # high confidence. If any of these regress to high/exact/alias, a
    # future-outcome row would be silently attributed to the wrong club.
    confusable_pool = ["Athletic Club", "Real Madrid", "Burnley", "Bolton"]
    decoys = {
        "Atlético": "Athletic Club",      # Atlético Madrid != Athletic Bilbao/Club
        "Real Murcia": "Real Madrid",     # unrelated small club != Real Madrid
        "Barnsley FC": "Burnley",         # different English clubs
        "Luton": "Bolton",                # different English clubs
    }
    decoy_cw = build_crosswalk(list(decoys.keys()), confusable_pool)
    decoy_conf = decoy_cw.set_index("tm_club_name").confidence.to_dict()
    bad = {tm: c for tm, c in decoy_conf.items() if c in ("exact", "high", "alias")}
    assert not bad, f"known false-positive club pairs must not resolve at trusted confidence: {bad}"

    print(f"ok — club crosswalk resolves {len(named_cases)}/{len(named_cases)} named cases "
          f"at exact/high/alias confidence, rejects an unrelated name, disambiguates AC/Inter "
          f"Milan, and keeps 4 known confusable pairs (Atlético/Athletic, Real Murcia/Real "
          f"Madrid, Barnsley/Burnley, Luton/Bolton) out of the trusted tiers")


if __name__ == "__main__":
    _check()
