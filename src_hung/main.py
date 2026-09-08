import math
import csv
import random
from pathlib import Path

import networkx as nx
import matplotlib.pyplot as plt

from src_hung.algorithms.routing import RoutingEngine
from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.algorithms.SA import CrossLayerSA
from src_hung.model.demand import generate_random_demands
from src_hung.model.lightpath import Lightpath
from src_hung.model.network import generate_multilayer_topology
from src_hung.model.state import MultiLayerState
from src_hung.objective.cost_func import CostCalculator
from src_hung.visualization.plot_results import (
    plot_sa_history,
)


DEFAULT_CONFIG = {
    "random_seed": 42,
    "network": {
        "opt_nodes": 10,
        "opt_links": 14,
        "ip_nodes": 6,
        "ip_links": 8,
        "num_slots": 100,
        "lightpath_capacity": 80,
    },
    "demands": {
        "num_demands": 8,
        "bw_min": 10,
        "bw_max": 100,
    },
    "initialization": {
        # Nghiệm ban đầu lấy ngẫu nhiên từ tập k shortest paths.
        # k_shortest = 10 nghĩa là:
        #   - IP route của mỗi demand chọn ngẫu nhiên trong 10 shortest IP paths.
        #   - Optical route của mỗi lightpath chọn ngẫu nhiên trong 10 shortest optical paths.
        "k_shortest": 10,
    },
    "objective": {
        # Objective mới: minimize số lightpaths.
        # p_transponder chỉ dùng để report energy_cost = p_transponder * lightpaths.
        "weight_energy": 1.0,
        "weight_latency": 0.0,
        "p_transponder": 1,
        # Các penalty cũ giữ lại để tương thích config, không còn dùng trong objective.
        "penalty_flow": 0,
        "penalty_capacity": 0,
        "penalty_spectrum": 0,
        "penalty_lightpath_consistency": 0,
        "penalty_non_disruptive": 0,
    },
    "sa": {
        "T_max": 1000.0,
        "T_min": 1.0,
        "cooling_rate": 0.95,
        "iterations_per_temperature": 80,
        "rho_limit": 10,
    },
}

SWEEP_MODE = True
DEMAND_POINTS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90]
SWEEP_REPETITIONS = 1
PRINT_FLOW_REPORT_IN_SWEEP = False

def load_config(path: str = "config/default.yaml") -> dict:
    config_path = Path(path)

    if not config_path.exists():
        print("[!] Không thấy config/default.yaml, dùng DEFAULT_CONFIG.")
        return DEFAULT_CONFIG

    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)

        return merge_dict(DEFAULT_CONFIG, loaded)

    except Exception as exc:
        print(f"[!] Lỗi đọc config: {exc}. Dùng DEFAULT_CONFIG.")
        return DEFAULT_CONFIG


