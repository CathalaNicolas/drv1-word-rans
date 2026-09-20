from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Case:
    name: str
    fn: Callable[[], None]
    """Raise AssertionError or any Exception to fail."""
    expect_failure: bool = False
    why: str = ""


@dataclass(frozen=True)
class CaseResult:
    name: str
    ok: bool
    expect_failure: bool
    detail: str
    why: str = ""


def run_cases(cases: list[Case]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        try:
            case.fn()
        except Exception as exc:
            failed = True
            detail = f"{type(exc).__name__}: {exc}"
        else:
            failed = False
            detail = "ok"
        if case.expect_failure:
            ok = failed
            if not failed:
                detail = "expected this case to break, but it succeeded"
        else:
            ok = not failed
        results.append(
            CaseResult(
                name=case.name,
                ok=ok,
                expect_failure=case.expect_failure,
                detail=detail,
                why=case.why,
            )
        )
    return results
