from __future__ import annotations

import copy
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HYPERGIANT_SRC = Path(__file__).resolve().parent / "hypergiant_isp" / "src"


def ensure_import_paths() -> None:
    for path in (PROJECT_ROOT, HYPERGIANT_SRC):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def build_input_instance_from_generated_data(
    physical_net,
    ip_graph,
    ip_to_opt_map: dict[int, int],
    demands,
    *,
    lightpath_capacity: float,
    num_slots: int,
    topology_name: str = "generated_cross_layer_topology",
    ip_candidate_mode: str = "generated",
    ip_link_utilization: float | None = None,
    num_transceivers: int | None = None,
    optical_candidate_k: int = 10,
    initial_state=None,
    rho_limit: int | None = None,
):
    """Convert this project's generated topology/demands into Hypergiant MILP input.

    The Hypergiant MILP logic is intentionally left untouched. This adapter only
    creates the model objects expected by that solver.
    """
    ensure_import_paths()

    import constants as hg_constants
    import model.demand as hg_demand
    import model.input as hg_input
    import model.topology as hg_topology

    if ip_candidate_mode not in {"complete", "generated"}:
        raise ValueError("ip_candidate_mode must be 'complete' or 'generated'.")

    parameter = {
        hg_constants.KEY_IP_LIGHTPATH_CAPACITY: float(lightpath_capacity),
    }
    if ip_link_utilization is not None:
        parameter[hg_constants.KEY_IP_LINK_UTILIZATION] = float(ip_link_utilization)

    topology = hg_topology.Topology(name=topology_name, parameter=parameter)

    opt_nodes = {}
    for opt_id in sorted(physical_net.graph.nodes()):
        node = hg_topology.OpticalNode(nid=_optical_id(opt_id))
        topology.add_node(node)
        opt_nodes[opt_id] = node

    transceivers = int(num_transceivers if num_transceivers is not None else num_slots)
    ip_nodes = {}
    for ip_id in sorted(ip_to_opt_map):
        parent = opt_nodes[ip_to_opt_map[ip_id]]
        node = hg_topology.IPNode(
            nid=_ip_id(ip_id),
            parent=parent,
            num_transceiver=transceivers,
        )
        topology.add_node(node)
        ip_nodes[ip_id] = node

    added_undirected_edges: set[tuple[int, int]] = set()
    for u, v, data in physical_net.graph.edges(data=True):
        edge_key = tuple(sorted((u, v)))
        if edge_key in added_undirected_edges:
            continue
        added_undirected_edges.add(edge_key)
        length = float(data.get("weight", 1.0))
        fiber_capacity = int(data.get("slots", num_slots))
        topology.add_edge(
            hg_topology.OpticalLink(opt_nodes[u], opt_nodes[v], capacity=fiber_capacity),
            weight=length,
        )
        topology.add_edge(
            hg_topology.OpticalLink(opt_nodes[v], opt_nodes[u], capacity=fiber_capacity),
            weight=length,
        )

    background_demand = hg_demand.DemandMatrix()
    for demand in demands:
        src = ip_nodes[demand.s]
        dst = ip_nodes[demand.t]
        key = (demand.id, str(src), str(dst))
        background_demand[key] = hg_demand.EndToEndDemand(
            src,
            dst,
            volume=float(demand.bandwidth),
        )

    fixed_layers = {}

    input_instance = hg_input.InputInstance(
        topology=topology,
        demandset=hg_demand.DemandSet(),
        background_demand=background_demand,
        fixed_layers=fixed_layers,
    )

    input_instance.num_slots = int(num_slots)
    input_instance.optical_candidate_k = int(optical_candidate_k)
    input_instance.allowed_ip_edges = None
    if ip_candidate_mode == "generated":
        input_instance.allowed_ip_edges = [
            (_ip_id(u), _ip_id(v))
            for u, v in sorted(ip_graph.edges())
            if u != v
        ]
    input_instance.rho_limit = rho_limit
    input_instance.baseline_lightpaths = (
        _serialize_baseline_lightpaths(initial_state)
        if initial_state is not None
        else None
    )

    metadata = {
        "topology_name": topology_name,
        "ip_candidate_mode": ip_candidate_mode,
        "constraint_profile": "sa_compatible",
        "num_transceivers_per_ip_node": transceivers,
        "ip_link_utilization": ip_link_utilization,
        "rho_limit": rho_limit,
        "optical_candidate_k": optical_candidate_k,
        "ip_to_opt_map": {str(k): v for k, v in sorted(ip_to_opt_map.items())},
        "generated_ip_edges": [[u, v] for u, v in sorted(ip_graph.edges())],
        "physical_edges": _serialize_physical_edges(physical_net),
        "demands": [
            {
                "id": demand.id,
                "source": demand.s,
                "target": demand.t,
                "bandwidth": float(demand.bandwidth),
            }
            for demand in demands
        ],
        "milp_demands": [
            {
                "key": list(key),
                "id": key[0],
                "source": _from_ip_id(dem.node1.id),
                "target": _from_ip_id(dem.node2.id),
                "bandwidth": float(dem.volume),
            }
            for key, dem in background_demand.items()
        ],
        "baseline_lightpaths": input_instance.baseline_lightpaths,
    }

    return input_instance, metadata


