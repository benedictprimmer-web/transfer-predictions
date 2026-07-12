"""The harvest harness — one command to refresh open-redistribution data, validate
it, rebuild the canonical table, and promote a versioned snapshot.

    python -m ingest.harvest              # refresh -> validate -> rebuild -> promote -> report
    python -m ingest.harvest --dry-run    # HEAD only: what WOULD refresh; no writes
    python -m ingest.harvest --only transfermarkt tm_raw
    python -m ingest.harvest --force      # ignore etag/hash, re-fetch all
    python -m ingest.harvest --no-promote # rebuild + validate, skip snapshot/live swap
    python -m ingest.harvest --check      # stdlib self-check, no network

Idempotent (conditional GET / hash-match / md5 skip; atomic writes), provenance-stamped
(data/manifest.json), and snapshot-versioned (data/merged/snapshots/<ts>_<sha>/) so a bad
gate never clobbers the live parquet. STDLIB ONLY. No TM/FBref scraping — CC0 feeds only.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ingest import manifest
from ingest.sources import REGISTRY, CANONICAL_REQUIRED, CANONICAL_NUMERIC
from ingest.tm_raw import _UA as UA


@dataclass
class FetchResult:
    status: str; etag: str | None; last_modified: str | None; sha256: str | None; bytes: int


@dataclass
class GateResult:
    gate: str; ok: bool; detail: str; blocking: bool = True
    def __str__(self):
        return f"  [{'PASS' if self.ok else 'FAIL'}] {self.gate}: {self.detail}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_rows(path: Path) -> int | None:
    """Row count of a .csv.gz (minus header). Only called on changed gated artifacts."""
    try:
        with gzip.open(path, "rt", errors="ignore") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return None


# ─────────────────────────── fetch ───────────────────────────

def conditional_get(url: str, dest: Path, prev: dict | None) -> FetchResult:
    """304 or matching sha256 -> 'unchanged', dest untouched. Else atomic write."""
    req = Request(url, headers={"User-Agent": UA})
    if prev:
        if prev.get("etag"):
            req.add_header("If-None-Match", prev["etag"])
        if prev.get("last_modified"):
            req.add_header("If-Modified-Since", prev["last_modified"])
    try:
        r = urlopen(req, timeout=180)
    except HTTPError as e:
        if e.code == 304:
            return FetchResult("unchanged", prev.get("etag"), prev.get("last_modified"),
                               prev.get("sha256"), prev.get("bytes", 0))
        raise
    body = r.read()
    digest = sha256(body).hexdigest()
    etag, lm = r.headers.get("ETag"), r.headers.get("Last-Modified")
    if prev and digest == prev.get("sha256"):
        return FetchResult("unchanged", etag or prev.get("etag"), lm, digest, len(body))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, dest)                    # atomic
    return FetchResult("updated" if prev else "new", etag, lm, digest, len(body))


def _selected(only):
    return [(k, s) for k, s in REGISTRY.items() if only is None or k in only]


def refresh(only=None, m_prev=None, force=False) -> dict:
    m_prev = m_prev or manifest.load()
    prev = m_prev.get("artifacts", {})
    m = {"schema_version": 1, "generated_at": None, "artifacts": dict(prev)}
    for skey, src in _selected(only):
        if src.kind == "http":
            for a in src.artifacts:
                k = manifest.key(skey, a)
                p = None if force else prev.get(k)
                fr = conditional_get(src.url(a), src.path(a), p)
                rows = (_count_rows(src.path(a)) if (src.min_rows and fr.status != "unchanged")
                        else (p or {}).get("rows"))
                m["artifacts"][k] = {
                    "source": skey, "artifact": a, "url": src.url(a),
                    "cache_path": str(src.path(a)), "etag": fr.etag,
                    "last_modified": fr.last_modified, "sha256": fr.sha256,
                    "bytes": fr.bytes, "rows": rows, "fetched_at": _now(), "status": fr.status}
                print(f"  {fr.status:>9}  {k}  ({fr.bytes:,}b)")
        elif src.kind == "dvc":
            _refresh_dvc(skey, m, prev, force)
    return m


def _refresh_dvc(skey, m, prev, force):
    """dcaribou RAW via DVC: skip unless the GitHub .dir md5 changed; else re-harvest."""
    import ingest.tm_raw as raw
    changed = False
    for ds in ("transfermarkt-api", "transfermarkt-scraper"):
        md5 = raw._dir_md5(ds)
        k = manifest.key(skey, ds)
        was = (prev.get(k) or {}).get("etag")
        status = "unchanged" if (not force and was == md5) else ("updated" if was else "new")
        changed = changed or status != "unchanged"
        m["artifacts"][k] = {"source": skey, "artifact": ds, "etag": md5,
                             "status": status, "fetched_at": _now()}
        print(f"  {status:>9}  {k}  (dir {md5[:10]})")
    if changed or force:
        raw.harvest(seasons=tuple(range(2012, 2026)), force=force)


# ─────────────────────────── validate ───────────────────────────

def validate(m, m_prev, strict=False) -> list[GateResult]:
    out, prev = [], m_prev.get("artifacts", {})
    for k, e in m["artifacts"].items():
        src = REGISTRY[e["source"]]
        if src.min_rows and e.get("rows") is not None:
            rows = e["rows"]
            pr = (prev.get(k) or {}).get("rows")
            ok = rows >= src.min_rows and (pr is None or rows >= 0.90 * pr)
            out.append(GateResult(f"rows {k}", ok, f"{rows:,} (floor {src.min_rows:,}, prev {pr})"))
    return out


def validate_canonical(df) -> list[GateResult]:
    missing = CANONICAL_REQUIRED - set(df.columns)
    out = [GateResult("canonical schema", not missing,
                      "all required columns present" if not missing else f"MISSING {sorted(missing)}")]
    import pandas as pd
    bad = [c for c in CANONICAL_NUMERIC if c in df and not pd.api.types.is_numeric_dtype(df[c])]
    out.append(GateResult("canonical dtypes", not bad,
                          "numeric ok" if not bad else f"non-numeric {bad}"))
    return out


# ─────────────────────────── promote ───────────────────────────

def promote(df, m, keep=6) -> Path:
    from ingest.merge import OUT
    sha = manifest.manifest_sha(m)[:6]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    snap = OUT.parent / "snapshots" / f"{ts}_{sha}"
    snap.mkdir(parents=True, exist_ok=True)
    df.to_parquet(snap / OUT.name, index=False)
    manifest.save(m, snap / "manifest.json")
    df.to_parquet(OUT, index=False)          # live pointer
    snaps = sorted((OUT.parent / "snapshots").glob("*"))
    for old in snaps[:-keep]:
        shutil.rmtree(old, ignore_errors=True)
    return snap


# ─────────────────────────── orchestrate ───────────────────────────

def _dry_run(only):
    print("DRY RUN — would check:")
    m_prev = manifest.load().get("artifacts", {})
    for skey, src in _selected(only):
        if src.kind != "http":
            print(f"  {skey}: dvc (compares GitHub .dir md5)")
            continue
        for a in src.artifacts:
            k = manifest.key(skey, a)
            try:
                req = Request(src.url(a), method="HEAD", headers={"User-Agent": UA})
                r = urlopen(req, timeout=30)
                etag = r.headers.get("ETag")
                was = (m_prev.get(k) or {}).get("etag")
                print(f"  {'CHANGED' if etag != was else 'unchanged':>9}  {k}")
            except Exception as e:
                print(f"  {'ERR':>9}  {k}: {e}")
    return 0


def harvest(only=None, dry_run=False, strict=False, promote_=True, force=False) -> int:
    if dry_run:
        return _dry_run(only)
    m_prev = manifest.load()
    print("refresh:")
    m = refresh(only, m_prev, force)
    gates = validate(m, m_prev, strict)
    if any(not g.ok and g.blocking for g in gates):
        print("SOURCE GATES:"); [print(g) for g in gates]
        print("ABORT — bad source, canonical left untouched"); return 1
    from ingest.merge import build_canonical
    print("rebuild canonical:")
    df = build_canonical(write=False)
    cgates = validate_canonical(df)
    print("GATES:"); [print(g) for g in gates + cgates]
    if any(not g.ok and g.blocking for g in cgates):
        print("ABORT — canonical failed contract, not promoted"); return 1
    if promote_:
        snap = promote(df, m)
        m["generated_at"] = _now()
        manifest.save(m)
        print(f"promoted -> {snap}")
    else:
        print("--no-promote: canonical rebuilt but not written")
    return 0


def _check():
    """stdlib self-check, no network: conditional_get hash-skip, atomic write, shrink gate."""
    import tempfile
    d = Path(tempfile.mkdtemp())
    body = b"col\n1\n2\n3\n"
    src = d / "src.txt"; src.write_bytes(body)
    dest = d / "dest.txt"
    # (a) hash-match -> unchanged, no rewrite
    fr1 = conditional_get(src.as_uri(), dest, None)
    assert fr1.status == "new" and dest.read_bytes() == body
    fr2 = conditional_get(src.as_uri(), dest, {"sha256": fr1.sha256})
    assert fr2.status == "unchanged", fr2.status
    # (b) shrink gate blocks a 50%-shrunk gated table
    from ingest.sources import Source
    REGISTRY["_t"] = Source(key="_t", licence="x", cadence="weekly", feeds=(), min_rows=10)
    m = {"artifacts": {"_t/a": {"source": "_t", "artifact": "a", "rows": 40}}}
    prev = {"artifacts": {"_t/a": {"rows": 100}}}
    g = validate(m, prev)[0]
    assert not g.ok, "shrink guard should fail 40 vs prev 100"
    m2 = {"artifacts": {"_t/a": {"source": "_t", "artifact": "a", "rows": 95}}}
    assert validate(m2, prev)[0].ok, "95 vs 100 should pass"
    del REGISTRY["_t"]
    # (c) atomic write left no .tmp
    assert not list(d.glob("*.tmp"))
    print("ok — conditional-get hash-skip, atomic write, shrink gate all correct")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--check" in a:
        _check()
    else:
        only = a[a.index("--only") + 1:] if "--only" in a else None
        only = [x for x in only if not x.startswith("--")] if only else None
        sys.exit(harvest(only=only, dry_run="--dry-run" in a, strict="--strict" in a,
                         promote_="--no-promote" not in a, force="--force" in a))
