from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(description="Compare runtime of all five methods.")
    parser.add_argument("--summary", default="results/multilayer_demand_sweep_summary.csv")
    parser.add_argument("--ppo-csv", default="training/results_milp/ppo_milp_fast_top32.csv")
    parser.add_argument("--milp-dir", default="training/milp_teacher_eval")
    parser.add_argument("--ppo-rollouts", type=int, default=1)
    parser.add_argument("--ppo-label", default="Fast MILP-Teacher PPO (top-32)")
    parser.add_argument("--output", default="results/02_runtime_all_five_methods.png")
    parser.add_argument("--csv-output", default="training/results_milp/runtime_all_five_methods.csv")
    return parser.parse_args()


def main():
    args = parse_args()
    with Path(args.summary).open("r", newline="", encoding="utf-8") as stream:
        summary = list(csv.DictReader(stream))
    with Path(args.ppo_csv).open("r", newline="", encoding="utf-8") as stream:
        ppo_rows = list(csv.DictReader(stream))
    ppo_by_demand = {int(row["num_demands"]): row for row in ppo_rows}

    output_rows = []
    for row in summary:
        count = int(float(row["num_demands"]))
        seed = 42 + 1000 * count
        teacher_path = Path(args.milp_dir) / f"milp_teacher_d{count}_seed{seed}.json"
        teacher = json.loads(teacher_path.read_text(encoding="utf-8"))
        single_ppo = float(ppo_by_demand[count]["ppo_runtime_sec"])
        solver_ms = float(teacher["milp"]["solver_time_ms"])
        build_ms = float(teacher["milp"].get("model_build_time_ms") or 0.0)
        total_milp_ms = float(
            teacher["milp"].get("total_milp_time_ms") or (build_ms + solver_ms)
        )
        output_rows.append(
            {
                "num_demands": count,
                "initial_allocation_sec": float(row["initial_runtime_sec"]),
                "sa_sec": float(row["sa_runtime_sec"]),
                "lns_sec": float(row["lns_runtime_sec"]),
                "milp_model_build_sec": build_ms / 1000.0,
                "milp_cplex_solver_sec": solver_ms / 1000.0,
                "milp_total_sec": total_milp_ms / 1000.0,
                "ppo_single_rollout_sec": single_ppo,
                "ppo_rollouts": args.ppo_rollouts,
                "ppo_best_of_runtime_sec": single_ppo * args.ppo_rollouts,
            }
        )

    csv_path = Path(args.csv_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    x = [row["num_demands"] for row in output_rows]
    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax.plot(x, [r["initial_allocation_sec"] for r in output_rows], "o--", label="Initial Allocation", color="steelblue")
    ax.plot(x, [r["sa_sec"] for r in output_rows], "s-", label="SA Optimized", color="tomato")
    ax.plot(x, [r["lns_sec"] for r in output_rows], "^-", label="LNS-Repair", color="seagreen")
    ax.plot(x, [r["milp_total_sec"] for r in output_rows], "P-", label="MILP/CPLEX (build + solve)", color="black")
    ax.plot(
        x,
        [r["ppo_best_of_runtime_sec"] for r in output_rows],
        "D-",
        label=args.ppo_label,
        color="mediumpurple",
    )
    ax.set_yscale("log")
    ax.set_xlabel("Number of Demands")
    ax.set_ylabel("Runtime (seconds, log scale)")
    ax.set_title("Runtime Comparison of All Five Methods")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.legend(ncol=2)
    fig.tight_layout()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    print(f"[+] Runtime CSV: {csv_path}")
    print(f"[+] Runtime plot: {output_path}")


if __name__ == "__main__":
    main()
