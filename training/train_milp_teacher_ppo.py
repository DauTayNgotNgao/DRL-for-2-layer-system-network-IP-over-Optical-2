from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3.common.monitor import Monitor

from src_hung.main import load_config
from training.common import (
    build_topology,
    fixed_instance_factory,
    make_instance,
    make_training_factory,
)
from training.ppo_env import CrossLayerPPOEnv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Behavior-clone a licensed CPLEX MILP teacher, then fine-tune PPO."
    )
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument(
        "--teacher-dirs",
        default="MILP/teacher_outputs,training/milp_teacher",
    )
    parser.add_argument("--teacher-cases-per-demand", type=int, default=30)
    parser.add_argument("--bc-epochs", type=int, default=25)
    parser.add_argument("--bc-batch-size", type=int, default=128)
    parser.add_argument("--bc-learning-rate", type=float, default=5e-4)
    parser.add_argument("--timesteps", type=int, default=8192)
    parser.add_argument(
        "--demand-points", default="2,4,5,6,8,10,12,15,18,20,25,30,40,50"
    )
    parser.add_argument("--max-demands", type=int, default=50)
    parser.add_argument("--k-paths", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="training/artifacts_milp")
    return parser.parse_args()


def _teacher_route_edges(payload: dict) -> dict[str, set[tuple[int, int]]]:
    routes = {}
    for route in payload.get("teacher", {}).get("demand_routes", []):
        demand_id = route.get("demand_id")
        if demand_id is None:
            continue
        routes[demand_id] = {
            (int(hop["source"]), int(hop["target"]))
            for hop in route.get("ip_hops", [])
        }
    return routes


def _balanced_teacher_files(
    directories: list[Path], cases_per_demand: int, seed: int
) -> list[tuple[Path, dict]]:
    grouped: dict[int, list[tuple[Path, dict]]] = defaultdict(list)
    seen = set()
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.glob("milp_teacher_d*_seed*.json"):
            key = path.name
            if key in seen:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not payload.get("sa_constraint_check", {}).get("feasible", False):
                continue
            if not payload.get("teacher", {}).get("demand_routes"):
                continue
            count = int(payload["case"]["num_demands"])
            # Keep the demand-sweep seed (42 + 1000*d) strictly held out.
            if int(payload["case"]["seed"]) == 42 + 1000 * count:
                continue
            grouped[count].append((path, payload))
            seen.add(key)

    rng = random.Random(seed)
    selected = []
    for count in sorted(grouped):
        cases = grouped[count]
        rng.shuffle(cases)
        selected.extend(cases[:cases_per_demand])
    rng.shuffle(selected)
    return selected


