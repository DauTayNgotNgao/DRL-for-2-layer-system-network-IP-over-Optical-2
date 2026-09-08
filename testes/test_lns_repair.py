import math

from src_hung.algorithms.lns_repair import CrossLayerLNSRepair
from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.main import initialize_state_multilayer
from src_hung.model.demand import generate_random_demands
from src_hung.model.network import generate_multilayer_topology
from src_hung.objective.cost_func import CostCalculator


def test_lns_repair_keeps_feasibility_and_improves_initial_state():
    seed = 5042
    physical_net, ip_graph, ip_to_opt_map = generate_multilayer_topology(
        opt_nodes=10,
        opt_links=14,
        ip_nodes=6,
        ip_links=8,
        num_slots=70,
        lightpath_capacity=80,
        seed=42,
    )
    demands = generate_random_demands(
        num_demands=5,
        num_ip_nodes=6,
        bw_min=20,
        bw_max=100,
        seed=seed,
    )
    initial_state = initialize_state_multilayer(
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        demands=demands,
        lightpath_capacity=80,
        num_slots=70,
        k_shortest=10,
        seed=seed,
    )
    calc = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=80,
        num_slots=70,
        rho_limit=35,
    )

    initial_cost = calc.calculate_objective(initial_state)
    optimizer = CrossLayerLNSRepair(
        initial_state=initial_state,
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=physical_net.graph,
        ip_to_opt_map=ip_to_opt_map,
        cost_calculator=calc,
        spectrum_allocator=SpectrumAllocator(num_slots=70),
        lightpath_capacity=80,
        max_ip_paths=10,
        max_optical_paths=10,
        max_destroy_candidates=10,
        repack_trials=8,
        seed=seed,
    )

    best_state = optimizer.run(max_iterations=40)
    best_cost, details = calc.calculate_objective(best_state, return_details=True)

    assert math.isfinite(best_cost)
    assert details["feasible"] is True
    assert best_cost <= initial_cost
