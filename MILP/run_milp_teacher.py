from __future__ import annotations

import argparse
import json
from pathlib import Path

from src_hung.main import initialize_state_multilayer, load_config
from src_hung.model.demand import generate_random_demands
from src_hung.model.network import generate_multilayer_topology
from src_hung.objective.cost_func import CostCalculator

from MILP.hypergiant_adapter import (
    build_input_instance_from_generated_data,
    solution_to_teacher_labels,
    solve_input_instance,
    state_from_solution_dict,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Hypergiant MILP logic on generated project data with native IBM CPLEX."
    )
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--num-demands", type=int, default=None)
    parser.add_argument("--demand-points", type=int, nargs="*", default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--start-rep",
        type=int,
        default=0,
        help="Starting repetition index, useful for resuming teacher generation.",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--topology-seed",
        type=int,
        default=None,
        help="Seed for the fixed topology. Default uses config random_seed, matching demand_sweep.",
    )
    parser.add_argument("--solver", choices=["cplex"], default="cplex")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Seconds. Default is no limit, preserving the slow exact MILP behavior.",
    )
    parser.add_argument(
        "--ip-candidate-mode",
        choices=["complete", "generated"],
        default="generated",
        help=(
            "complete keeps the original MILP virtual-topology search over all IP "
            "pairs; generated fixes connectivity to the generated IP graph."
        ),
    )
    parser.add_argument("--ip-link-utilization", type=float, default=None)
    parser.add_argument("--num-transceivers", type=int, default=None)
    parser.add_argument("--optical-candidate-k", type=int, default=None)
    parser.add_argument(
        "--disable-rho",
        action="store_true",
        help="Do not enforce SA rho_limit in CPLEX. Default enforces it.",
    )
    parser.add_argument("--output-dir", default="MILP/teacher_outputs")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip teacher JSON files that already exist instead of overwriting them.",
    )
    parser.add_argument("--export-lp", action="store_true")
    parser.add_argument("--cplex-log", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    base_seed = args.seed if args.seed is not None else config["random_seed"]
    topology_seed = args.topology_seed if args.topology_seed is not None else config["random_seed"]
    demand_points = args.demand_points
    if not demand_points:
        demand_points = [args.num_demands or config["demands"]["num_demands"]]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for num_demands in demand_points:
        for rep in range(args.start_rep, args.start_rep + args.repetitions):
            case_seed = base_seed if args.seed is not None else num_demands * 1000 + base_seed + rep
            output_path = output_dir / f"milp_teacher_d{num_demands}_seed{case_seed}.json"
            lp_path = output_path.with_suffix(".lp") if args.export_lp else None
            if args.skip_existing and output_path.exists():
                print(f"[=] Skip existing teacher data: {output_path}")
                continue

            run_one_case(
                config=config,
                num_demands=num_demands,
                seed=case_seed,
                topology_seed=topology_seed,
                args=args,
                output_path=output_path,
                lp_path=lp_path,
            )


def run_one_case(
    *,
    config: dict,
    num_demands: int,
    seed: int,
    topology_seed: int,
    args: argparse.Namespace,
    output_path: Path,
    lp_path: Path | None,
) -> None:
    net_cfg = config["network"]
    demand_cfg = config["demands"]
    init_cfg = config.get("initialization", {})
    sa_cfg = config.get("sa", {})
    optical_candidate_k = args.optical_candidate_k or init_cfg.get("k_shortest", 10)
    rho_limit = None if args.disable_rho else sa_cfg.get("rho_limit")

    print(f"\n[+] MILP teacher: num_demands={num_demands}, seed={seed}, topology_seed={topology_seed}")

    physical_net, ip_graph, ip_to_opt_map = generate_multilayer_topology(
        opt_nodes=net_cfg["opt_nodes"],
        opt_links=net_cfg["opt_links"],
        ip_nodes=net_cfg["ip_nodes"],
        ip_links=net_cfg["ip_links"],
        num_slots=net_cfg["num_slots"],
        lightpath_capacity=net_cfg["lightpath_capacity"],
        seed=topology_seed,
    )
    demands = generate_random_demands(
        num_demands=num_demands,
        num_ip_nodes=net_cfg["ip_nodes"],
        bw_min=demand_cfg["bw_min"],
        bw_max=demand_cfg["bw_max"],
        seed=seed,
    )
    initial_state = initialize_state_multilayer(
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        demands=demands,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        k_shortest=optical_candidate_k,
        seed=seed,
    )

    input_instance, metadata = build_input_instance_from_generated_data(
        physical_net=physical_net,
        ip_graph=ip_graph,
        ip_to_opt_map=ip_to_opt_map,
        demands=demands,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        ip_candidate_mode=args.ip_candidate_mode,
        ip_link_utilization=args.ip_link_utilization,
        num_transceivers=args.num_transceivers,
        optical_candidate_k=optical_candidate_k,
        initial_state=initial_state,
        rho_limit=rho_limit,
        topology_name=f"generated_topo{topology_seed}_d{num_demands}_seed{seed}",
    )

    model, solution, status_name = solve_input_instance(
        input_instance,
        solver=args.solver,
        threads=args.threads,
        time_limit=args.time_limit,
        export_lp=str(lp_path) if lp_path is not None else None,
        enable_output=args.cplex_log,
    )
    solution_dict = solution
    teacher_labels = solution_to_teacher_labels(solution_dict)
    constraint_check = evaluate_with_sa_constraints(
        solution_dict=solution_dict,
        initial_state=initial_state,
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        rho_limit=rho_limit,
    )

    payload = {
        "case": {
            "num_demands": num_demands,
            "seed": seed,
            "topology_seed": topology_seed,
            "solver": args.solver,
            "threads": args.threads,
            "time_limit_seconds": args.time_limit,
        },
        "input": metadata,
        "milp": {
            "status": int(model.result_status),
            "status_name": status_name,
            "objective": solution_dict.get("metrics", {}).get("objective"),
            "model_build_time_ms": solution_dict.get("metrics", {}).get("model_build_time"),
            "solver_time_ms": solution_dict.get("metrics", {}).get("solver_time"),
            "total_milp_time_ms": solution_dict.get("metrics", {}).get("total_milp_time"),
            "best_bound": solution_dict.get("metrics", {}).get("best_bound"),
            "problem_stats": model.stats(),
        },
        "sa_constraint_check": constraint_check,
        "solution": solution_dict,
        "teacher": teacher_labels,
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        "[+] Done: "
        f"status={status_name}, objective={payload['milp']['objective']}, "
        f"total_milp_time_ms={payload['milp']['total_milp_time_ms']}, "
        f"sa_feasible={constraint_check['feasible']}"
    )
    print(f"[+] Saved teacher data: {output_path}")


def evaluate_with_sa_constraints(
    *,
    solution_dict: dict,
    initial_state,
    demands,
    ip_graph,
    opt_graph,
    ip_to_opt_map,
    lightpath_capacity: float,
    num_slots: int,
    rho_limit: int | None,
) -> dict:
    if not solution_dict.get("lightpaths"):
        return {"feasible": False, "reason": "no_cplex_solution_lightpaths"}

    cplex_state = state_from_solution_dict(
        solution_dict=solution_dict,
        demands=demands,
        initial_state=initial_state,
    )
    cost_calculator = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=lightpath_capacity,
        num_slots=num_slots,
        rho_limit=rho_limit,
    )
    cost, details = cost_calculator.calculate_objective(cplex_state, return_details=True)
    details["objective_cost_checked_by_sa"] = cost
    return details


if __name__ == "__main__":
    main()
