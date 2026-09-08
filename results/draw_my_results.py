r"""
Vẽ lại các hình từ file CSV kết quả thí nghiệm.

Cách chạy:
    cd F:\Cross-Layer-Optimization_Tung_HUST\results
    python draw_my_results.py

Script này đọc:
    - multilayer_demand_sweep_summary.csv hoặc demand_sweep_summary.csv
    - rho_sweep_summary.csv nếu đã chạy rho sweep
"""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parent

DEMAND_CANDIDATES = [
    BASE_DIR / "multilayer_demand_sweep_summary.csv",
    BASE_DIR / "demand_sweep_summary.csv",
    BASE_DIR / "multilayer_default_summary.csv",
]
RHO_CANDIDATES = [
    BASE_DIR / "rho_sweep_summary.csv",
]


def load_first_existing(candidates):
    return next((p for p in candidates if p.exists()), None)


def save_current_figure(filename: str):
    plt.tight_layout()
    plt.savefig(BASE_DIR / filename, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[+] Đã lưu: {filename}")


def require_columns(df, columns, figure_name: str) -> bool:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        print(f"[!] Bỏ qua {figure_name}: CSV thiếu cột {missing}.")
        return False
    return True


def plot_demand_figures(df: pd.DataFrame):
    required = ["num_demands", "initial_cost", "best_cost", "normalized_cost"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"CSV thiếu các cột cần thiết: {missing}.\n"
            "Hãy chạy lại từ thư mục gốc project:\n"
            "    python -m src_hung.experiments.demand_sweep"
        )

    if "initial_normalized_cost" not in df.columns:
        if "total_bandwidth" in df.columns:
            df["initial_normalized_cost"] = df["initial_cost"] / df["total_bandwidth"]
        else:
            df["initial_normalized_cost"] = 0.0

    if "improvement_percent" not in df.columns:
        df["improvement_percent"] = (
            (df["initial_cost"] - df["best_cost"]) / df["initial_cost"] * 100
        )

    # Hình 1: Initial vs SA optimized total cost
    plt.figure(figsize=(11, 6))
    plt.plot(df["num_demands"], df["initial_cost"], marker="o", linestyle="--", linewidth=2, label="Initial Allocation")
    plt.plot(df["num_demands"], df["best_cost"], marker="s", linestyle="-", linewidth=2, label="SA Energy Optimized")
    plt.xlabel("Number of Demands")
    plt.ylabel("Number of Lightpaths")
    plt.title("Multi-layer Topology: Initial Allocation vs SA Optimized", fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    save_current_figure("01_initial_vs_sa_total_cost.png")

    # Hình 2: Normalized cost
    plt.figure(figsize=(11, 6))
    plt.plot(df["num_demands"], df["initial_normalized_cost"], marker="o", linestyle="--", linewidth=2, label="Initial Normalized Cost")
    plt.plot(df["num_demands"], df["normalized_cost"], marker="s", linestyle="-", linewidth=2, label="SA Optimized Normalized Cost")
    plt.xlabel("Number of Demands")
    plt.ylabel("Normalized Lightpaths")
    plt.title("Multi-layer Topology: Normalized Lightpaths per Bandwidth", fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    save_current_figure("02_initial_vs_sa_normalized_cost.png")

    # Hình 3: Improvement percentage
    plt.figure(figsize=(11, 6))
    plt.plot(df["num_demands"], df["improvement_percent"], marker="s", linestyle="-", linewidth=2, label="Improvement")
    plt.xlabel("Number of Demands")
    plt.ylabel("Improvement (%)")
    plt.title("SA Improvement over Initial Allocation", fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    save_current_figure("03_improvement_percent.png")

    # Hình 5: Added / removed lightpaths
    if require_columns(df, ["num_demands", "added_lightpaths", "removed_lightpaths"], "05_added_removed_lightpaths.png"):
        plt.figure(figsize=(11, 6))
        plt.plot(df["num_demands"], df["added_lightpaths"], marker="o", linestyle="-", linewidth=2, label="Added lightpaths")
        plt.plot(df["num_demands"], df["removed_lightpaths"], marker="s", linestyle="--", linewidth=2, label="Removed lightpaths")
        plt.xlabel("Number of Demands")
        plt.ylabel("Number of Lightpaths")
        plt.title("Total Added and Removed Lightpaths", fontweight="bold")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.legend()
        save_current_figure("05_added_removed_lightpaths.png")

    # Hình 6: Network load = used slots / total slots
    if require_columns(df, ["num_demands", "initial_network_load", "best_network_load"], "06_network_load.png"):
        plt.figure(figsize=(11, 6))
        plt.plot(df["num_demands"], df["initial_network_load"] * 100, marker="o", linestyle="--", linewidth=2, label="Initial load")
        plt.plot(df["num_demands"], df["best_network_load"] * 100, marker="s", linestyle="-", linewidth=2, label="Optimized load")
        plt.xlabel("Number of Demands")
        plt.ylabel("Network Load (%)")
        plt.title("Network Load Before and After Optimization", fontweight="bold")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.legend()
        save_current_figure("06_network_load.png")


def plot_rho_figures(df: pd.DataFrame):
    if not require_columns(df, ["num_demands", "rho_limit", "improvement_percent"], "07_rho_impact_improvement.png"):
        return

    plt.figure(figsize=(11, 6))
    for num_demands in sorted(df["num_demands"].unique()):
        group = df[df["num_demands"] == num_demands].sort_values("rho_limit")
        plt.plot(group["rho_limit"], group["improvement_percent"], marker="o", linewidth=2, label=f"{num_demands} demands")

    plt.xlabel("Rho limit")
    plt.ylabel("Improvement (%)")
    plt.title("Impact of Rho on Improvement", fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    save_current_figure("07_rho_impact_improvement.png")


def main():
    demand_csv = load_first_existing(DEMAND_CANDIDATES)
    if demand_csv is None:
        names = "\n".join(f"  - {p.name}" for p in DEMAND_CANDIDATES)
        raise FileNotFoundError(
            "Không tìm thấy file demand summary CSV trong thư mục results.\n"
            "Bạn hãy chạy từ thư mục gốc project trước:\n"
            "    python -m src_hung.experiments.demand_sweep\n\n"
            f"Các tên file được hỗ trợ:\n{names}"
        )

    print(f"[+] Đang đọc demand CSV: {demand_csv}")
    demand_df = pd.read_csv(demand_csv)
    plot_demand_figures(demand_df)

    rho_csv = load_first_existing(RHO_CANDIDATES)
    if rho_csv is None:
        print("[!] Chưa có rho_sweep_summary.csv, bỏ qua hình 07_rho_impact_improvement.png.")
        print("    Để tạo hình này, chạy: python -m src_hung.experiments.rho_sweep")
    else:
        print(f"[+] Đang đọc rho CSV: {rho_csv}")
        rho_df = pd.read_csv(rho_csv)
        plot_rho_figures(rho_df)


if __name__ == "__main__":
    main()
