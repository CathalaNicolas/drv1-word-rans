"""Run M2 works cases. Entry: python run_all.py"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from common.cases import CaseResult, run_cases
from frontier.m2_derived import works as m2_derived_works

GROUPS = [
    ("m2_derived / works", m2_derived_works.cases()),
]


def _print_group(title: str, results: list[CaseResult]) -> bool:
    print(f"\n== {title} ==")
    ok = True
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        line = f"  [{mark}] {r.name}"
        if not r.ok:
            line += f" — {r.detail}"
            ok = False
        print(line)
        if r.why and not r.ok:
            print(f"         {r.why}")
    return ok


def main() -> int:
    all_ok = True
    totals = [0, 0]
    for title, cases in GROUPS:
        results = run_cases(cases)
        if not _print_group(title, results):
            all_ok = False
        totals[0] += sum(1 for r in results if r.ok)
        totals[1] += len(results)
    print(f"\n{totals[0]}/{totals[1]} cases passed")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
