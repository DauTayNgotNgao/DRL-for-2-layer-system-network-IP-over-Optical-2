from pathlib import Path

import matplotlib.pyplot as plt


def _ensure_parent_dir(output_path):
    if output_path is None:
        return
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)


def plot_sa_history(history, output_path=None, title="Simulated Annealing Cost History"):
    """Vẽ lịch sử cost tốt nhất theo từng bước nhiệt độ của SA."""
    if not history:
        print("Không có history để vẽ.")
        return

    plt.figure(figsize=(10, 5))
    plt.plot(range(len(history)), history, marker="o", linewidth=2)
    plt.xlabel("Temperature step")
    plt.ylabel("Best cost")
    plt.title(title)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_cost_breakdown(
    labels,
    details_list,
    output_path=None,
    title="Cost breakdown before and after optimization",
):
    """Vẽ biểu đồ cột chồng so sánh Energy / Delay / Penalty."""
    if not labels or not details_list or len(labels) != len(details_list):
        raise ValueError("labels và details_list phải có cùng số phần tử.")

    energy = [d.get("energy_cost", 0.0) for d in details_list]
    delay = [d.get("delay_cost", 0.0) for d in details_list]
    penalty = [d.get("penalty", 0.0) for d in details_list]
    x = list(range(len(labels)))

    plt.figure(figsize=(8, 5))
    plt.bar(x, energy, label="Energy")
    plt.bar(x, delay, bottom=energy, label="Delay")
    bottom_penalty = [energy[i] + delay[i] for i in range(len(labels))]
    plt.bar(x, penalty, bottom=bottom_penalty, label="Penalty")

    plt.xticks(x, labels)
    plt.ylabel("Cost component value")
    plt.title(title)
    plt.legend()
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_demand_sweep(results, output_path=None, metric="normalized_cost", title=None):
    """Vẽ một metric theo số lượng demand."""
    if not results:
        print("Không có kết quả demand sweep để vẽ.")
        return

    x = [row["num_demands"] for row in results]
    y = [row[metric] for row in results]

    plt.figure(figsize=(10, 5.5))
    plt.plot(x, y, marker="o", linewidth=2)
    plt.xlabel("Number of Demands")
    plt.ylabel(metric.replace("_", " ").title())
    plt.title(title or f"Demand sweep - {metric}")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_initial_vs_optimized_demand_sweep(
    results,
    output_path=None,
    title="Multi-layer Cross-layer Optimization",
    initial_metric="initial_cost",
    optimized_metric="best_cost",
    ylabel="Total Cross-layer Cost",
    optimized_label="SA Cross-layer Optimized",
):
    """
    Vẽ biểu đồ giống bài đơn lớp IP:
    - Trục X: Number of Demands
    - Trục Y: Cost
    - Đường 1: Initial Allocation
    - Đường 2: SA Optimized
    """
    if not results:
        print("Không có kết quả để vẽ biểu đồ Initial vs Optimized.")
        return

    x = [row["num_demands"] for row in results]
    y_initial = [row[initial_metric] for row in results]
    y_optimized = [row[optimized_metric] for row in results]

    plt.figure(figsize=(11, 6))
    plt.plot(
        x,
        y_initial,
        marker="o",
        linestyle="--",
        linewidth=2,
        label="Initial Allocation",
    )
    plt.plot(
        x,
        y_optimized,
        marker="s",
        linestyle="-",
        linewidth=2,
        label=optimized_label,
    )

    plt.xlabel("Number of Demands")
    plt.ylabel(ylabel)
    plt.title(title, fontweight="bold")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_improvement_percent(
    results,
    output_path=None,
    title="SA Improvement over Initial Allocation",
):
    """Vẽ phần trăm cải thiện theo số demand."""
    if not results:
        print("Không có kết quả để vẽ improvement.")
        return

    x = [row["num_demands"] for row in results]
    y = [row["improvement_percent"] for row in results]

    plt.figure(figsize=(10, 5.5))
    plt.plot(x, y, marker="s", linewidth=2, label="Improvement")
    plt.xlabel("Number of Demands")
    plt.ylabel("Improvement (%)")
    plt.title(title, fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_two_phase_history(
    ip_history,
    optical_history,
    output_path=None,
    title="Two-phase Cross-layer Optimization",
):
    """Vẽ cost history của 2 pha nếu sau này bạn tách IP phase và optical phase."""
    ip_history = ip_history or []
    optical_history = optical_history or []

    if not ip_history and not optical_history:
        print("Không có history để vẽ.")
        return

    merged = ip_history + optical_history
    x = list(range(len(merged)))

    plt.figure(figsize=(10, 5))
    plt.plot(x, merged, marker="o", linewidth=2)

    if ip_history and optical_history:
        phase_boundary = len(ip_history) - 1
        plt.axvline(phase_boundary, linestyle="--", linewidth=2)
        plt.text(phase_boundary, max(merged), "  Phase 1 -> Phase 2", va="top")

    plt.xlabel("Temperature step")
    plt.ylabel("Best cost")
    plt.title(title)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_two_topology_initial_vs_optimized(
    case_results,
    output_path=None,
    ylabel="Total Cross-layer Cost",
    optimized_label="SA Cross-layer Optimized",
):
    """Vẽ 2 subplot giống kiểu hình Abilene/Geant."""
    if not case_results:
        print("Không có kết quả case để vẽ.")
        return

    n_cases = len(case_results)
    fig, axes = plt.subplots(1, n_cases, figsize=(8 * n_cases, 5.5))
    if n_cases == 1:
        axes = [axes]

    for ax, case in zip(axes, case_results):
        results = case["results"]
        x = [row["num_demands"] for row in results]
        y_initial = [row["initial_cost"] for row in results]
        y_optimized = [row["best_cost"] for row in results]

        ax.plot(x, y_initial, marker="o", linestyle="--", linewidth=2, label="Initial Allocation")
        ax.plot(x, y_optimized, marker="s", linestyle="-", linewidth=2, label=optimized_label)
        ax.set_title(case.get("title", "Multi-layer topology"), fontweight="bold")
        ax.set_xlabel("Number of Demands")
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend()

    fig.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_added_removed_lightpaths(
    results,
    output_path=None,
    title="Total Added and Removed Lightpaths",
):
    """Vẽ số lightpath thêm/xóa giữa best state và initial state."""
    if not results:
        print("Không có kết quả để vẽ added/removed lightpaths.")
        return

    x = [row["num_demands"] for row in results]
    added = [row.get("added_lightpaths", 0) for row in results]
    removed = [row.get("removed_lightpaths", 0) for row in results]

    plt.figure(figsize=(11, 6))
    plt.plot(x, added, marker="o", linestyle="-", linewidth=2, label="Added lightpaths")
    plt.plot(x, removed, marker="s", linestyle="--", linewidth=2, label="Removed lightpaths")
    plt.xlabel("Number of Demands")
    plt.ylabel("Number of Lightpaths")
    plt.title(title, fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_network_load(
    results,
    output_path=None,
    title="Network Load Before and After Optimization",
):
    """Vẽ network load = used slots / total slots trước và sau tối ưu."""
    if not results:
        print("Không có kết quả để vẽ network load.")
        return

    x = [row["num_demands"] for row in results]
    initial = [row.get("initial_network_load", 0) * 100 for row in results]
    optimized = [row.get("best_network_load", 0) * 100 for row in results]

    plt.figure(figsize=(11, 6))
    plt.plot(x, initial, marker="o", linestyle="--", linewidth=2, label="Initial load")
    plt.plot(x, optimized, marker="s", linestyle="-", linewidth=2, label="Optimized load")
    plt.xlabel("Number of Demands")
    plt.ylabel("Network Load (%)")
    plt.title(title, fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()


def plot_rho_impact(
    results,
    output_path=None,
    title="Impact of Rho on SA Improvement",
):
    """Vẽ ảnh hưởng của rho_limit lên improvement percent."""
    if not results:
        print("Không có kết quả để vẽ rho impact.")
        return

    demand_values = sorted(set(row.get("num_demands") for row in results))

    plt.figure(figsize=(11, 6))
    for num_demands in demand_values:
        group = [row for row in results if row.get("num_demands") == num_demands]
        group = sorted(group, key=lambda row: row["rho_limit"])
        x = [row["rho_limit"] for row in group]
        y = [row["improvement_percent"] for row in group]
        plt.plot(
            x,
            y,
            marker="o",
            linewidth=2,
            label=f"{num_demands} demands",
        )

    plt.xlabel("Rho limit")
    plt.ylabel("Improvement (%)")
    plt.title(title, fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()

    if output_path:
        _ensure_parent_dir(output_path)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"[+] Đã lưu biểu đồ: {output_path}")
    else:
        plt.show()
