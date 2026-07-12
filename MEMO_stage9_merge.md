# Stage 9 — Merge the two estates, backfill, ship the fee ranker

**Ask:** merge `~/Downloads/football-transfer-db` (Estate B, the finished-but-sandbox-blocked
DuckDB) with `~/Transfer Predictions/data` (Estate A, the live raw dumps); backfill exact dates
and market value; ship the fee ranker with the impact/NPV score demoted to a sanity check.

## What was built

| Artifact | Path | What it is |
|---|---|---|
| Merge pipeline | `ingest/merge.py` | Estate B enriched spine + Estate A fills → one canonical table |
| Canonical table | `data/merged/transfers_canonical.parquet` | 124,183 rows, 1992–2026, leakage-safe |
| Fee ranker (shipped) | `money/fees.py::ship` → `data/money/fee_ranker.csv` | 13,853 ranked deals, over/under-pay verdict |

Both have runnable self-checks: `python -m ingest.merge --check`, `python -m money.fees` (`_check`).

## Merge + backfill — before → after (every number from a query)

| Field | Estate B alone | Canonical | How |
|---|---|---|---|
| rows | 115,033 (≤2022) | **124,183** (≤2026) | +9,150 Estate A 2023–26 rows, enriched from clubs/players |
| dedup | already clean on guarded key | unchanged (idempotent) | ported Estate B's fee-conflict-guarded SQL — never merges 2 distinct fees |
| market value (any) | 40.0% | **57.3%** | point-in-time fill |
| market value point-in-time | — | **53.4%** | `merge_asof` valuations, **strictly before** the pre-window date (no leak) |
| exact `transfer_date` | 0% | **9.6%** | join Estate A transfers slice; rest keep a flagged window proxy |
| model-ready (fee+mv+age) | 16,731 | **16,233** | trainable fee rows preserved |

Provenance columns ride along: `date_source` (exact/proxy), `mv_source`, `mv_is_point_in_time`, `origin`.

## Fee ranker — shipped and gated

- **Gate PASSES both marquee deals:** Haaland → Man City **−18%** (underpay ✓), Antony → Man Utd **+144%** (overpay ✓).
- Trains on the **union** of canonical (breadth + point-in-time MV + real leagues) and `big_5_transfers.rds`
  (marquee + proper player-URL keys — Estate B left Antony's `player_id` null, so canonical alone lost him).
- **Spearman(fee, pred): 0.787 all / 0.790 plausible / 0.755 Big-5-core**; OOF log-R² 0.614, n=13,853.
  (Original Big-5-only model was ρ0.845 on n≈6.7k — the union roughly doubles coverage at a modest ρ cost.)
- **Data-quality guard:** 19 rows with fee ≥€10m at >15× market value (Malomo €50m→AC Prato etc. — decimal/data
  errors Estate B's `fee_suspect` missed at <€222m) are flagged `fee_vs_mv_implausible`, kept in the CSV, dropped
  from the ranking.
- **Impact/NPV is deliberately NOT in the board** — it stays in `money.price` as a wide-error sanity check
  (calibrated to the r≈0.08 Stage-4 channel, band by design). Fee residual is the headline; impact is the second opinion.

**Read the residual as "fee vs prior market consensus", not "vs true value."** Crowd-sourced MV lags breakouts,
so young breakout buys (Osimhen, Mbappé) top the overpay list because their *pre-window* consensus value was low —
the model is faithful, the framing needs the caveat. Headline lists therefore restrict to established value (fee & MV ≥ €10m).

## Honest gaps — still need external sourcing (say the word to spawn agents)

1. **Exact dates at scale.** Estate A's transfers slice is thin — 4,345 players, ~2.6k fees, no marquee, overlaps
   Estate B by 811 players → exact dates cover only 9.6%. Fuller dated transfers (or reconstruction from
   appearances/valuation club-changes) is unsolved here.
2. **Recent Big-5 fees.** `big_5_transfers.rds` stops 2022; the 2023–26 extension carries roster/MV but few fees.
   The ranker is thin post-2022.
3. **Point-in-time contracts.** Still empty. The only on-disk source (`players.csv` latest `contract_expiration_date`)
   is not point-in-time and would leak on historical deals. Needs raw per-season scraper JSON. Wages remain licensed-only.

## Reproduce

```bash
python -m ingest.merge          # build canonical + coverage report
python -m money.fees ship       # fit, gate, write data/money/fee_ranker.csv
```
