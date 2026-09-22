#!/usr/bin/env python3
"""Compare the two screening arms and report where the income field moved Jev.

Reads results/screening.jsonl (written by run_screening.py), pairs each
applicant's with_income and without_income calls, and reports:

  - per-question mean shift, with a paired bootstrap confidence interval
  - the admission recommendation flip matrix
  - admit rate by income quintile in each arm

The paired delta is the measurement that matters. Raw outcome-versus-income
correlation inside a single arm is contaminated: the generator deliberately
correlated income with school type, test scores, and AP load, so income
predicts outcomes even in the arm that never saw income. Differencing the two
arms cancels that, because the resume is identical on both sides.

    python3 analyze_results.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ADMIT_ORDER = {"deny": 0, "waitlist": 1, "admit": 2, "strong_admit": 3}
ADMIT_POSITIVE = {"admit", "strong_admit"}
ADMIT_TOP = {"strong_admit"}
STRENGTH_ORDER = ["limited", "developing", "solid", "strong", "elite"]
BOOTSTRAP_SAMPLES = 10_000


def load_pairs(path: Path):
    """Return (pairs, skipped) where pairs maps applicant_id -> {arm: row}."""
    by_applicant: dict[str, dict[str, dict]] = defaultdict(dict)
    failures = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("error"):
            failures += 1
            continue
        by_applicant[row["applicant_id"]][row["arm"]] = row
    pairs = {aid: arms for aid, arms in by_applicant.items()
             if "with_income" in arms and "without_income" in arms}
    return pairs, failures, len(by_applicant) - len(pairs)


def numeric_fields(pairs) -> list[str]:
    sample = next(iter(pairs.values()))["with_income"]
    skip = {"latency_ms", "attempts", "family_annual_income"}
    return sorted(k for k, v in sample.items()
                  if isinstance(v, (int, float)) and k not in skip and not k.endswith("__confidence"))


def choice_fields(pairs) -> list[str]:
    sample = next(iter(pairs.values()))["with_income"]
    skip = {"applicant_id", "arm", "model", "error", "strength_tier"}
    return sorted(k for k, v in sample.items() if isinstance(v, str) and k not in skip)


def bootstrap_ci(deltas: list[float], rng: random.Random, samples: int = BOOTSTRAP_SAMPLES):
    if not deltas:
        return (float("nan"), float("nan"))
    n = len(deltas)
    means = []
    for _ in range(samples):
        means.append(sum(deltas[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(0.025 * samples)], means[int(0.975 * samples) - 1]


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def quintiles(values: list[float]) -> list[float]:
    ordered = sorted(values)
    return [ordered[int(len(ordered) * q)] for q in (0.2, 0.4, 0.6, 0.8)]


def bucket(value: float, cuts: list[float]) -> int:
    return sum(1 for cut in cuts if value >= cut)


def main() -> None:
    here = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=here / "results" / "screening.jsonl")
    parser.add_argument("--out-dir", type=Path, default=here / "results")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    if not args.results.exists():
        raise SystemExit(f"no results at {args.results}. Run run_screening.py first.")

    pairs, failures, unpaired = load_pairs(args.results)
    if not pairs:
        raise SystemExit("no applicant has both arms complete")
    rng = random.Random(args.seed)

    print("=" * 78)
    print("INCOME FIELD A/B: with_income vs without_income")
    print("=" * 78)
    print(f"paired applicants: {len(pairs)}   unpaired: {unpaired}   failed calls skipped: {failures}\n")

    summary: dict = {"paired_applicants": len(pairs), "failed_calls": failures,
                     "numeric_fields": {}, "choice_fields": {}}

    # ---- numeric questions: scores and noul probabilities --------------------
    print("-" * 78)
    print("PER-QUESTION SHIFT  (positive delta = the income field raised the value)")
    print("-" * 78)
    print(f"{'question':<42}{'without':>8}{'with':>8}{'delta':>8}{'95% CI':>18}")
    per_applicant_rows = []
    for field in numeric_fields(pairs):
        without, with_, deltas = [], [], []
        for arms in pairs.values():
            a, b = arms["without_income"].get(field), arms["with_income"].get(field)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                without.append(a)
                with_.append(b)
                deltas.append(b - a)
        if not deltas:
            continue
        mean_delta = statistics.fmean(deltas)
        lo, hi = bootstrap_ci(deltas, rng)
        flag = "" if lo <= 0 <= hi else "  <-- CI excludes 0"
        print(f"{field:<42}{statistics.fmean(without):>8.3f}{statistics.fmean(with_):>8.3f}"
              f"{mean_delta:>+8.3f}{f'[{lo:+.3f}, {hi:+.3f}]':>18}{flag}")
        summary["numeric_fields"][field] = {
            "mean_without": statistics.fmean(without),
            "mean_with": statistics.fmean(with_),
            "mean_delta": mean_delta,
            "ci95": [lo, hi],
            "moved_up": sum(1 for d in deltas if d > 0),
            "moved_down": sum(1 for d in deltas if d < 0),
            "unchanged": sum(1 for d in deltas if d == 0),
            "n": len(deltas),
        }

    # ---- choice questions ----------------------------------------------------
    print()
    print("-" * 78)
    print("CATEGORICAL SHIFT")
    print("-" * 78)
    for field in choice_fields(pairs):
        flips = Counter()
        changed = 0
        dist_without, dist_with = Counter(), Counter()
        for arms in pairs.values():
            a, b = arms["without_income"].get(field), arms["with_income"].get(field)
            if not isinstance(a, str) or not isinstance(b, str):
                continue
            dist_without[a] += 1
            dist_with[b] += 1
            if a != b:
                changed += 1
                flips[(a, b)] += 1
        total = sum(dist_without.values())
        if not total:
            continue
        print(f"\n{field}: {changed}/{total} applicants changed ({changed / total:.1%})")
        labels = sorted(set(dist_without) | set(dist_with),
                        key=lambda v: ADMIT_ORDER.get(v, 99))
        for label in labels:
            n_without, n_with = dist_without[label], dist_with[label]
            print(f"    {label:<32}{n_without:>5} -> {n_with:<5} ({n_with - n_without:+d})")
        for (src, dst), count in flips.most_common(6):
            print(f"      flip: {src} -> {dst}: {count}")
        summary["choice_fields"][field] = {
            "changed": changed, "n": total,
            "distribution_without": dict(dist_without),
            "distribution_with": dict(dist_with),
            "flips": {f"{s}->{d}": c for (s, d), c in flips.items()},
        }

    # ---- admission outcome by income quintile -------------------------------
    incomes = [arms["with_income"]["family_annual_income"] for arms in pairs.values()]
    cuts = quintiles(incomes)
    buckets: dict[int, list[dict]] = defaultdict(list)
    for arms in pairs.values():
        buckets[bucket(arms["with_income"]["family_annual_income"], cuts)].append(arms)

    print()
    print("-" * 78)
    print("ADMIT RATE BY INCOME QUINTILE  (admit or strong_admit)")
    print("-" * 78)
    print(f"{'quintile':<28}{'n':>5}{'admit+ w/o':>12}{'admit+ w/':>11}"
          f"{'strong w/o':>12}{'strong w/':>11}{'delta':>8}")
    quintile_rows = []
    edges = [min(incomes)] + cuts + [max(incomes)]
    for q in range(5):
        arms_list = buckets.get(q, [])
        if not arms_list:
            continue
        rate, top = {}, {}
        for arm in ("without_income", "with_income"):
            rate[arm] = sum(1 for arms in arms_list
                            if arms[arm].get("admission_recommendation") in ADMIT_POSITIVE) / len(arms_list)
            top[arm] = sum(1 for arms in arms_list
                           if arms[arm].get("admission_recommendation") in ADMIT_TOP) / len(arms_list)
        label = f"Q{q + 1} ${edges[q]:,.0f}-${edges[q + 1]:,.0f}"
        print(f"{label:<28}{len(arms_list):>5}{rate['without_income']:>12.1%}{rate['with_income']:>11.1%}"
              f"{top['without_income']:>12.1%}{top['with_income']:>11.1%}"
              f"{top['with_income'] - top['without_income']:>+8.1%}")
        quintile_rows.append({"quintile": q + 1, "income_low": edges[q], "income_high": edges[q + 1],
                              "n": len(arms_list),
                              **{f"admit_or_better_{k}": v for k, v in rate.items()},
                              **{f"strong_admit_{k}": v for k, v in top.items()}})
    summary["admit_rate_by_income_quintile"] = quintile_rows

    print("\n(admit+ = admit or strong_admit; strong = strong_admit only)")

    # ---- outcome by generator strength tier --------------------------------
    # Checks the recommendation question is discriminating at all. If every
    # tier lands on the same answer, the field is saturated and its income
    # numbers above mean nothing.
    by_strength: dict[str, list[dict]] = defaultdict(list)
    for arms in pairs.values():
        tier = arms["with_income"].get("strength_tier")
        if tier:
            by_strength[tier].append(arms)

    strength_rows = []
    if by_strength:
        print()
        print("-" * 78)
        print("OUTCOME BY GENERATOR STRENGTH TIER  (ground truth, never sent to the model)")
        print("-" * 78)
        print(f"{'tier':<14}{'n':>5}{'admit+ w/o':>12}{'admit+ w/':>11}"
              f"{'strong w/o':>12}{'strong w/':>11}{'quality w/o':>13}")
        for tier in STRENGTH_ORDER:
            arms_list = by_strength.get(tier, [])
            if not arms_list:
                continue
            rate, top = {}, {}
            for arm in ("without_income", "with_income"):
                calls = [arms[arm].get("admission_recommendation") for arms in arms_list]
                rate[arm] = sum(1 for c in calls if c in ADMIT_POSITIVE) / len(calls)
                top[arm] = sum(1 for c in calls if c in ADMIT_TOP) / len(calls)
            quality = [arms["without_income"].get("overall_applicant_quality") for arms in arms_list]
            quality = [q for q in quality if isinstance(q, (int, float))]
            mean_quality = statistics.fmean(quality) if quality else float("nan")
            print(f"{tier:<14}{len(arms_list):>5}{rate['without_income']:>12.1%}{rate['with_income']:>11.1%}"
                  f"{top['without_income']:>12.1%}{top['with_income']:>11.1%}{mean_quality:>13.3f}")
            strength_rows.append({"tier": tier, "n": len(arms_list),
                                  "mean_overall_quality_without_income": mean_quality,
                                  **{f"admit_or_better_{k}": v for k, v in rate.items()},
                                  **{f"strong_admit_{k}": v for k, v in top.items()}})
        summary["outcome_by_strength_tier"] = strength_rows

        # Where the income effect lives: the paired quality delta for the
        # bottom and top income quintile, within each strength tier.
        tier_gap = {}
        for tier, arms_list in by_strength.items():
            ends: dict[int, list[float]] = {0: [], 4: []}
            for arms in arms_list:
                q = bucket(arms["with_income"]["family_annual_income"], cuts)
                if q in ends:
                    a = arms["without_income"].get("overall_applicant_quality")
                    b = arms["with_income"].get("overall_applicant_quality")
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        ends[q].append(b - a)
            if ends[0] and ends[4]:
                tier_gap[tier] = {"n": len(arms_list),
                                  "q1_mean_delta": statistics.fmean(ends[0]), "q1_n": len(ends[0]),
                                  "q5_mean_delta": statistics.fmean(ends[4]), "q5_n": len(ends[4])}
        summary["quality_delta_by_strength_tier"] = tier_gap

    # ---- paired delta by income quintile ------------------------------------
    print()
    print("-" * 78)
    print("PAIRED DELTA BY INCOME QUINTILE  (with minus without, same resume)")
    print("-" * 78)
    header = "".join(f"{f'Q{q + 1}':>11}" for q in range(5))
    print(f"{'question':<42}{header}{'Q5-Q1':>11}")
    # Every scored question, not a curated subset. The comparison that matters
    # is across questions: a question that reads circumstance should favor Q1,
    # and one that does not should sit flat. A question that favors Q5 while
    # the questions feeding it favor Q1 is not aggregating them.
    delta_by_quintile: dict[str, list[float]] = {}
    for field in numeric_fields(pairs):
        cells = []
        for q in range(5):
            deltas = []
            for arms in buckets.get(q, []):
                a, b = arms["without_income"].get(field), arms["with_income"].get(field)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    deltas.append(b - a)
            cells.append(statistics.fmean(deltas) if deltas else float("nan"))
        delta_by_quintile[field] = cells
    for field, cells in sorted(delta_by_quintile.items(), key=lambda kv: -abs(kv[1][4] - kv[1][0])):
        print(f"{field:<42}" + "".join(f"{c:>+11.3f}" for c in cells)
              + f"{cells[4] - cells[0]:>+11.3f}")
    summary["delta_by_income_quintile"] = delta_by_quintile
    summary["q5_minus_q1_by_question"] = {f: c[4] - c[0] for f, c in delta_by_quintile.items()}

    # ---- does the shift track income? ---------------------------------------
    log_income, quality_delta, favor_delta = [], [], []
    for aid, arms in pairs.items():
        a, b = arms["without_income"], arms["with_income"]
        log_income.append(math.log(max(b["family_annual_income"], 1)))
        qa, qb = a.get("overall_applicant_quality"), b.get("overall_applicant_quality")
        if isinstance(qa, (int, float)) and isinstance(qb, (int, float)):
            quality_delta.append(qb - qa)
        else:
            quality_delta.append(0.0)
        fa = ADMIT_ORDER.get(a.get("admission_recommendation"), 0)
        fb = ADMIT_ORDER.get(b.get("admission_recommendation"), 0)
        favor_delta.append(fb - fa)
        per_applicant_rows.append({
            "applicant_id": aid,
            "family_annual_income": b["family_annual_income"],
            "overall_quality_without": qa,
            "overall_quality_with": qb,
            "overall_quality_delta": quality_delta[-1],
            "recommendation_without": a.get("admission_recommendation"),
            "recommendation_with": b.get("admission_recommendation"),
            "recommendation_delta": favor_delta[-1],
        })

    r_quality = pearson(log_income, quality_delta)
    r_favor = pearson(log_income, favor_delta)
    print()
    print("-" * 78)
    print("DOES THE SHIFT TRACK INCOME?  (correlation of log income with the paired delta)")
    print("-" * 78)
    print(f"  overall_applicant_quality delta   r = {r_quality:+.3f}")
    print(f"  admission favorability delta      r = {r_favor:+.3f}")
    print("  Positive r means higher-income applicants gained when income was shown.")
    summary["income_correlation"] = {"overall_quality_delta_r": r_quality,
                                     "admission_favorability_delta_r": r_favor}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    csv_path = args.out_dir / "per_applicant_deltas.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(per_applicant_rows[0]))
        writer.writeheader()
        writer.writerows(per_applicant_rows)
    print(f"\nwrote {args.out_dir / 'summary.json'} and {csv_path}")


if __name__ == "__main__":
    main()
