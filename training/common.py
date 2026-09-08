from __future__ import annotations

import copy
import random

from src_hung.main import initialize_state_multilayer, load_config
from src_hung.model.demand import generate_random_demands
from src_hung.model.network import generate_multilayer_topology
from src_hung.objective.cost_func import CostCalculator


def build_topology(config):
    net_cfg = config["network"]
    return generate_multilayer_topology(
        opt_nodes=net_cfg["opt_nodes"],
        opt_links=net_cfg["opt_links"],
        ip_nodes=net_cfg["ip_nodes"],
        ip_links=net_cfg["ip_links"],
        num_slots=net_cfg["num_slots"],
        lightpath_capacity=net_cfg["lightpath_capacity"],
        seed=config["random_seed"],
    )


def make_instance(config, physical_net, ip_graph, ip_to_opt_map, num_demands: int, seed: int):
    net_cfg = config["network"]
    demand_cfg = config["demands"]
    k_shortest = config.get("initialization", {}).get("k_shortest", 10)
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
        k_shortest=k_shortest,
        seed=seed,
    )
    obj_cfg = config["objective"]
    calculator = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        weight_energy=obj_cfg["weight_energy"],
        weight_latency=obj_cfg["weight_latency"],
        p_transponder=obj_cfg["p_transponder"],
        rho_limit=config["sa"].get("rho_limit"),
        penalty_flow=obj_cfg.get("penalty_flow", 0),
        penalty_capacity=obj_cfg.get("penalty_capacity", 0),
        penalty_spectrum=obj_cfg.get("penalty_spectrum", 0),
        penalty_lightpath_consistency=obj_cfg.get("penalty_lightpath_consistency", 0),
        penalty_non_disruptive=obj_cfg.get("penalty_non_disruptive", 0),
    )
    return {
        "initial_state": initial_state,
        "demands": demands,
        "ip_graph": ip_graph,
        "opt_graph": physical_net.graph,
        "ip_to_opt_map": ip_to_opt_map,
        "cost_calculator": calculator,
        "num_slots": net_cfg["num_slots"],
        "lightpath_capacity": net_cfg["lightpath_capacity"],
    }


def make_training_factory(config_path: str, demand_points: list[int], seed: int):
    config = copy.deepcopy(load_config(config_path))
    physical_net, ip_graph, ip_to_opt_map = build_topology(config)
    rng = random.Random(seed)

    def factory():
        count = rng.choice(demand_points)
        case_seed = config["random_seed"] + 1000 * count + rng.randrange(100_000)
        return make_instance(
            config, physical_net, ip_graph, ip_to_opt_map, count, case_seed
        )

    return config, factory


def fixed_instance_factory(instance):
    def factory():
        copied = dict(instance)
        copied["initial_state"] = instance["initial_state"].deepcopy()
        return copied

    return factory