def collect_demonstrations(
    files: list[tuple[Path, dict]],
    config: dict,
    max_demands: int,
    k_paths: int,
    max_steps: int,
):
    physical_net, ip_graph, ip_to_opt_map = build_topology(config)
    observations: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    actions: list[int] = []
    stats = {
        "teacher_files": len(files),
        "usable_teacher_files": 0,
        "matched_route_actions": 0,
        "unmatched_teacher_route_checks": 0,
        "teacher_initial_cost_sum": 0.0,
        "teacher_milp_cost_sum": 0.0,
        "rollout_best_cost_sum": 0.0,
    }

    for file_index, (_path, payload) in enumerate(files, start=1):
        count = int(payload["case"]["num_demands"])
        seed = int(payload["case"]["seed"])
        if count > max_demands:
            continue
        instance = make_instance(
            config, physical_net, ip_graph, ip_to_opt_map, count, seed
        )
        env = CrossLayerPPOEnv(
            fixed_instance_factory(instance),
            max_demands=max_demands,
            k_paths=k_paths,
            max_steps=max_steps,
            seed=seed,
        )
        observation, _ = env.reset()
        desired = _teacher_route_edges(payload)
        usable = False

        for _ in range(max_steps - 1):
            ranked_actions = []
            for demand_index, demand in enumerate(env.demands):
                target_edges = desired.get(demand.id)
                if not target_edges:
                    continue
                current_edges = set(env.state.get_demand_edges(demand.id))
                if current_edges == target_edges:
                    continue
                matching_rank = None
                for path_rank, path in enumerate(env._candidate_ip_paths(demand)):
                    if set(env._path_edges(path)) == target_edges:
                        matching_rank = path_rank
                        break
                if matching_rank is None:
                    stats["unmatched_teacher_route_checks"] += 1
                    continue
                action = 1 + demand_index * k_paths + matching_rank
                # MILP-relevant demands that can release more LP capacity go first.
                feature_offset = env.GLOBAL_FEATURES + demand_index * env.DEMAND_FEATURES
                saving_feature = float(observation[feature_offset + 5])
                priority = saving_feature * 10.0 + float(demand.bandwidth) / 100.0
                ranked_actions.append((priority, action))

            if not ranked_actions:
                break
            ranked_actions.sort(reverse=True)
            chosen = None
            chosen_candidate = None
            chosen_cost = float("inf")
            # Follow the first feasible high-priority MILP action.  Ranking every
            # candidate by a full repair/check is unnecessarily expensive.
            for _priority, action in ranked_actions[:12]:
                demand_index, path_rank = env._decode_action(action)
                candidate = env._candidate_from_action(demand_index, path_rank)
                if candidate is None:
                    continue
                candidate_cost = float(env.cost_calculator.calculate_objective(candidate))
                if np.isfinite(candidate_cost):
                    chosen = action
                    chosen_candidate = candidate
                    chosen_cost = candidate_cost
                    break
            if chosen is None:
                break

            observations.append(observation.copy())
            masks.append(env.action_masks().copy())
            actions.append(chosen)
            # Commit the already checked candidate instead of recomputing it in step().
            env.step_count += 1
            env.state = chosen_candidate
            env.current_cost = chosen_cost
            env.accepted_moves += 1
            if chosen_cost < env.best_cost:
                env.best_cost = chosen_cost
                env.best_state = chosen_candidate.deepcopy()
            observation = env._observation()
            stats["matched_route_actions"] += 1
            usable = True
            if env.step_count >= env.max_steps:
                break

        # Teach the stopping decision after the useful MILP-aligned sequence.
        observations.append(observation.copy())
        masks.append(env.action_masks().copy())
        actions.append(0)
        if usable:
            stats["usable_teacher_files"] += 1
        stats["teacher_initial_cost_sum"] += env.initial_cost
        stats["teacher_milp_cost_sum"] += float(payload["milp"]["objective"])
        stats["rollout_best_cost_sum"] += env.best_cost
        env.close()
        if file_index % 20 == 0:
            print(
                f"[+] Extracted demonstrations from {file_index}/{len(files)} teachers",
                flush=True,
            )

    if not observations:
        raise RuntimeError("No usable MILP teacher demonstrations were extracted.")
    dataset = (
        np.asarray(observations, dtype=np.float32),
        np.asarray(masks, dtype=bool),
        np.asarray(actions, dtype=np.int64),
    )
    return dataset, stats


def behavior_clone(
    model: MaskablePPO,
    observations: np.ndarray,
    masks: np.ndarray,
    actions: np.ndarray,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
):
    rng = np.random.default_rng(seed)
    indices = np.arange(len(actions))
    rng.shuffle(indices)
    split = max(1, int(len(indices) * 0.9))
    train_indices, validation_indices = indices[:split], indices[split:]
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=learning_rate)
    history = []

    for epoch in range(1, epochs + 1):
        rng.shuffle(train_indices)
        model.policy.train()
        total_loss = total_correct = total_items = 0
        for start in range(0, len(train_indices), batch_size):
            batch = train_indices[start:start + batch_size]
            obs_tensor = torch.as_tensor(observations[batch], device=model.device)
            mask_tensor = torch.as_tensor(masks[batch], device=model.device)
            action_tensor = torch.as_tensor(actions[batch], device=model.device)
            distribution = model.policy.get_distribution(
                obs_tensor, action_masks=mask_tensor
            )
            logits = distribution.distribution.logits
            loss = F.cross_entropy(logits, action_tensor)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.policy.parameters(), 0.5)
            optimizer.step()
            total_loss += float(loss.item()) * len(batch)
            total_correct += int((logits.argmax(dim=1) == action_tensor).sum().item())
            total_items += len(batch)

        model.policy.eval()
        with torch.no_grad():
            val_obs = torch.as_tensor(observations[validation_indices], device=model.device)
            val_masks = torch.as_tensor(masks[validation_indices], device=model.device)
            val_actions = torch.as_tensor(actions[validation_indices], device=model.device)
            val_dist = model.policy.get_distribution(val_obs, action_masks=val_masks)
            val_logits = val_dist.distribution.logits
            val_loss = float(F.cross_entropy(val_logits, val_actions).item())
            val_accuracy = float((val_logits.argmax(dim=1) == val_actions).float().mean().item())
        row = {
            "epoch": epoch,
            "train_loss": total_loss / max(1, total_items),
            "train_accuracy": total_correct / max(1, total_items),
            "validation_loss": val_loss,
            "validation_accuracy": val_accuracy,
        }
        history.append(row)
        print(
            f"[BC] epoch={epoch:02d}, loss={row['train_loss']:.4f}, "
            f"acc={row['train_accuracy']:.3f}, val_acc={val_accuracy:.3f}"
        )
    return history


