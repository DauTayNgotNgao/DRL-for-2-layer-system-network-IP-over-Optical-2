"""
Rho sweep cho bài toán tối ưu đa lớp.

Mục tiêu:
- Giữ cố định topology và traffic generation rule.
- Thay đổi rho_limit để xem reconfiguration budget ảnh hưởng thế nào tới improvement.
- Sinh CSV và hình:
    results/rho_sweep_raw.csv
    results/rho_sweep_summary.csv
    results/07_rho_impact_improvement.png

Chạy từ thư mục gốc project:
    python -m src_hung.experiments.rho_sweep

Ví dụ:
    python -m src_hung.experiments.rho_sweep --num-demands 20,40,60,80 --rho-values 0,2,4,6,8,10,15,20 --repetitions 3
"""

from __future__ import annotations

import argparse
import copy
import csv
from pathlib import Path
from statistics import mean

from src_hung.experiments.demand_sweep import run_one_case, save_csv
from src_hung.main import load_config
from src_hung.model.network import generate_multilayer_topology
from src_hung.visualization.plot_results import plot_rho_impact

OUTPUT_DIR = Path("results")
DEFAULT_RHO_VALUES = [0, 2, 4, 6, 8, 10, 12, 15, 20]
DEFAULT_DEMAND_LEVELS = [20, 40, 60, 80]


def parse_int_list(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def aggregate_by_demand_and_rho(rows: list[dict]) -> list[dict]:
    """Lấy trung bình kết quả theo từng cặp (num_demands, rho_limit)."""
    if not rows:
        return []

    keys = sorted(set((row["num_demands"], row["rho_limit"]) for row in rows))
    aggregated = []

    # Chỉ aggregate các cột số quan trọng để CSV gọn và dễ vẽ.
    numeric_columns = [
        "total_bandwidth",
        "initial_cost",
        "best_cost",
        "initial_normalized_cost",
        "normalized_cost",
        "improvement_percent",
        "initial_energy_cost",
        "best_energy_cost",
        "initial_lightpaths",
        "best_lightpaths",
        "added_lightpaths",
        "removed_lightpaths",
        "total_lightpath_changes",
        "initial_used_slots",
        "best_used_slots",
        "total_slots",
        "initial_network_load",
        "best_network_load",
        "network_load_reduction_percent",
        "reconfiguration_distance",
        "mbb_attempts",
        "mbb_success",
        "feasible",
    ]

    for num_demands, rho_limit in keys:
        group = [
            row for row in rows
            if row["num_demands"] == num_demands and row["rho_limit"] == rho_limit
        ]
        out = {
            "num_demands": num_demands,
            "rho_limit": rho_limit,
            "repetitions": len(group),
        }
        for col in numeric_columns:
            if col in group[0]:
                out[col if col != "feasible" else "feasible_rate"] = mean(row[col] for row in group)
        aggregated.append(out)

    return aggregated


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        default="config/default.yaml",
        help="Đường dẫn file config. Nếu không tồn tại thì dùng DEFAULT_CONFIG.",
    )
    parser.add_argument(
        "--num-demands",
        type=str,
        default=",".join(str(x) for x in DEFAULT_DEMAND_LEVELS),
        help="Các mức demand cố định để sweep rho, ví dụ: 20,40,60,80",
    )
    parser.add_argument(
        "--rho-values",
        type=str,
        default=",".join(str(x) for x in DEFAULT_RHO_VALUES),
        help="Danh sách rho_limit, ví dụ: 0,2,4,6,8,10,15,20",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Số lần chạy lặp lại cho mỗi cặp demand/rho.",
    )
    parser.add_argument(
        "--k-shortest",
        type=int,
        default=None,
        help="Ghi đè số candidate shortest paths khi khởi tạo nghiệm ban đầu.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_config = copy.deepcopy(load_config(args.config))

    if args.k_shortest is not None:
        base_config.setdefault("initialization", {})["k_shortest"] = args.k_shortest

    seed = base_config["random_seed"]
    net_cfg = base_config["network"]
    demand_levels = parse_int_list(args.num_demands)
    rho_values = parse_int_list(args.rho_values)
    repetitions = max(1, args.repetitions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[+] Sinh topology cố định cho toàn bộ rho sweep...")
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

    for num_demands in demand_levels:
        for rho_limit in rho_values:
            print(f"\n[+] Đang chạy num_demands={num_demands}, rho_limit={rho_limit}")
            for rep in range(repetitions):
                config = copy.deepcopy(base_config)
                config.setdefault("sa", {})["rho_limit"] = rho_limit

                case_seed = seed + 100000 * num_demands + 1000 * rho_limit + rep
                row, _ = run_one_case(
                    config=config,
                    physical_net=physical_net,
                    ip_graph=ip_graph,
                    ip_to_opt_map=ip_to_opt_map,
                    num_demands=num_demands,
                    seed=case_seed,
                )
                raw_rows.append(row)
                print(
                    f"    seed={case_seed}, "
                    f"initial={row['initial_cost']:.2f}, "
                    f"best={row['best_cost']:.2f}, "
                    f"improve={row['improvement_percent']:.2f}%, "
                    f"add={row['added_lightpaths']}, "
                    f"remove={row['removed_lightpaths']}, "
                    f"load={row['best_network_load'] * 100:.2f}%, "
                    f"feasible={row['feasible']}"
                )

    summary_rows = aggregate_by_demand_and_rho(raw_rows)

    raw_csv = OUTPUT_DIR / "rho_sweep_raw.csv"
    summary_csv = OUTPUT_DIR / "rho_sweep_summary.csv"
    save_csv(raw_csv, raw_rows)
    save_csv(summary_csv, summary_rows)

    plot_rho_impact(
        results=summary_rows,
        output_path=OUTPUT_DIR / "07_rho_impact_improvement.png",
        title="Impact of Rho on Improvement",
    )

    print("\n[+] Hoàn thành rho sweep.")
    print(f"[+] File CSV chính: {summary_csv}")
    print("[+] Hình chính:")
    print("    results/07_rho_impact_improvement.png")


if __name__ == "__main__":
    main()