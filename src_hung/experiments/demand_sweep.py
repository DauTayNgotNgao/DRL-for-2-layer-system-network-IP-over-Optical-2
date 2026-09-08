"""
Demand sweep cho bài toán tối ưu đa lớp.

Mục tiêu:
- Giữ cố định topology IP + optical + mapping.
- Tăng dần số lượng demand.
- Với mỗi mức demand, so sánh:
    1) Initial Allocation
    2) SA Cross-layer Optimized
- Sinh CSV và 3 hình trong thư mục results/.

Chạy từ thư mục gốc project:
    python -m src_hung.experiments.demand_sweep
"""

from __future__ import annotations

import argparse
import copy
import csv
import random
import time
from pathlib import Path
from collections import Counter
from statistics import mean

from src_hung.algorithms.SA import CrossLayerSA
from src_hung.algorithms.lns_repair import CrossLayerLNSRepair
from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.main import DEFAULT_CONFIG, initialize_state_multilayer, load_config
from src_hung.model.demand import generate_random_demands
from src_hung.model.network import generate_multilayer_topology
from src_hung.objective.cost_func import CostCalculator
from src_hung.visualization.plot_results import (
    plot_added_removed_lightpaths,
    plot_improvement_percent,
    plot_initial_vs_optimized_demand_sweep,
    plot_network_load,
)

OUTPUT_DIR = Path("results")
DEFAULT_DEMAND_POINTS = [2, 4, 6, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50]


def build_cost_calculator(config, demands, ip_graph, opt_graph, ip_to_opt_map):
    net_cfg = config["network"]
    obj_cfg = config["objective"]
    sa_cfg = config["sa"]

    return CostCalculator(
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        weight_energy=obj_cfg["weight_energy"],
        weight_latency=obj_cfg["weight_latency"],
        p_transponder=obj_cfg["p_transponder"],
        rho_limit=sa_cfg.get("rho_limit"),
        penalty_flow=obj_cfg["penalty_flow"],
        penalty_capacity=obj_cfg["penalty_capacity"],
        penalty_spectrum=obj_cfg["penalty_spectrum"],
        penalty_lightpath_consistency=obj_cfg["penalty_lightpath_consistency"],
        penalty_non_disruptive=obj_cfg["penalty_non_disruptive"],
    )


def format_path(path) -> str:
    """Đổi list node thành chuỗi 1 -> 2 -> 3."""
    if not path:
        return "N/A"
    return " -> ".join(str(x) for x in path)


def lightpath_signature(lp) -> tuple:
    """
    Signature dùng để so sánh lightpath giữa initial state và best state.

    Không dùng lp.id vì id chỉ là mã nội bộ trong từng state. Nếu cùng IP link,
    cùng optical route, cùng slot block thì coi là cùng một lightpath logic.
    """
    return (
        tuple(lp.ip_link),
        tuple(lp.opt_path),
        int(lp.slot_start),
        int(lp.slots),
    )


def count_added_removed_lightpaths(initial_state, best_state) -> tuple[int, int]:
    """
    Đếm số lightpath được thêm/xóa bằng cách so sánh best state với initial state.

    Added  = lightpath có trong best nhưng không có trong initial.
    Removed = lightpath có trong initial nhưng không có trong best.
    Dùng Counter để xử lý trường hợp có nhiều lightpath trùng signature.
    """
    initial_counter = Counter(
        lightpath_signature(lp) for lp in initial_state.lightpath_info.values()
    )
    best_counter = Counter(
        lightpath_signature(lp) for lp in best_state.lightpath_info.values()
    )

    added = sum((best_counter - initial_counter).values())
    removed = sum((initial_counter - best_counter).values())
    return added, removed


def compute_spectrum_usage(state, opt_graph, num_slots: int) -> dict:
    """
    Tính network load theo đúng mô hình slot trong code.

    used_slots = tổng số slot đang bị chiếm trên tất cả directed optical edges.
    total_slots = số directed optical edges * num_slots.

    Lưu ý: PhysicalNetwork.add_link() tạo hai cung u->v và v->u, nên opt_graph
    là directed graph. Vì lightpath trong state cũng đi theo directed edge, mẫu số
    phải dùng opt_graph.number_of_edges() để cùng logic đếm với used_slots.
    """
    occupied_by_edge: dict[tuple[int, int], set[int]] = {
        edge: set() for edge in opt_graph.edges()
    }

    for lp in state.lightpath_info.values():
        start = int(lp.slot_start)
        end = start + int(lp.slots)
        for edge in lp.opt_edges:
            occupied_by_edge.setdefault(edge, set()).update(range(start, end))

    used_slots = sum(len(slots) for slots in occupied_by_edge.values())
    total_slots = opt_graph.number_of_edges() * int(num_slots)
    network_load = used_slots / total_slots if total_slots > 0 else 0.0

    return {
        "used_slots": used_slots,
        "total_slots": total_slots,
        "network_load": network_load,
    }


