"""Locked final-test protection (owner decision 3, task §12).

The locked final period is `season >= LOCKED_SEASON_MIN`, taken from
`docs/modelling-contract.md`'s `design_A_recommended` fold
(`locked_final_test: season >= 2023`) — the one document in this repo that
formally proposes a fold design, as opposed to `validate/data_audit.py`'s
`temporal_fold_counts` which is a descriptive funnel table, not an adopted
contract. `season == 2022` is a deliberate one-season gap/buffer between
`calibration` and the locked period; it is neither dev nor locked and
`dev_only()` drops it along with the locked rows.

Every V2 development loader must route through `dev_only()` before any
model sees the data. `assert_no_locked()` is a defense-in-depth check for
code paths that build their own filters.

    python3 -m validate.locked_guard    # offline self-check
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
LOCKED_SEASON_MIN = 2023


class LockedDataAccessError(RuntimeError):
    pass


def dev_only(df: pd.DataFrame, season_col: str = "season") -> pd.DataFrame:
    """Drop the locked period (and the season==2022 buffer) before any
    development code sees the frame. Never call locked rows a "zero" or
    impute over them — they are excluded, not evaluated."""
    return df[df[season_col] < LOCKED_SEASON_MIN - 1].copy()


def assert_no_locked(df: pd.DataFrame, season_col: str = "season") -> None:
    if len(df) == 0:
        return
    bad = df[df[season_col] >= LOCKED_SEASON_MIN]
    if len(bad):
        raise LockedDataAccessError(
            f"{len(bad)} rows with {season_col} >= {LOCKED_SEASON_MIN} reached "
            "development code. This must never happen — route through dev_only()."
        )


def locked_audit_record(all_df: pd.DataFrame, season_col: str = "season") -> dict:
    """Row counts and a hash of the locked rows' KEYS only (never outcomes/labels),
    proving the locked period was identified and excluded without exposing what
    is in it. Safe to write to a tracked report."""
    locked = all_df[all_df[season_col] >= LOCKED_SEASON_MIN]
    dev = dev_only(all_df, season_col)
    buffer_rows = len(all_df) - len(locked) - len(dev)
    key_col = "transfer_uid" if "transfer_uid" in all_df.columns else season_col
    key_material = "|".join(sorted(locked[key_col].astype(str))) if len(locked) else ""
    return {
        "locked_season_min": LOCKED_SEASON_MIN,
        "total_rows": int(len(all_df)),
        "dev_rows": int(len(dev)),
        "buffer_rows_excluded_season_2022": int(buffer_rows),
        "locked_rows_excluded": int(len(locked)),
        "locked_rows_key_hash_sha256": hashlib.sha256(key_material.encode()).hexdigest() if key_material else None,
        "note": "Hash covers row KEYS only, not any outcome/label/prediction. No locked-row metric was computed.",
    }


def write_locked_audit(all_df: pd.DataFrame, out_path: Path, season_col: str = "season") -> Path:
    rec = locked_audit_record(all_df, season_col)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return out_path


def _check():
    df = pd.DataFrame({"season": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
                        "transfer_uid": [f"t{i}" for i in range(7)],
                        "secret_label": [1, 2, 3, 4, 5, 6, 7]})
    dev = dev_only(df)
    assert set(dev.season) == {2018, 2019, 2020, 2021}, dev.season.tolist()
    assert_no_locked(dev)  # must not raise

    try:
        assert_no_locked(df)
        raise AssertionError("assert_no_locked should have raised on the full frame")
    except LockedDataAccessError:
        pass

    rec = locked_audit_record(df)
    assert rec["locked_rows_excluded"] == 2 and rec["dev_rows"] == 4 and rec["buffer_rows_excluded_season_2022"] == 1
    assert set(rec.keys()) == {
        "locked_season_min", "total_rows", "dev_rows", "buffer_rows_excluded_season_2022",
        "locked_rows_excluded", "locked_rows_key_hash_sha256", "note",
    }, "audit record schema must only carry counts/hash, never an outcome/label column"
    assert len(rec["locked_rows_key_hash_sha256"]) == 64, "sha256 hex digest length"

    print("ok — dev_only excludes locked+buffer, assert_no_locked raises, audit hash carries no outcomes")


if __name__ == "__main__":
    _check()
