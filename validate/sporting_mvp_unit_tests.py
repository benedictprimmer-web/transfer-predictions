"""Data-independent Sporting MVP unit tests for CI.

These tests exercise synthetic event-key collision and denominator fixtures.
They intentionally do not load the repository's private/full data artifacts.

Run:
    python3 -m validate.sporting_mvp_unit_tests
"""
from __future__ import annotations

from validate.sporting_mvp_integrity import run_adversarial_event_tests, run_denominator_tests


def main() -> int:
    run_adversarial_event_tests()
    run_denominator_tests()
    print("ok - sporting MVP synthetic event-key and denominator tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