def reconstruct_demand_ip_path(state, demand) -> list[int] | None:
    """
    Khôi phục đường đi IP của một demand từ biến state.x.

    state.x lưu theo dạng x[(demand_id, u_ip, v_ip)] = 1.
    Hàm này biến các cạnh rời rạc đó thành path dạng node:
        [source, ..., target]
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


def summarize_lightpaths_for_ip_link(state, ip_link: tuple[int, int]) -> str:
    """
    Tóm tắt các lightpath đang hỗ trợ một IP link.

    Ví dụ output:
        LP#0: 5 -> 1 -> 8 -> 4 -> 0 [slot=0-0]; LP#1: ...
    """
    lightpaths = sorted(
        [lp for lp in state.lightpath_info.values() if lp.ip_link == ip_link],
        key=lambda lp: lp.id,
    )

    if not lightpaths:
        return "NO_LIGHTPATH"

    parts = []
    for lp in lightpaths:
        slot_end = lp.slot_start + lp.slots - 1
        parts.append(
            f"LP#{lp.id}: {format_path(lp.opt_path)} "
            f"[slot={lp.slot_start}-{slot_end}, slots={lp.slots}]"
        )

    return "; ".join(parts)


def collect_demand_path_rows(
    *,
    state_name: str,
    state,
    demands,
    ip_to_opt_map: dict[int, int],
    num_demands: int,
    seed: int,
) -> list[dict]:
    """
    Tạo các dòng CSV mô tả path của từng demand trong INITIAL hoặc BEST state.

    Mỗi dòng tương ứng một demand ở một state:
    - state_name: initial hoặc best
    - IP source/target
    - Optical source/target tương ứng
    - IP route thực tế của demand
    - Optical mapped route: ánh xạ từng IP node trong IP route xuống optical node
    - Lightpaths: các đường quang thật đang đỡ từng IP link trong route
    """
    rows = []

    for demand in demands:
        ip_path = reconstruct_demand_ip_path(state, demand)

        if ip_path is None:
            optical_mapped_path = None
            ip_link_details = "INVALID_OR_NOT_FOUND"
        else:
            optical_mapped_path = [ip_to_opt_map.get(ip_node, "?") for ip_node in ip_path]

            link_parts = []
            for i in range(len(ip_path) - 1):
                u_ip = ip_path[i]
                v_ip = ip_path[i + 1]
                u_opt = ip_to_opt_map.get(u_ip, "?")
                v_opt = ip_to_opt_map.get(v_ip, "?")
                lightpaths = summarize_lightpaths_for_ip_link(state, (u_ip, v_ip))
                link_parts.append(
                    f"IP {u_ip}->{v_ip} maps OPT {u_opt}->{v_opt}: {lightpaths}"
                )

            ip_link_details = " | ".join(link_parts)

        rows.append(
            {
                "num_demands": num_demands,
                "seed": seed,
                "state": state_name,
                "demand_id": demand.id,
                "bandwidth": demand.bandwidth,
                "ip_source": demand.s,
                "ip_target": demand.t,
                "optical_source": ip_to_opt_map.get(demand.s, "?"),
                "optical_target": ip_to_opt_map.get(demand.t, "?"),
                "ip_path": format_path(ip_path),
                "optical_mapped_path": format_path(optical_mapped_path),
                "ip_link_lightpaths": ip_link_details,
            }
        )

    return rows


def run_one_case(
    config,
    physical_net,
    ip_graph,
    ip_to_opt_map,
    num_demands: int,
    seed: int,
    include_lns: bool = True,
    lns_iterations: int = 80,
    lns_max_destroy_candidates: int = 10,
    lns_repack_trials: int = 8,
) -> tuple[dict, list[dict]]:
    """Chạy một kịch bản với số demand và seed cụ thể."""
    net_cfg = config["network"]
    demand_cfg = config["demands"]
    sa_cfg = config["sa"]
    init_cfg = config.get("initialization", {})
    opt_graph = physical_net.graph

    demands = generate_random_demands(
        num_demands=num_demands,
        num_ip_nodes=net_cfg["ip_nodes"],
        bw_min=demand_cfg["bw_min"],
        bw_max=demand_cfg["bw_max"],
        seed=seed,
    )
    total_bandwidth = sum(d.bandwidth for d in demands)

    case_start_time = time.perf_counter()

    init_start_time = time.perf_counter()
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
    initial_runtime_sec = time.perf_counter() - init_start_time

    cost_calculator = build_cost_calculator(
        config=config,
        demands=demands,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
    )

    initial_cost, initial_details = cost_calculator.calculate_objective(
        initial_state,
        return_details=True,
    )

    spectrum_allocator = SpectrumAllocator(num_slots=net_cfg["num_slots"], guardband=0)

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

    sa_start_time = time.perf_counter()
    best_state = optimizer.run()
    sa_runtime_sec = time.perf_counter() - sa_start_time
    best_cost, best_details = cost_calculator.calculate_objective(best_state, return_details=True)

    lns_state = None
    lns_cost = None
    lns_details = None
    lns_stats = None
    lns_runtime_sec = None
    if include_lns:
        lns_optimizer = CrossLayerLNSRepair(
            initial_state=initial_state,
            demands=demands,
            ip_graph=ip_graph,
            opt_graph=opt_graph,
            ip_to_opt_map=ip_to_opt_map,
            cost_calculator=cost_calculator,
            spectrum_allocator=spectrum_allocator,
            lightpath_capacity=net_cfg["lightpath_capacity"],
            max_ip_paths=init_cfg.get("k_shortest", 10),
            max_optical_paths=init_cfg.get("k_shortest", 10),
            max_destroy_candidates=lns_max_destroy_candidates,
            repack_trials=lns_repack_trials,
            seed=seed,
        )
        lns_start_time = time.perf_counter()
        lns_state = lns_optimizer.run(max_iterations=lns_iterations)
        lns_runtime_sec = time.perf_counter() - lns_start_time
        lns_cost, lns_details = cost_calculator.calculate_objective(
            lns_state,
            return_details=True,
        )
        lns_stats = lns_optimizer.stats

    total_runtime_sec = time.perf_counter() - case_start_time
    lns_speedup_vs_sa = (
        sa_runtime_sec / lns_runtime_sec
        if lns_runtime_sec is not None and lns_runtime_sec > 0 else None
    )

    initial_normalized_cost = initial_cost / total_bandwidth if total_bandwidth > 0 else 0.0
    normalized_cost = best_cost / total_bandwidth if total_bandwidth > 0 else 0.0
    improvement_percent = ((initial_cost - best_cost) / initial_cost * 100) if initial_cost else 0.0
    lns_normalized_cost = (
        lns_cost / total_bandwidth
        if lns_cost is not None and total_bandwidth > 0 else None
    )
    lns_improvement_percent = (
        ((initial_cost - lns_cost) / initial_cost * 100)
        if lns_cost is not None and initial_cost else None
    )
    lns_gap_vs_sa = (lns_cost - best_cost) if lns_cost is not None else None

    added_lightpaths, removed_lightpaths = count_added_removed_lightpaths(
        initial_state,
        best_state,
    )
    initial_spectrum = compute_spectrum_usage(
        initial_state,
        opt_graph=opt_graph,
        num_slots=net_cfg["num_slots"],
    )
    best_spectrum = compute_spectrum_usage(
        best_state,
        opt_graph=opt_graph,
        num_slots=net_cfg["num_slots"],
    )

    result_row = {
        "num_demands": num_demands,
        "seed": seed,
        "k_shortest_initialization": init_cfg.get("k_shortest", 10),
        "total_bandwidth": total_bandwidth,
        "initial_cost": initial_cost,
        "best_cost": best_cost,
        "lns_cost": lns_cost,
        "lns_improvement_percent": lns_improvement_percent,
        "lns_gap_vs_sa": lns_gap_vs_sa,
        "initial_runtime_sec": initial_runtime_sec,
        "sa_runtime_sec": sa_runtime_sec,
        "lns_runtime_sec": lns_runtime_sec,
        "total_runtime_sec": total_runtime_sec,
        "lns_speedup_vs_sa": lns_speedup_vs_sa,
        "initial_normalized_cost": initial_normalized_cost,
        "normalized_cost": normalized_cost,
        "lns_normalized_cost": lns_normalized_cost,
        "improvement_percent": improvement_percent,
        "initial_energy_cost": initial_details["energy_cost"],
        "best_energy_cost": best_details["energy_cost"],
        "lns_energy_cost": lns_details["energy_cost"] if lns_details else None,
        "initial_lightpaths": initial_details["lightpaths"],
        "best_lightpaths": best_details["lightpaths"],
        "lns_lightpaths": lns_details["lightpaths"] if lns_details else None,
        "initial_constraint_violations": initial_details["constraint_violations"],
        "best_constraint_violations": best_details["constraint_violations"],
        "lns_constraint_violations": lns_details["constraint_violations"] if lns_details else None,
        "reconfiguration_distance": best_details["reconfiguration_distance"],
        "lns_reconfiguration_distance": lns_details["reconfiguration_distance"] if lns_details else None,
        "rho_limit": sa_cfg.get("rho_limit"),
        "added_lightpaths": added_lightpaths,
        "removed_lightpaths": removed_lightpaths,
        "total_lightpath_changes": added_lightpaths + removed_lightpaths,
        "lns_iterations": lns_stats.iterations if lns_stats else 0,
        "lns_candidate_moves": lns_stats.candidate_moves if lns_stats else 0,
        "lns_accepted_moves": lns_stats.accepted_moves if lns_stats else 0,
        "lns_pruned_lightpaths": lns_stats.pruned_lightpaths if lns_stats else 0,
        "initial_used_slots": initial_spectrum["used_slots"],
        "best_used_slots": best_spectrum["used_slots"],
        "total_slots": initial_spectrum["total_slots"],
        "initial_network_load": initial_spectrum["network_load"],
        "best_network_load": best_spectrum["network_load"],
        "network_load_reduction_percent": (
            (initial_spectrum["network_load"] - best_spectrum["network_load"])
            / initial_spectrum["network_load"]
            * 100
        ) if initial_spectrum["network_load"] else 0.0,
        "mbb_attempts": optimizer.stats.get("mbb_attempts", 0),
        "mbb_success": optimizer.stats.get("mbb_success", 0),
        "feasible": 1 if best_details["feasible"] else 0,
        "lns_feasible": 1 if lns_details and lns_details["feasible"] else None,
    }

    demand_path_rows = []
    demand_path_rows.extend(
        collect_demand_path_rows(
            state_name="initial",
            state=initial_state,
            demands=demands,
            ip_to_opt_map=ip_to_opt_map,
            num_demands=num_demands,
            seed=seed,
        )
    )
    demand_path_rows.extend(
        collect_demand_path_rows(
            state_name="best",
            state=best_state,
            demands=demands,
            ip_to_opt_map=ip_to_opt_map,
            num_demands=num_demands,
            seed=seed,
        )
    )
    if lns_state is not None:
        demand_path_rows.extend(
            collect_demand_path_rows(
                state_name="lns",
                state=lns_state,
                demands=demands,
                ip_to_opt_map=ip_to_opt_map,
                num_demands=num_demands,
                seed=seed,
            )
        )

    return result_row, demand_path_rows


def aggregate_results(rows: list[dict]) -> list[dict]:
    """Lấy trung bình theo từng mức num_demands."""
    demand_values = sorted(set(row["num_demands"] for row in rows))
    aggregated = []

    for n in demand_values:
        group = [row for row in rows if row["num_demands"] == n]
        aggregated.append(
            {
                "num_demands": n,
                "k_shortest_initialization": mean(row["k_shortest_initialization"] for row in group),
                "total_bandwidth": mean(row["total_bandwidth"] for row in group),
                "initial_cost": mean(row["initial_cost"] for row in group),
                "best_cost": mean(row["best_cost"] for row in group),
                "lns_cost": (
                    mean(r["lns_cost"] for r in group if r["lns_cost"] is not None)
                    if any(r["lns_cost"] is not None for r in group) else None
                ),
                "lns_improvement_percent": (
                    mean(r["lns_improvement_percent"] for r in group if r["lns_improvement_percent"] is not None)
                    if any(r["lns_improvement_percent"] is not None for r in group) else None
                ),
                "lns_gap_vs_sa": (
                    mean(r["lns_gap_vs_sa"] for r in group if r["lns_gap_vs_sa"] is not None)
                    if any(r["lns_gap_vs_sa"] is not None for r in group) else None
                ),
                "initial_runtime_sec": mean(row["initial_runtime_sec"] for row in group),
                "sa_runtime_sec": mean(row["sa_runtime_sec"] for row in group),
                "lns_runtime_sec": (
                    mean(r["lns_runtime_sec"] for r in group if r["lns_runtime_sec"] is not None)
                    if any(r["lns_runtime_sec"] is not None for r in group) else None
                ),
                "total_runtime_sec": mean(row["total_runtime_sec"] for row in group),
                "lns_speedup_vs_sa": (
                    mean(r["lns_speedup_vs_sa"] for r in group if r["lns_speedup_vs_sa"] is not None)
                    if any(r["lns_speedup_vs_sa"] is not None for r in group) else None
                ),
                "initial_normalized_cost": mean(row["initial_normalized_cost"] for row in group),
                "normalized_cost": mean(row["normalized_cost"] for row in group),
                "lns_normalized_cost": (
                    mean(r["lns_normalized_cost"] for r in group if r["lns_normalized_cost"] is not None)
                    if any(r["lns_normalized_cost"] is not None for r in group) else None
                ),
                "improvement_percent": mean(row["improvement_percent"] for row in group),
                "initial_energy_cost": mean(row["initial_energy_cost"] for row in group),
                "best_energy_cost": mean(row["best_energy_cost"] for row in group),
                "lns_energy_cost": (
                    mean(r["lns_energy_cost"] for r in group if r["lns_energy_cost"] is not None)
                    if any(r["lns_energy_cost"] is not None for r in group) else None
                ),
                "initial_lightpaths": mean(row["initial_lightpaths"] for row in group),
                "best_lightpaths": mean(row["best_lightpaths"] for row in group),
                "lns_lightpaths": (
                    mean(r["lns_lightpaths"] for r in group if r["lns_lightpaths"] is not None)
                    if any(r["lns_lightpaths"] is not None for r in group) else None
                ),
                "initial_constraint_violations": mean(row["initial_constraint_violations"] for row in group),
                "best_constraint_violations": mean(row["best_constraint_violations"] for row in group),
                "lns_constraint_violations": (
                    mean(r["lns_constraint_violations"] for r in group if r["lns_constraint_violations"] is not None)
                    if any(r["lns_constraint_violations"] is not None for r in group) else None
                ),
                "reconfiguration_distance": mean(row["reconfiguration_distance"] for row in group),
                "lns_reconfiguration_distance": (
                    mean(r["lns_reconfiguration_distance"] for r in group if r["lns_reconfiguration_distance"] is not None)
                    if any(r["lns_reconfiguration_distance"] is not None for r in group) else None
                ),
                "rho_limit": mean(row["rho_limit"] for row in group),
                "added_lightpaths": mean(row["added_lightpaths"] for row in group),
                "removed_lightpaths": mean(row["removed_lightpaths"] for row in group),
                "total_lightpath_changes": mean(row["total_lightpath_changes"] for row in group),
                "lns_iterations": mean(row["lns_iterations"] for row in group),
                "lns_candidate_moves": mean(row["lns_candidate_moves"] for row in group),
                "lns_accepted_moves": mean(row["lns_accepted_moves"] for row in group),
                "lns_pruned_lightpaths": mean(row["lns_pruned_lightpaths"] for row in group),
                "initial_used_slots": mean(row["initial_used_slots"] for row in group),
                "best_used_slots": mean(row["best_used_slots"] for row in group),
                "total_slots": mean(row["total_slots"] for row in group),
                "initial_network_load": mean(row["initial_network_load"] for row in group),
                "best_network_load": mean(row["best_network_load"] for row in group),
                "network_load_reduction_percent": mean(row["network_load_reduction_percent"] for row in group),
                "mbb_attempts": mean(row["mbb_attempts"] for row in group),
                "mbb_success": mean(row["mbb_success"] for row in group),
                "feasible_rate": mean(row["feasible"] for row in group),
                "lns_feasible_rate": (
                    mean(r["lns_feasible"] for r in group if r["lns_feasible"] is not None)
                    if any(r["lns_feasible"] is not None for r in group) else None
                ),
            }
        )

    return aggregated


def save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[+] Đã lưu CSV: {path}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        default="config/default.yaml",
        help="Đường dẫn file config. Nếu không tồn tại thì dùng DEFAULT_CONFIG.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Số lần chạy lặp lại cho mỗi mức demand.",
    )
    parser.add_argument(
        "--demand-points",
        type=str,
        default=",".join(str(x) for x in DEFAULT_DEMAND_POINTS),
        help="Danh sách số demand, ví dụ: 5,10,20,30,40,50",
    )
    parser.add_argument(
        "--k-shortest",
        type=int,
        default=None,
        help=(
            "Ghi đè số candidate shortest paths dùng khi khởi tạo nghiệm ban đầu. "
            "Ví dụ --k-shortest 10 nghĩa là IP route và optical route đều chọn ngẫu nhiên từ 10 shortest paths."
        ),
    )
    parser.add_argument(
        "--no-lns",
        action="store_true",
        default=False,
        help="Tắt so sánh LNS-Repair, chỉ chạy Initial và SA.",
    )
    parser.add_argument(
        "--lns-iterations",
        type=int,
        default=80,
        help="Số vòng cải thiện tối đa của LNS-Repair.",
    )
    parser.add_argument(
        "--lns-destroy-candidates",
        type=int,
        default=10,
        help="Số demand có score cao nhất được thử trong mỗi vòng LNS.",
    )
    parser.add_argument(
        "--lns-repack-trials",
        type=int,
        default=8,
        help="Số thứ tự repack nhiều demand được thử trong mỗi vòng LNS.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = copy.deepcopy(load_config(args.config))
    include_lns = not args.no_lns

    if args.k_shortest is not None:
        config.setdefault("initialization", {})["k_shortest"] = args.k_shortest

    seed = config["random_seed"]
    net_cfg = config["network"]
    init_cfg = config.get("initialization", {})
    k_shortest = init_cfg.get("k_shortest", 10)

    demand_points = [int(x.strip()) for x in args.demand_points.split(",") if x.strip()]
    repetitions = max(1, args.repetitions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"[+] Khởi tạo nghiệm ban đầu: mỗi IP route và optical route "
        f"được chọn ngẫu nhiên từ tối đa {k_shortest} shortest paths."
    )
    print("[+] Sinh topology cố định cho toàn bộ thí nghiệm...")
    physical_net, ip_graph, ip_to_opt_map = generate_multilayer_topology(
        opt_nodes=net_cfg["opt_nodes"],
        opt_links=net_cfg["opt_links"],
        ip_nodes=net_cfg["ip_nodes"],
        ip_links=net_cfg["ip_links"],
        num_slots=net_cfg["num_slots"],
        lightpath_capacity=net_cfg["lightpath_capacity"],
        seed=seed,
    )

    raw_rows = []
    demand_path_rows = []

    if include_lns:
        print(
            f"[+] Chế độ LNS-Repair: iterations={args.lns_iterations}, "
            f"destroy_candidates={args.lns_destroy_candidates}, "
            f"repack_trials={args.lns_repack_trials}."
        )

    for num_demands in demand_points:
        print(f"\n[+] Đang chạy num_demands = {num_demands}")
        for rep in range(repetitions):
            case_seed = seed + 1000 * num_demands + rep
            row, case_path_rows = run_one_case(
                config=config,
                physical_net=physical_net,
                ip_graph=ip_graph,
                ip_to_opt_map=ip_to_opt_map,
                num_demands=num_demands,
                seed=case_seed,
                include_lns=include_lns,
                lns_iterations=args.lns_iterations,
                lns_max_destroy_candidates=args.lns_destroy_candidates,
                lns_repack_trials=args.lns_repack_trials,
            )
            raw_rows.append(row)
            demand_path_rows.extend(case_path_rows)
            lns_info = ""
            if row["lns_cost"] is not None:
                lns_info = (
                    f", lns={row['lns_cost']}, "
                    f"lns_improve={row['lns_improvement_percent']:.2f}%, "
                    f"lns_gap_vs_sa={row['lns_gap_vs_sa']:.2f}, "
                    f"lns_moves={row['lns_accepted_moves']}, "
                    f"lns_time={row['lns_runtime_sec']:.3f}s, "
                    f"speedup={row['lns_speedup_vs_sa']:.1f}x"
                )
            print(
                f"    seed={case_seed}, "
                f"initial={row['initial_cost']:.2f}, "
                f"sa={row['best_cost']:.2f}"
                f"{lns_info}, "
                f"sa_time={row['sa_runtime_sec']:.3f}s, "
                f"improve={row['improvement_percent']:.2f}%, "
                f"feasible={row['feasible']}"
            )

    aggregated = aggregate_results(raw_rows)

    raw_csv = OUTPUT_DIR / "multilayer_demand_sweep_raw.csv"
    summary_csv = OUTPUT_DIR / "multilayer_demand_sweep_summary.csv"
    save_csv(raw_csv, raw_rows)
    save_csv(summary_csv, aggregated)

    # Lưu thêm tên cũ để các script trước của bạn vẫn đọc được.
    save_csv(OUTPUT_DIR / "demand_sweep_raw.csv", raw_rows)
    save_csv(OUTPUT_DIR / "demand_sweep_summary.csv", aggregated)

    # File này là phần bổ sung: path của từng demand trong initial và best state.
    save_csv(OUTPUT_DIR / "05_demand_paths_raw.csv", demand_path_rows)

    # Hình 1: Initial vs SA vs LNS, cộng PPO inference nếu đã chạy training/.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_vals  = [r["num_demands"] for r in aggregated]
    y_init  = [r["initial_cost"] for r in aggregated]
    y_sa    = [r["best_cost"]    for r in aggregated]
    y_lns   = [r["lns_cost"]     for r in aggregated]
    has_lns = any(v is not None for v in y_lns)

    ppo_by_demand = {}
    ppo_label = "PPO Inference"
    ppo_candidates = [
        (Path("training/results_milp/ppo_milp_fast_top32.csv"), "Fast MILP-Teacher PPO"),
        (Path("training/results_milp/ppo_milp_inference.csv"), "MILP-Teacher PPO"),
        (Path("training/results/ppo_inference.csv"), "PPO Inference"),
    ]
    ppo_csv = next((path for path, _ in ppo_candidates if path.exists()), None)
    if ppo_csv is not None:
        ppo_label = next(label for path, label in ppo_candidates if path == ppo_csv)
        with open(ppo_csv, "r", newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                ppo_by_demand[int(float(row["num_demands"]))] = float(row["ppo_cost"])
    has_ppo = any(value in ppo_by_demand for value in x_vals)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(x_vals, y_init, "o--", label="Initial Allocation",  color="steelblue")
    ax.plot(x_vals, y_sa,   "s-",  label="SA Optimized",        color="tomato")
    if has_lns:
        y_lns_clean = [v if v is not None else float("nan") for v in y_lns]
        ax.plot(x_vals, y_lns_clean, "^-", label="LNS-Repair", color="seagreen")
    if has_ppo:
        y_ppo = [ppo_by_demand.get(value, float("nan")) for value in x_vals]
        ax.plot(x_vals, y_ppo, "D-", label=ppo_label, color="mediumpurple")
    ax.set_xlabel("Number of Demands")
    ax.set_ylabel("Number of Lightpaths")
    ax.set_title("Initial vs SA vs LNS vs PPO Inference" if has_ppo else "Initial vs SA vs LNS")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    out1 = OUTPUT_DIR / "01_initial_vs_sa_vs_rl.png"
    fig.savefig(out1, dpi=150)
    if has_ppo:
        fig.savefig(OUTPUT_DIR / "01_initial_vs_sa_vs_lns_vs_ppo.png", dpi=150)
    plt.close(fig)
    print(f"[+] Đã lưu hình: {out1}")

    # Hình 2: normalized cost
    plot_initial_vs_optimized_demand_sweep(
        results=aggregated,
        output_path=OUTPUT_DIR / "02_initial_vs_sa_normalized_cost.png",
        title="Multi-layer Topology: Normalized Cost",
        initial_metric="initial_normalized_cost",
        optimized_metric="normalized_cost",
        ylabel="Normalized Cost",
        optimized_label="SA Optimized Normalized Cost",
    )

    # Hình 3: phần trăm cải thiện SA
    plot_improvement_percent(
        results=aggregated,
        output_path=OUTPUT_DIR / "03_improvement_percent.png",
        title="SA Lightpath Reduction over Initial Allocation",
    )

    if has_lns:
        y_sa_improve = [r["improvement_percent"] for r in aggregated]
        y_lns_improve = [
            r["lns_improvement_percent"] if r["lns_improvement_percent"] is not None else float("nan")
            for r in aggregated
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(x_vals, y_sa_improve, "s-", label="SA improvement", color="tomato")
        ax.plot(x_vals, y_lns_improve, "^-", label="LNS improvement", color="seagreen")
        ax.set_xlabel("Number of Demands")
        ax.set_ylabel("Improvement over Initial (%)")
        ax.set_title("SA vs LNS Improvement")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()
        out_improve = OUTPUT_DIR / "04_sa_vs_rl_improvement_percent.png"
        fig.savefig(out_improve, dpi=150)
        plt.close(fig)
        print(f"[+] Đã lưu hình: {out_improve}")

        y_lns_gap = [
            r["lns_gap_vs_sa"] if r["lns_gap_vs_sa"] is not None else float("nan")
            for r in aggregated
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.axhline(0, color="black", linewidth=1.0, linestyle="--", alpha=0.8)
        ax.plot(x_vals, y_lns_gap, "o-", label="LNS cost - SA cost", color="seagreen")
        ax.fill_between(x_vals, y_lns_gap, 0, where=[v <= 0 for v in y_lns_gap], color="seagreen", alpha=0.18)
        ax.set_xlabel("Number of Demands")
        ax.set_ylabel("Lightpath Gap vs SA")
        ax.set_title("LNS Gap vs SA")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()
        out_gap = OUTPUT_DIR / "04_rl_gap_vs_sa.png"
        fig.savefig(out_gap, dpi=150)
        plt.close(fig)
        print(f"[+] Đã lưu hình: {out_gap}")

        y_sa_runtime = [r["sa_runtime_sec"] for r in aggregated]
        y_lns_runtime = [
            r["lns_runtime_sec"] if r["lns_runtime_sec"] is not None else float("nan")
            for r in aggregated
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(x_vals, y_sa_runtime, "s-", label="SA runtime", color="tomato")
        ax.plot(x_vals, y_lns_runtime, "^-", label="LNS runtime", color="seagreen")
        ax.set_xlabel("Number of Demands")
        ax.set_ylabel("Runtime (seconds)")
        ax.set_title("SA vs LNS Runtime")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()
        out_runtime = OUTPUT_DIR / "07_sa_vs_rl_runtime.png"
        fig.savefig(out_runtime, dpi=150)
        plt.close(fig)
        print(f"[+] Đã lưu hình: {out_runtime}")

        y_speedup = [
            r["lns_speedup_vs_sa"] if r["lns_speedup_vs_sa"] is not None else float("nan")
            for r in aggregated
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(x_vals, y_speedup, "o-", label="SA runtime / LNS runtime", color="seagreen")
        ax.axhline(1, color="black", linewidth=1.0, linestyle="--", alpha=0.8)
        ax.set_xlabel("Number of Demands")
        ax.set_ylabel("Speedup (x)")
        ax.set_title("LNS Speedup over SA")
        ax.legend()
        ax.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()
        out_speedup = OUTPUT_DIR / "07_rl_speedup_vs_sa.png"
        fig.savefig(out_speedup, dpi=150)
        plt.close(fig)
        print(f"[+] Đã lưu hình: {out_speedup}")

    # Hình 5: added/removed
    plot_added_removed_lightpaths(
        results=aggregated,
        output_path=OUTPUT_DIR / "05_added_removed_lightpaths.png",
        title="Total Added and Removed Lightpaths",
    )

    # Hình 6: network load
    plot_network_load(
        results=aggregated,
        output_path=OUTPUT_DIR / "06_network_load.png",
        title="Network Load Before and After Optimization",
    )

    print("\n[+] Hoàn thành demand sweep.")
    print(f"[+] File CSV chính: {summary_csv}")
    print("[+] Hình chính:")
    print("    results/01_initial_vs_sa_vs_rl.png")
    print("    results/02_initial_vs_sa_normalized_cost.png")
    print("    results/03_improvement_percent.png")
    if include_lns:
        print("    results/04_sa_vs_rl_improvement_percent.png")
        print("    results/04_rl_gap_vs_sa.png")
        print("    results/07_sa_vs_rl_runtime.png")
        print("    results/07_rl_speedup_vs_sa.png")
    print("    results/05_added_removed_lightpaths.png")
    print("    results/06_network_load.png")
    print("[+] File path của từng demand:")
    print("    results/05_demand_paths_raw.csv")


if __name__ == "__main__":
    main()
