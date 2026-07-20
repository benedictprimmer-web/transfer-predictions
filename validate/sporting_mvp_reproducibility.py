"""Reproduce deterministic Sporting MVP artifacts twice and verify stability.

Run:
    python3 -m validate.sporting_mvp_reproducibility
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from validate.sporting_mvp_integrity import OUT, REPO, write_outputs
from validate.sporting_mvp_models import run_models
from validate.sporting_mvp_visuals import main as render_visuals


DETERMINISTIC_ARTIFACTS = [
    OUT / "dev-population-manifest.csv",
    OUT / "dev-population-summary.json",
    OUT / "data-fix-summary.csv",
    OUT / "join-funnel.csv",
    OUT / "join-audit.csv",
    OUT / "key-collisions.csv",
    OUT / "fold-manifest.csv",
    OUT / "fold-model-audit.csv",
    OUT / "model-comparison.csv",
    OUT / "design-ablation.csv",
    OUT / "subgroup-results.csv",
    OUT / "abstention-summary.csv",
    OUT / "run-manifest.json",
    OUT / "validated-output-contract.csv",
    OUT / "design-a-scouting-desk.html",
    OUT / "design-b-recruitment-lab.html",
]


def _hashes() -> dict[str, str]:
    return {
        str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in DETERMINISTIC_ARTIFACTS
    }


def _generate_all() -> None:
    write_outputs()
    run_models()
    render_visuals()


def main() -> int:
    _generate_all()
    first = _hashes()
    _generate_all()
    second = _hashes()
    assert first == second, "deterministic artifact hashes changed across identical reruns"

    paths = [str(path.relative_to(REPO)) for path in DETERMINISTIC_ARTIFACTS]
    diff = subprocess.run(["git", "diff", "--quiet", "--", *paths], cwd=REPO)
    assert diff.returncode == 0, "tracked deterministic artifacts are dirty after regeneration"
    print("ok - sporting MVP deterministic artifacts reproduce without diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
