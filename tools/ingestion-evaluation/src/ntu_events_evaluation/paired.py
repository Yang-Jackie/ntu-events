"""Clustered paired bootstrap for completed fixed-input experiments."""

import argparse
import json
import random
import statistics
from collections import defaultdict
from itertools import combinations

from .paths import run_directory


def compare(data: dict, *, seed: int = 20261008) -> list[dict]:
    if not data["metadata"]["complete"]:
        raise RuntimeError("Wait for all paired observations before interpreting rankings")
    rows = data["rows"]
    report = []
    for stage in ("extraction", "canonicalization"):
        groups = defaultdict(lambda: defaultdict(list))
        for row in rows:
            if row["stage"] == stage:
                groups[row["configuration"]][row["case_id"]].append(
                    float(row["grade"]["all_passed"])
                )
        for a, b in combinations(sorted(groups), 2):
            if groups[a].keys() != groups[b].keys():
                raise RuntimeError("Configurations must cover the same paired cases")
            keys = sorted(groups[a])
            if not keys or any(len(groups[a][k]) != 2 or len(groups[b][k]) != 2 for k in keys):
                raise RuntimeError("Incomplete paired repetitions")
            differences = [
                statistics.mean(groups[a][k]) - statistics.mean(groups[b][k]) for k in keys
            ]
            rng = random.Random(seed)
            samples = sorted(
                statistics.mean(rng.choices(differences, k=len(keys))) for _ in range(10000)
            )
            report.append(
                {
                    "stage": stage,
                    "a": a,
                    "b": b,
                    "unique_cases": len(keys),
                    "difference_percentage_points": round(statistics.mean(differences) * 100, 2),
                    "case_cluster_bootstrap_95_percent_interval": [
                        round(samples[249] * 100, 2),
                        round(samples[9749] * 100, 2),
                    ],
                }
            )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    directory = run_directory(args.run_dir)
    data = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
    report = compare(data)
    (directory / "paired_comparisons.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
