from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3.common.monitor import Monitor

from training.common import make_training_factory
from training.ppo_env import CrossLayerPPOEnv


def parse_args():
    parser = argparse.ArgumentParser(description="Train pure PPO for cross-layer rerouting.")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--timesteps", type=int, default=4096)
    parser.add_argument("--demand-points", default="5,10,15,20,25,30")
    parser.add_argument("--k-paths", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="training/artifacts")
    return parser.parse_args()


def plot_learning_curve(monitor_path: Path, output_path: Path) -> int:
    with monitor_path.open("r", encoding="utf-8") as stream:
        stream.readline()
        rows = list(csv.DictReader(stream))
    rewards = [float(row["r"]) for row in rows]
    if rewards:
        window = min(20, len(rewards))
        smooth = [
            sum(rewards[max(0, i - window + 1): i + 1])
            / len(rewards[max(0, i - window + 1): i + 1])
            for i in range(len(rewards))
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(rewards, alpha=0.3, label="Episode reward")
        ax.plot(smooth, linewidth=2, label=f"Moving average ({window})")
        ax.set_xlabel("Episode")
        ax.set_ylabel("Reward")
        ax.set_title("Short PPO Training Curve")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        fig.savefig(output_path, dpi=160)
        plt.close(fig)
    return len(rewards)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    demand_points = [int(value) for value in args.demand_points.split(",") if value.strip()]
    max_demands = max(demand_points)
    _, factory = make_training_factory(args.config, demand_points, args.seed)

    raw_env = CrossLayerPPOEnv(
        instance_factory=factory,
        max_demands=max_demands,
        k_paths=args.k_paths,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    monitor_path = output_dir / "episodes.monitor.csv"
    monitored = Monitor(raw_env, filename=str(monitor_path))
    env = ActionMasker(monitored, lambda wrapped: wrapped.unwrapped.action_masks())

    model = MaskablePPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        n_steps=256,
        batch_size=64,
        n_epochs=5,
        gamma=0.97,
        gae_lambda=0.95,
        ent_coef=0.02,
        verbose=1,
        seed=args.seed,
        device="cpu",
        policy_kwargs={"net_arch": [128, 128]},
    )
    model.learn(total_timesteps=max(256, args.timesteps), progress_bar=False)
    checkpoint = output_dir / "ppo_short"
    model.save(str(checkpoint))
    env.close()

    metadata = {
        "algorithm": "MaskablePPO",
        "pure_rl": True,
        "uses_sa_or_lns": False,
        "timesteps": max(256, args.timesteps),
        "demand_points": demand_points,
        "max_demands": max_demands,
        "k_paths": args.k_paths,
        "max_steps": args.max_steps,
        "seed": args.seed,
        "checkpoint": str(checkpoint.with_suffix(".zip")),
    }
    (output_dir / "ppo_short.metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    episodes = plot_learning_curve(monitor_path, output_dir / "training_curve.png")
    print(f"[+] PPO checkpoint: {checkpoint.with_suffix('.zip')}")
    print(f"[+] Training episodes: {episodes}")
    print(f"[+] Learning curve: {output_dir / 'training_curve.png'}")


if __name__ == "__main__":
    main()