def read_monitor(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        stream.readline()
        return list(csv.DictReader(stream))


def plot_training(bc_history, monitor_rows, output_path: Path):
    rewards = [float(row["r"]) for row in monitor_rows]
    smooth = []
    for index in range(len(rewards)):
        values = rewards[max(0, index - 19): index + 1]
        smooth.append(sum(values) / len(values))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot([r["epoch"] for r in bc_history], [r["train_loss"] for r in bc_history], label="Train loss")
    axes[0].plot([r["epoch"] for r in bc_history], [r["validation_loss"] for r in bc_history], label="Validation loss")
    axes[0].set_title("MILP Behavior Cloning")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Cross-entropy")
    axes[0].legend()
    axes[0].grid(True, linestyle="--", alpha=0.4)
    axes[1].plot(rewards, alpha=0.25, label="Episode reward")
    axes[1].plot(smooth, linewidth=2, label="Moving average (20)")
    axes[1].set_title("PPO Fine-tuning")
    axes[1].set_xlabel("Episode")
    axes[1].set_ylabel("Reward")
    axes[1].legend()
    axes[1].grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    demand_points = [int(value) for value in args.demand_points.split(",") if value.strip()]
    teacher_dirs = [Path(value.strip()) for value in args.teacher_dirs.split(",") if value.strip()]
    config = load_config(args.config)
    teacher_files = _balanced_teacher_files(
        teacher_dirs, args.teacher_cases_per_demand, args.seed
    )
    print(f"[+] Selected {len(teacher_files)} feasible CPLEX teacher cases")
    (observations, masks, actions), teacher_stats = collect_demonstrations(
        teacher_files,
        config,
        args.max_demands,
        args.k_paths,
        args.max_steps,
    )
    np.savez_compressed(
        output_dir / "milp_demonstrations.npz",
        observations=observations,
        action_masks=masks,
        actions=actions,
    )
    print(f"[+] Demonstration transitions: {len(actions)}")

    _, factory = make_training_factory(args.config, demand_points, args.seed + 7)
    raw_env = CrossLayerPPOEnv(
        factory,
        max_demands=args.max_demands,
        k_paths=args.k_paths,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    monitor_path = output_dir / "ppo_finetune.monitor.csv"
    monitored = Monitor(raw_env, filename=str(monitor_path))
    env = ActionMasker(monitored, lambda wrapped: wrapped.unwrapped.action_masks())
    model = MaskablePPO(
        "MlpPolicy",
        env,
        learning_rate=2e-4,
        n_steps=512,
        batch_size=128,
        n_epochs=8,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        verbose=1,
        seed=args.seed,
        device="cpu",
        policy_kwargs={"net_arch": [256, 256]},
    )
    bc_history = behavior_clone(
        model,
        observations,
        masks,
        actions,
        args.bc_epochs,
        args.bc_batch_size,
        args.bc_learning_rate,
        args.seed,
    )
    model.save(str(output_dir / "ppo_milp_bc"))
    model.learn(total_timesteps=max(512, args.timesteps), progress_bar=False)
    checkpoint = output_dir / "ppo_milp_teacher"
    model.save(str(checkpoint))
    env.close()

    with (output_dir / "bc_history.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(bc_history[0]))
        writer.writeheader()
        writer.writerows(bc_history)
    monitor_rows = read_monitor(monitor_path)
    plot_training(bc_history, monitor_rows, output_dir / "milp_teacher_training_curve.png")

    teacher_stats["demonstration_transitions"] = len(actions)
    teacher_stats["bc_final_validation_accuracy"] = bc_history[-1]["validation_accuracy"]
    metadata = {
        "algorithm": "MaskablePPO",
        "teacher": "licensed IBM CPLEX MILP",
        "training_method": "behavior cloning + PPO fine-tuning",
        "timesteps": max(512, args.timesteps),
        "teacher_stats": teacher_stats,
        "demand_points": demand_points,
        "max_demands": args.max_demands,
        "k_paths": args.k_paths,
        "max_steps": args.max_steps,
        "seed": args.seed,
        "checkpoint": str(checkpoint.with_suffix(".zip")),
    }
    (output_dir / "ppo_milp_teacher.metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"[+] Final checkpoint: {checkpoint.with_suffix('.zip')}")
    print(f"[+] Training curve: {output_dir / 'milp_teacher_training_curve.png'}")


if __name__ == "__main__":
    main()
