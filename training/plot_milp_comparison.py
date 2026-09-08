from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(description="Plot Initial/SA/LNS/MILP/PPO comparison.")
    parser.add_argument("--summary", default="results/multilayer_demand_sweep_summary.csv")
    parser.add_argument("--ppo-csv", default="training/results_milp/ppo_milp_fast_top32.csv")
    parser.add_argument("--ppo-label", default="Fast MILP-Teacher PPO (top-32)")
    parser.add_argument("--milp-dir", default="training/milp_teacher_eval")
    parser.add_argument("--output", default="results/01_final_milp_teacher_ppo_comparison.png")
    parser.add_argument("--metrics-output", default="training/results_milp/final_comparison.csv")
    return parser.parse_args()


def main():
    args = parse_args()
    with Path(args.summary).open("r", newline="", encoding="utf-8") as stream:
        summary = list(csv.DictReader(stream))
    with Path(args.ppo_csv).open("r", newline="", encoding="utf-8") as stream:
        ppo_rows = list(csv.DictReader(stream))
    ppo_by_demand = {int(row["num_demands"]): row for row in ppo_rows}

    combined = []
    for row in summary:
        count = int(float(row["num_demands"]))
        seed = 42 + 1000 * count
        teacher_path = Path(args.milp_dir) / f"milp_teacher_d{count}_seed{seed}.json"
        teacher = json.loads(teacher_path.read_text(encoding="utf-8"))
        if not teacher.get("sa_constraint_check", {}).get("feasible", False):
            raise ValueError(f"MILP teacher failed project constraint check: {teacher_path}")
        initial = float(row["initial_cost"])
        ppo = float(ppo_by_demand[count]["ppo_cost"])
        milp = float(teacher["milp"]["objective"])
        combined.append(
            {
                "num_demands": count,
                "initial": initial,
                "sa": float(row["best_cost"]),
                "lns": float(row["lns_cost"]),
                "milp_optimum": milp,
                "milp_teacher_ppo": ppo,
                "ppo_improvement_percent": (initial - ppo) / initial * 100.0,
                "ppo_gap_to_milp": ppo - milp,
                "ppo_feasible": int(ppo_by_demand[count]["ppo_feasible"]),
            }
        )

    metrics_path = Path(args.metrics_output)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)

    x = [row["num_demands"] for row in combined]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.plot(x, [r["initial"] for r in combined], "o--", label="Initial Allocation", color="steelblue")
    ax.plot(x, [r["sa"] for r in combined], "s-", label="SA Optimized", color="tomato")
    ax.plot(x, [r["lns"] for r in combined], "^-", label="LNS-Repair", color="seagreen")
    ax.plot(x, [r["milp_optimum"] for r in combined], "P-", label="MILP Optimum (CPLEX)", color="black")
    ax.plot(x, [r["milp_teacher_ppo"] for r in combined], "D-", label=args.ppo_label, color="mediumpurple")
    ax.set_xlabel("Number of Demands")
    ax.set_ylabel("Number of Lightpaths")
    ax.set_title("Cross-layer Optimization: CPLEX Teacher and PPO Student")
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(ncol=2)
    fig.tight_layout()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    print(f"[+] Final comparison CSV: {metrics_path}")
    print(f"[+] Final comparison plot: {output_path}")


if __name__ == "__main__":
    main()