def solve_input_instance(
    input_instance,
    *,
    solver: str = "cplex",
    threads: int | None = 1,
    time_limit: int | None = None,
    export_lp: str | None = None,
    enable_output: bool = False,
):
    if solver.lower() != "cplex":
        raise ValueError("Only native IBM CPLEX is supported by this runner.")

    from MILP.cplex_native_milp import NativeCplexPathMixedIntegerProgram

    model = NativeCplexPathMixedIntegerProgram(
        inputinstance=input_instance,
        num_threads=threads,
        time_limit=time_limit,
        enable_output=enable_output,
    )
    model.build()
    if export_lp is not None:
        model.write(export_lp)
    model.solve()
    return model, model.get_solution_dict(), model.status_name


def solution_to_teacher_labels(solution_dict: dict[str, Any]) -> dict[str, Any]:
    ip_links = []
    for link in solution_dict.get("ip_links", []):
        optical_hops_by_path = defaultdict(list)
        for opt_link in link.get("opt_links", []):
            opt_u, opt_v, trunks, path_num = opt_link[:4]
            slot_start = opt_link[4] if len(opt_link) > 4 else None
            optical_hops_by_path[int(path_num)].append(
                {
                    "source": _from_optical_id(opt_u),
                    "target": _from_optical_id(opt_v),
                    "trunks": float(trunks),
                    "slot_start": slot_start,
                }
            )
        ip_links.append(
            {
                "source": _from_ip_id(link["node1"]),
                "target": _from_ip_id(link["node2"]),
                "num_trunks": float(link["num_trunks"]),
                "optical_paths": [
                    {"path_id": path_id, "hops": hops}
                    for path_id, hops in sorted(optical_hops_by_path.items())
                ],
            }
        )

    demand_routes = []
    for routed in solution_dict.get("e2e_routing", []):
        demand_routes.append(
            {
                "demand_id": routed.get("demand_id"),
                "source": _from_ip_id(routed["node1"]),
                "target": _from_ip_id(routed["node2"]),
                "ip_hops": [
                    {
                        "source": _from_ip_id(edge[0][0]),
                        "target": _from_ip_id(edge[0][1]),
                        "bandwidth": float(edge[1]),
                    }
                    for edge in routed.get("paths", [])
                ],
            }
        )

    return {
        "ip_links": ip_links,
        "lightpaths": solution_dict.get("lightpaths", []),
        "demand_routes": demand_routes,
    }


def state_from_solution_dict(solution_dict: dict[str, Any], demands, initial_state=None):
    from src_hung.model.lightpath import Lightpath
    from src_hung.model.state import MultiLayerState

    state = MultiLayerState(demands=demands)

    for routed in solution_dict.get("e2e_routing", []):
        demand_id = routed.get("demand_id")
        if demand_id is None:
            continue
        for edge, _volume in routed.get("paths", []):
            u_ip = _from_ip_id(edge[0])
            v_ip = _from_ip_id(edge[1])
            state.x[(demand_id, u_ip, v_ip)] = 1

    for lp_data in solution_dict.get("lightpaths", []):
        lp = Lightpath(
            id=int(lp_data["id"]),
            ip_link=tuple(lp_data["ip_link"]),
            opt_path=list(lp_data["opt_path"]),
            slot_start=int(lp_data["slot_start"]),
            slots=int(lp_data.get("slots", 1)),
            path_id=int(lp_data["path_id"]),
        )
        state.add_lightpath(lp)

    if initial_state is not None:
        state.y0 = copy.deepcopy(initial_state.y0)
        state.q0 = copy.deepcopy(initial_state.q0)
    else:
        state.set_baseline_y0()

    return state


def make_jsonable(value):
    if isinstance(value, dict):
        return {str(k): make_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_jsonable(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return copy.deepcopy(value)


def _ip_id(ip_id: int) -> str:
    return f"IP-{ip_id}"


def _optical_id(opt_id: int) -> str:
    return f"O-{opt_id}"


def _from_ip_id(value: str) -> int:
    return int(str(value).replace("IP-", ""))


def _from_optical_id(value: str) -> int:
    return int(str(value).replace("O-", ""))


def _serialize_physical_edges(physical_net) -> list[dict[str, Any]]:
    edges = []
    seen = set()
    for u, v, data in physical_net.graph.edges(data=True):
        edge_key = tuple(sorted((u, v)))
        if edge_key in seen:
            continue
        seen.add(edge_key)
        edges.append(
            {
                "source": u,
                "target": v,
                "length": float(data.get("weight", 1.0)),
                "fiber_capacity_slots": int(data.get("slots", physical_net.num_slots)),
            }
        )
    return sorted(edges, key=lambda e: (e["source"], e["target"]))


def _serialize_baseline_lightpaths(initial_state) -> list[dict[str, Any]]:
    return [
        {
            "id": int(lp.id),
            "ip_link": [int(lp.ip_link[0]), int(lp.ip_link[1])],
            "opt_path": [int(node) for node in lp.opt_path],
            "slot_start": int(lp.slot_start),
            "slots": int(lp.slots),
            "path_id": int(lp.path_id),
        }
        for lp in initial_state.lightpath_info.values()
    ]
