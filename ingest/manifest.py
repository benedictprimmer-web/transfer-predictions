"""Provenance ledger for the harvest harness — `data/manifest.json`.

One entry per fetched artifact: url, etag/last-modified (for conditional GET),
sha256, byte size, row count, fetched_at, and status. This is what makes a
refresh idempotent (skip unchanged) and every canonical row traceable to the
exact source bytes it came from.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "manifest.json"


def key(source: str, artifact: str) -> str:
    return f"{source}/{artifact}"


def load(path=MANIFEST) -> dict:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return {"schema_version": 1, "generated_at": None, "artifacts": {}}


def save(m: dict, path=MANIFEST) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, indent=2, default=str))
    os.replace(tmp, p)                      # atomic — a crash never leaves a half-written manifest


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_sha(m: dict) -> str:
    """One hash over the sorted (artifact -> sha256) map — stamps a canonical build."""
    items = sorted((k, v.get("sha256")) for k, v in m.get("artifacts", {}).items())
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()


def _check():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "m.json"
    m = load(p)
    m["artifacts"][key("s", "a")] = {"sha256": "abc", "rows": 10}
    save(m, p)
    assert load(p)["artifacts"]["s/a"]["sha256"] == "abc"
    assert manifest_sha(m) == manifest_sha(load(p))
    print("ok — manifest round-trips, sha stable")


if __name__ == "__main__":
    _check()
