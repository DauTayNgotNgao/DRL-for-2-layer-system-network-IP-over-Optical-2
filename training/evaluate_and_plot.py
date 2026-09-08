from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sb3_contrib import MaskablePPO

from src_hung.main import load_config
from training.common import build_topology, fixed_instance_factory, make_instance
from training.ppo_env import CrossLayerPPOEnv, run_fast_policy_search, run_policy_episode


def parse_args():
    parser = argparse.ArgumentParser(description="Run PPO inference and merge it into the current comparison plot.")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--checkpoint", default="training/artifacts/ppo_short.zip")
    parser.add_argument("--summary", default="results/multilayer_demand_sweep_summary.csv")
    parser.add_argument("--output-dir", default="training/results")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--stochastic", action="store_true")
    parser.add_argument(
        "--best-of",
        action="store_true",
        help="Run one deterministic rollout plus stochastic rollouts and keep the best.",
    )
    parser.add_argument("--fast-greedy", action="store_true")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--fast-max-steps", type=int, default=16)
    parser.add_argument(
        "--label", default="PPO Inference", help="Legend label for the evaluated checkpoint."
    )
    parser.add_argument(
        "--csv-name", default="ppo_inference.csv", help="Inference CSV filename."
    )
    parser.add_argument(
        "--plot-name",
        default="01_initial_vs_sa_vs_lns_vs_ppo.png",
        help="Plot filename under results/.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    checkpoint = Path(args.checkpoint)
    metadata_path = checkpoint.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    config = load_config(args.config)
    physical_net, ip_graph, ip_to_opt_map = build_topology(config)
    with Path(args.summary).open("r", newline="", encoding="utf-8") as stream:
        summary = list(csv.DictReader(stream))

    model = MaskablePPO.load(str(checkpoint), device="cpu")
    inference_rows = []
    for row in summary:
        count = int(float(row["num_demands"]))
        case_seed = config["random_seed"] + 1000 * count
        instance = make_instance(
            config, physical_net, ip_graph, ip_to_opt_map, count, case_seed
        )
        best_state = None
        best_cost = float("inf")
        total_time = 0.0
        best_info = None
        for episode_index in range(max(1, args.episodes)):
            env = CrossLayerPPOEnv(
                fixed_instance_factory(instance),
                max_demands=int(metadata["max_demands"]),
                k_paths=int(metadata["k_paths"]),
                max_steps=int(metadata["max_steps"]),
                seed=int(metadata["seed"]),
            )
            started = time.perf_counter()
            deterministic = not args.stochastic
            if args.best_of:
                deterministic = episode_index == 0
            if args.fast_greedy:
                state, info = run_fast_policy_search(
                    model,
                    env,
                    top_k=args.top_k,
                    max_steps=args.fast_max_steps,
                )
            else:
                state, info = run_policy_episode(model, env, deterministic=deterministic)
            elapsed = time.perf_counter() - started
            cost = float(instance["cost_calculator"].calculate_objective(state))
            total_time += elapsed
            if cost < best_cost:
                best_cost, best_state, best_info = cost, state, info
            env.close()
        initial_cost = float(row["initial_cost"])
        inference_rows.append(
            {
                "num_demands": count,
                "seed": case_seed,
                "initial_cost_regenerated": instance["cost_calculator"].calculate_objective(instance["initial_state"]),
                "ppo_cost": best_cost,
                "ppo_improvement_percent": (initial_cost - best_cost) / initial_cost * 100 if initial_cost else 0.0,
                "ppo_runtime_sec": total_time / max(1, args.episodes),
                "ppo_single_rollout_runtime_sec": total_time / max(1, args.episodes),
                "ppo_total_runtime_sec": total_time,
                "ppo_rollouts": max(1, args.episodes),
                "ppo_accepted_moves": best_info["accepted_moves"],
                "ppo_invalid_moves": best_info["invalid_moves"],
                "ppo_feasible": int(instance["cost_calculator"].is_feasible(best_state)),
            }
        )
        print(f"[+] demands={count}: PPO={best_cost:.0f}, time={total_time / max(1, args.episodes):.3f}s")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / args.csv_name
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inference_rows[0]))
        writer.writeheader()
        writer.writerows(inference_rows)

    x = [int(float(row["num_demands"])) for row in summary]
    initial = [float(row["initial_cost"]) for row in summary]
    sa = [float(row["best_cost"]) for row in summary]
    lns = [float(row["lns_cost"]) for row in summary]
    ppo_by_count = {row["num_demands"]: row["ppo_cost"] for row in inference_rows}
    ppo = [ppo_by_count[value] for value in x]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(x, initial, "o--", label="Initial Allocation", color="steelblue")
    ax.plot(x, sa, "s-", label="SA Optimized", color="tomato")
    ax.plot(x, lns, "^-", label="LNS-Repair", color="seagreen")
    ax.plot(x, ppo, "D-", label=args.label, color="mediumpurple")
    ax.set_xlabel("Number of Demands")
    ax.set_ylabel("Number of Lightpaths")
    ax.set_title(f"Initial vs SA vs LNS vs {args.label}")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()
    fig.tight_layout()
    plot_path = Path("results") / args.plot_name
    fig.savefig(plot_path, dpi=160)
    # Update the legacy project filename only for the primary PPO comparison.
    if args.plot_name in {
        "01_initial_vs_sa_vs_lns_vs_ppo.png",
        "01_initial_vs_sa_vs_lns_vs_milp_ppo.png",
    }:
        fig.savefig("results/01_initial_vs_sa_vs_rl.png", dpi=160)
    plt.close(fig)
    print(f"[+] Inference CSV: {csv_path}")
    print(f"[+] Combined plot: {plot_path}")


if __name__ == "__main__":
    main()