def merge_dict(base: dict, override: dict | None) -> dict:
    if override is None:
        return base

    result = dict(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value

    return result


def initialize_state_multilayer(
    ip_graph,
    opt_graph,
    ip_to_opt_map,
    demands,
    lightpath_capacity: float,
    num_slots: int,
    k_shortest: int = 10,
    seed: int | None = None,
) -> MultiLayerState:
    """
    Khởi tạo nghiệm ban đầu theo đúng hướng ATC/SA:

    1. Với mỗi demand, chọn ngẫu nhiên 1 IP path trong tập k shortest IP paths.
    2. Tính load trên từng IP link sau khi đã route demand.
    3. Với mỗi IP link đang có traffic, tạo đủ số lightpath cần thiết.
    4. Với mỗi lightpath, chọn ngẫu nhiên optical path trong tập k shortest
       optical paths tương ứng, sau đó gán spectrum bằng first-fit.

    Với k_shortest = 10, cả IP route và optical route đều được lấy ngẫu nhiên
    từ tập 10 shortest paths tương ứng.
    """
    state = MultiLayerState(demands=demands)
    rng = random.Random(seed)

    routing_engine = RoutingEngine(ip_graph)
    for demand in demands:
        ip_path = routing_engine.random_path(
            demand=demand,
            max_candidates=k_shortest,
            seed=rng.randint(0, 10**9),
        )
        if ip_path is not None:
            routing_engine.apply_path(state, demand, ip_path)

    traffic_on_ip_link = compute_traffic_on_ip_link(state, demands)

    spectrum_allocator = SpectrumAllocator(num_slots=num_slots, guardband=0)

    for ip_link, load in traffic_on_ip_link.items():
        required_lightpaths = max(1, math.ceil(load / lightpath_capacity))

        for _ in range(required_lightpaths):
            ok = add_lightpath_for_ip_link(
                state=state,
                ip_link=ip_link,
                opt_graph=opt_graph,
                ip_to_opt_map=ip_to_opt_map,
                spectrum_allocator=spectrum_allocator,
                max_candidates=k_shortest,
                rng=rng,
            )

            if not ok:
                print(f"[!] Không tạo được lightpath cho IP link {ip_link}")

    state.set_baseline_y0()
    return state


def compute_traffic_on_ip_link(state, demands):
    demand_by_id = {d.id: d for d in demands}
    traffic = {}

    for (d_id, u, v), val in state.x.items():
        if val != 1:
            continue

        if d_id not in demand_by_id:
            continue

        traffic[(u, v)] = traffic.get((u, v), 0.0) + demand_by_id[d_id].bandwidth

    return traffic


def candidate_optical_paths(
    opt_graph,
    source: int,
    target: int,
    max_candidates: int = 10,
) -> list[list[int]]:
    """Lấy tối đa max_candidates shortest simple optical paths."""
    try:
        generator = nx.shortest_simple_paths(
            opt_graph,
            source=source,
            target=target,
            weight="weight",
        )
        paths: list[list[int]] = []
        for _, path in zip(range(max_candidates), generator):
            paths.append(path)
        return paths
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def add_lightpath_for_ip_link(
    state: MultiLayerState,
    ip_link: tuple[int, int],
    opt_graph,
    ip_to_opt_map,
    spectrum_allocator: SpectrumAllocator,
    max_candidates: int = 10,
    rng: random.Random | None = None,
) -> bool:
    """
    Tạo một lightpath cho IP link.

    Optical path không còn cố định là shortest path duy nhất. Thay vào đó,
    hàm lấy tối đa max_candidates shortest optical paths, xáo trộn thứ tự,
    rồi thử gán spectrum theo first-fit. Path đầu tiên có spectrum khả dụng
    sẽ được chọn.
    """
    rng = rng or random.Random()
    u_ip, v_ip = ip_link

    if u_ip not in ip_to_opt_map or v_ip not in ip_to_opt_map:
        return False

    u_opt = ip_to_opt_map[u_ip]
    v_opt = ip_to_opt_map[v_ip]
    candidates = candidate_optical_paths(
        opt_graph=opt_graph,
        source=u_opt,
        target=v_opt,
        max_candidates=max_candidates,
    )

    indexed_candidates = list(enumerate(candidates))
    rng.shuffle(indexed_candidates)

    for path_id, opt_path in indexed_candidates:
        opt_edges = [
            (opt_path[i], opt_path[i + 1])
            for i in range(len(opt_path) - 1)
        ]

        ok, slot = spectrum_allocator.find_available_slot(
            state=state,
            path_edges=opt_edges,
            required_slots=1,
        )

        if not ok:
            continue

        lp = Lightpath(
            id=state.next_lightpath_id,
            ip_link=ip_link,
            opt_path=opt_path,
            slot_start=slot,
            slots=1,
            path_id=path_id,
        )

        state.add_lightpath(lp)
        return True

    return False


def print_cost(title, cost, details):
    cost_text = "INF / infeasible" if cost == float("inf") else f"{cost:.2f}"
    print(f"\n===== {title} =====")
    print(f"Objective = #lightpaths : {cost_text}")
    print(f"Feasible                : {details['feasible']}")
    print(f"Lightpaths              : {details['lightpaths']}")
    print(f"Energy report           : {details['energy_cost']:.2f}")
    print(f"Constraint violations   : {details['constraint_violations']}")
    print(f"  - flow                : {details['flow_violations']}")
    print(f"  - capacity links      : {details['capacity_violations']}")
    print(f"  - excess bandwidth    : {details['capacity_excess_bandwidth']:.2f}")
    print(f"  - mapping             : {details['mapping_violations']}")
    print(f"  - z consistency       : {details['z_consistency_violations']}")
    print(f"  - spectrum            : {details['spectrum_violations']}")
    print(f"  - y consistency       : {details['y_consistency_violations']}")
    print(f"  - non-disruptive      : {details['non_disruptive_violations']}")
    print(f"Reconfig distance |Δy|  : {details['reconfiguration_distance']} / {details['rho_limit']}")

def reconstruct_demand_ip_path(
    state: MultiLayerState,
    demand,
) -> list[int] | None:
    """
    Khôi phục đường đi IP dạng node path từ biến x của state.

    Ví dụ state.x có:
        x[("d0", 1, 3)] = 1
        x[("d0", 3, 5)] = 1
    thì hàm trả về:
        [1, 3, 5]
    """
    edges = state.get_demand_edges(demand.id)
    if not edges:
        return None

    outgoing: dict[int, list[int]] = {}
    for u, v in edges:
        outgoing.setdefault(u, []).append(v)

    path = [demand.s]
    current = demand.s
    visited_edges = set()

    for _ in range(len(edges) + 1):
        if current == demand.t:
            return path

        next_nodes = outgoing.get(current, [])
        if len(next_nodes) != 1:
            return None

        nxt = next_nodes[0]
        edge = (current, nxt)
        if edge in visited_edges:
            return None

        visited_edges.add(edge)
        path.append(nxt)
        current = nxt

    return None


def format_node_path(path: list[int] | None) -> str:
    if not path:
        return "N/A"
    return " -> ".join(str(node) for node in path)


def get_lightpaths_for_ip_link(
    state: MultiLayerState,
    ip_link: tuple[int, int],
) -> list[Lightpath]:
    return sorted(
        [lp for lp in state.lightpath_info.values() if lp.ip_link == ip_link],
        key=lambda lp: lp.id,
    )


def build_demand_flow_report(
    title: str,
    state: MultiLayerState,
    demands,
    ip_to_opt_map: dict[int, int],
    lightpath_capacity: float,
) -> str:
    """
    Tạo report cho biết mỗi demand đi từ IP nào sang IP nào,
    ánh xạ xuống optical node nào, route IP đang dùng và các lightpath quang
    hỗ trợ từng IP link trên route đó.
    """
    lines: list[str] = []
    traffic_on_ip_link = compute_traffic_on_ip_link(state, demands)

    lines.append(f"\n===== {title} DEMAND FLOW REPORT =====")
    lines.append("Chú thích:")
    lines.append("  - IP route: đường đi của demand trên tầng IP.")
    lines.append("  - Optical mapped route: ánh xạ từng IP node trong route xuống optical node.")
    lines.append("  - Lightpath: đường quang thật đang hỗ trợ từng IP link.")

    for demand in demands:
        src_opt = ip_to_opt_map.get(demand.s, "?")
        dst_opt = ip_to_opt_map.get(demand.t, "?")
        ip_path = reconstruct_demand_ip_path(state, demand)

        lines.append("")
        lines.append(
            f"[{demand.id}] bw={demand.bandwidth} | "
            f"IP {demand.s} -> {demand.t} | "
            f"Optical {src_opt} -> {dst_opt}"
        )

        if ip_path is None:
            raw_edges = state.get_demand_edges(demand.id)
            lines.append("  IP route           : INVALID / NOT FOUND")
            lines.append(f"  Raw x edges         : {raw_edges}")
            continue

        optical_mapped_path = [ip_to_opt_map.get(ip_node, "?") for ip_node in ip_path]
        lines.append(f"  IP route           : {format_node_path(ip_path)}")
        lines.append(f"  Optical mapped route: {format_node_path(optical_mapped_path)}")

        for i in range(len(ip_path) - 1):
            u_ip = ip_path[i]
            v_ip = ip_path[i + 1]
            ip_link = (u_ip, v_ip)
            u_opt = ip_to_opt_map.get(u_ip, "?")
            v_opt = ip_to_opt_map.get(v_ip, "?")
            load = traffic_on_ip_link.get(ip_link, 0.0)
            lightpaths = get_lightpaths_for_ip_link(state, ip_link)
            installed_capacity = len(lightpaths) * lightpath_capacity

            lines.append(
                f"    IP link {u_ip}->{v_ip} maps Optical {u_opt}->{v_opt} | "
                f"load={load:.2f}, installed_capacity={installed_capacity:.2f}, "
                f"lightpaths={len(lightpaths)}"
            )

            if not lightpaths:
                lines.append("      - No lightpath allocated for this IP link")
                continue

            for lp in lightpaths:
                slot_end = lp.slot_start + lp.slots - 1
                lines.append(
                    f"      - LP#{lp.id}: opt_path={format_node_path(lp.opt_path)}, "
                    f"slot={lp.slot_start}-{slot_end}, slots={lp.slots}, path_id={lp.path_id}"
                )

    return "\n".join(lines)


def print_demand_flow_report(
    title: str,
    state: MultiLayerState,
    demands,
    ip_to_opt_map: dict[int, int],
    lightpath_capacity: float,
    output_path: str | None = None,
) -> None:
    report = build_demand_flow_report(
        title=title,
        state=state,
        demands=demands,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=lightpath_capacity,
    )
    print(report)

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report + "\n", encoding="utf-8")
        print(f"[+] Đã lưu demand flow report: {path}")



