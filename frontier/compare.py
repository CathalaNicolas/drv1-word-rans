"""Shared gates for M2 scorecard."""
from __future__ import annotations

WAYS = (1, 256, 1024, 3125)
K1_THIN_H0_MAX = 1.02
K2_DENSE_H0_MAX_N3125 = 1.05


def main() -> None:
    from frontier.m2_derived.measure import format_table, measure

    print("=== M2 / DRV1 (compact64 + keys=N control) ===")
    rows = measure()
    src = [r for r in rows if r["corpus"] == "source-200k"]
    print(format_table(src))
    c64 = [r for r in src if r["label"] == "compact64"]
    cliff = next(r for r in src if r["label"] == "keys=N" and r["N"] == 3125)
    r3125 = next(r for r in c64 if r["N"] == 3125)
    print(
        f"compact64 K1={all(r['K1'] for r in c64)}  "
        f"K2@3125={r3125['K2']} tot/H0={r3125['tot/H0']:.4f} meta={r3125['meta']}"
    )
    print(
        f"keys=N control tot/H0={cliff['tot/H0']:.4f} meta={cliff['meta']} (K2 fail)"
    )


if __name__ == "__main__":
    main()
