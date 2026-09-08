import networkx as nx

from src_hung.model.demand import Demand
from src_hung.model.state import MultiLayerState
from src_hung.model.lightpath import Lightpath
from src_hung.objective.cost_func import CostCalculator


def test_simple_feasible_state():
    ip_graph = nx.DiGraph()
    ip_graph.add_edge(0, 1, weight=10)

    opt_graph = nx.DiGraph()
    opt_graph.add_edge(0, 1, weight=10)

    mapping = {0: 0, 1: 1}

    demands = [
        Demand(id="d0", s=0, t=1, bandwidth=50),
    ]

    state = MultiLayerState(demands=demands)
    state.set_demand_path("d0", [0, 1])

    lp = Lightpath(
        id=0,
        ip_link=(0, 1),
        opt_path=[0, 1],
        slot_start=0,
        slots=1,
        path_id=0,
    )
    state.add_lightpath(lp)
    state.set_baseline_y0()

    calc = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=mapping,
        lightpath_capacity=80,
        num_slots=100,
        rho_limit=10,
    )

    cost, details = calc.calculate_objective(state, return_details=True)

    assert cost > 0
    assert details["feasible"] is True
    assert details["penalty"] == 0


def test_capacity_violation():
    ip_graph = nx.DiGraph()
    ip_graph.add_edge(0, 1, weight=10)

    opt_graph = nx.DiGraph()
    opt_graph.add_edge(0, 1, weight=10)

    mapping = {0: 0, 1: 1}

    demands = [
        Demand(id="d0", s=0, t=1, bandwidth=200),
    ]

    state = MultiLayerState(demands=demands)
    state.set_demand_path("d0", [0, 1])

    lp = Lightpath(
        id=0,
        ip_link=(0, 1),
        opt_path=[0, 1],
        slot_start=0,
        slots=1,
        path_id=0,
    )
    state.add_lightpath(lp)
    state.set_baseline_y0()

    calc = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=mapping,
        lightpath_capacity=80,
        num_slots=100,
        rho_limit=10,
    )

    _, details = calc.calculate_objective(state, return_details=True)

    assert details["feasible"] is False
    assert details["capacity_violations"] > 0
    assert details["capacity_excess_bandwidth"] > 0