def main():
    config = load_config()

    seed = config["random_seed"]

    net_cfg = config["network"]
    demand_cfg = config["demands"]
    obj_cfg = config["objective"]
    sa_cfg = config["sa"]
    init_cfg = config["initialization"]

    print("--- CROSS-LAYER OPTIMIZATION WITH SIMULATED ANNEALING ---")

    physical_net, ip_graph, ip_to_opt_map = generate_multilayer_topology(
        opt_nodes=net_cfg["opt_nodes"],
        opt_links=net_cfg["opt_links"],
        ip_nodes=net_cfg["ip_nodes"],
        ip_links=net_cfg["ip_links"],
        num_slots=net_cfg["num_slots"],
        lightpath_capacity=net_cfg["lightpath_capacity"],
        seed=seed,
    )

    opt_graph = physical_net.graph

    demands = generate_random_demands(
        num_demands=demand_cfg["num_demands"],
        num_ip_nodes=net_cfg["ip_nodes"],
        bw_min=demand_cfg["bw_min"],
        bw_max=demand_cfg["bw_max"],
        seed=seed,
    )

    print("\n[+] Demands:")
    for d in demands:
        print(f"    {d.id}: {d.s} -> {d.t}, bw = {d.bandwidth}")

    initial_state = initialize_state_multilayer(
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        demands=demands,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        k_shortest=init_cfg.get("k_shortest", 10),
        seed=seed,
    )

    cost_calculator = CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        weight_energy=obj_cfg["weight_energy"],
        weight_latency=obj_cfg["weight_latency"],
        p_transponder=obj_cfg["p_transponder"],
        rho_limit=sa_cfg["rho_limit"],
        penalty_flow=obj_cfg["penalty_flow"],
        penalty_capacity=obj_cfg["penalty_capacity"],
        penalty_spectrum=obj_cfg["penalty_spectrum"],
        penalty_lightpath_consistency=obj_cfg["penalty_lightpath_consistency"],
        penalty_non_disruptive=obj_cfg["penalty_non_disruptive"],
    )

    init_cost, init_details = cost_calculator.calculate_objective(
        initial_state,
        return_details=True,
    )
    print_cost("INITIAL STATE", init_cost, init_details)

    print_demand_flow_report(
        title="INITIAL STATE",
        state=initial_state,
        demands=demands,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        output_path="results/initial_demand_flow.txt",
    )

    spectrum_allocator = SpectrumAllocator(
        num_slots=net_cfg["num_slots"],
        guardband=0,
    )

    optimizer = CrossLayerSA(
        initial_state=initial_state,
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        cost_calculator=cost_calculator,
        spectrum_allocator=spectrum_allocator,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        T_max=sa_cfg["T_max"],
        T_min=sa_cfg["T_min"],
        cooling_rate=sa_cfg["cooling_rate"],
        iterations_per_temperature=sa_cfg["iterations_per_temperature"],
        seed=seed,
    )

    print("\n[+] Đang chạy Simulated Annealing...")

    best_state = optimizer.run()

    best_cost, best_details = cost_calculator.calculate_objective(
        best_state,
        return_details=True,
    )
    print_cost("BEST STATE", best_cost, best_details)
    print_demand_flow_report(
        title="BEST STATE",
        state=best_state,
        demands=demands,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        output_path="results/best_demand_flow.txt",
    )

    plot_sa_history(
        optimizer.history,
        output_path="results/sa_history.png",
        title="SA optimization history",
    )

    print("\n[+] SA stats:")
    for key, value in optimizer.stats.items():
        print(f"    {key}: {value}")

    print("\n[+] Hoàn thành.")

if __name__ == "__main__":
    main()