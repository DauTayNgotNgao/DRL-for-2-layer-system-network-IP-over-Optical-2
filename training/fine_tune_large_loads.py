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
    parser = argparse.ArgumentParser(description="Curriculum fine-tune PPO on large demand cases.")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--checkpoint", default="training/artifacts_milp/ppo_milp_teacher.zip")
    parser.add_argument("--demand-points", default="20,25,30,40,50")
    parser.add_argument("--timesteps", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=8e-5)
    parser.add_argument("--output-dir", default="training/artifacts_milp")
    parser.add_argument("--output-name", default="ppo_milp_teacher_large")
    parser.add_argument("--seed", type=int, default=314)
    return parser.parse_args()


def main():
    args = parse_args()
    checkpoint = Path(args.checkpoint)
    metadata_path = checkpoint.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    demand_points = [int(value) for value in args.demand_points.split(",") if value.strip()]
    _, factory = make_training_factory(args.config, demand_points, args.seed)
    raw_env = CrossLayerPPOEnv(
        factory,
        max_demands=int(metadata["max_demands"]),
        k_paths=int(metadata["k_paths"]),
        max_steps=int(metadata["max_steps"]),
        seed=args.seed,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    monitor_path = output_dir / "large_load_finetune.monitor.csv"
    monitored = Monitor(raw_env, filename=str(monitor_path))
    env = ActionMasker(monitored, lambda wrapped: wrapped.unwrapped.action_masks())
    model = MaskablePPO.load(str(checkpoint), env=env, device="cpu")
    model.learning_rate = args.learning_rate
    model.lr_schedule = lambda _progress: args.learning_rate
    model.ent_coef = 0.005
    model.learn(
        total_timesteps=max(512, args.timesteps),
        reset_num_timesteps=False,
        progress_bar=False,
    )
    output_checkpoint = output_dir / args.output_name
    model.save(str(output_checkpoint))
    env.close()

    with monitor_path.open("r", encoding="utf-8") as stream:
        stream.readline()
        rows = list(csv.DictReader(stream))
    rewards = [float(row["r"]) for row in rows]
    smooth = []
    for index in range(len(rewards)):
        window = rewards[max(0, index - 19): index + 1]
        smooth.append(sum(window) / len(window))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(rewards, alpha=0.25, label="Episode reward")
    ax.plot(smooth, linewidth=2, label="Moving average (20)")
    ax.set_title("Large-load PPO Curriculum Fine-tuning")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Reward")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "large_load_finetune_curve.png", dpi=160)
    plt.close(fig)

    metadata.update(
        {
            "training_method": "MILP behavior cloning + PPO + large-load curriculum",
            "large_load_timesteps": max(512, args.timesteps),
            "large_load_demand_points": demand_points,
            "large_load_learning_rate": args.learning_rate,
            "checkpoint": str(output_checkpoint.with_suffix(".zip")),
        }
    )
    output_checkpoint.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"[+] Large-load checkpoint: {output_checkpoint.with_suffix('.zip')}")
    print(f"[+] Fine-tune episodes: {len(rewards)}")


if __name__ == "__main__":
    main()
