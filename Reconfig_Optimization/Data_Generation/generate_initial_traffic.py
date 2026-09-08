# Noi dung/Muc dich:
# Pipeline sinh initial traffic chung cho ca BG traffic va H traffic. File nay
# route tat ca demands tren cung mot trang thai capacity de biet tong so
# lightpaths can mo them khi chay AllTraffic.

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "Traffict"))

import Config as cfg
from topology_common import write_csv
from traffic_common import (
    generate_bg_demands,
    generate_h_demands,
    load_lightpath_state,
    route_demands,
    write_lightpath_loads,
    write_resource_usage,
)


def main() -> None:
    bg_demands = generate_bg_demands()
    h_demands, peering_load_rows = generate_h_demands()
    all_demands = bg_demands + h_demands

    lightpath_state = load_lightpath_state()
    bg_routes, lightpath_state = route_demands(
        bg_demands,
        seed_salt=1501,
        lightpath_state=lightpath_state,
    )
    h_routes, lightpath_state = route_demands(
        h_demands,
        seed_salt=1502,
        lightpath_state=lightpath_state,
    )

    write_csv(
        cfg.BG_INITIAL_DEMANDS_FILE,
        bg_demands,
        ["demand_id", "traffic_type", "src_ip_node_id", "dst_ip_node_id", "demand_gbps"],
    )
    write_csv(
        cfg.H_INITIAL_DEMANDS_FILE,
        h_demands,
        [
            "demand_id",
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "src_ip_node_id",
            "end_user_node_id",
            "dst_ip_node_id",
            "demand_gbps",
        ],
    )
    write_csv(
        cfg.H_INITIAL_PEERING_LOADS_FILE,
        peering_load_rows,
        [
            "cdn_node_id",
            "hypergiant_id",
            "peering_ip_node_id",
            "peering_capacity_gbps",
            "allocated_gbps",
            "peering_utilization",
        ],
    )

    write_csv(
        cfg.ALL_INITIAL_DEMANDS_FILE,
        all_demands,
        [
            "demand_id",
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "src_ip_node_id",
            "end_user_node_id",
            "dst_ip_node_id",
            "demand_gbps",
        ],
    )
    write_csv(
        cfg.BG_INITIAL_ROUTING_FILE,
        bg_routes,
        [
            "demand_id",
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "end_user_node_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "demand_gbps",
            "ip_path",
            "ip_link_path",
            "ip_hops",
            "opened_lightpaths",
            "status",
            "block_reason",
        ],
    )
    write_csv(
        cfg.H_INITIAL_ROUTING_FILE,
        h_routes,
        [
            "demand_id",
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "end_user_node_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "demand_gbps",
            "ip_path",
            "ip_link_path",
            "ip_hops",
            "opened_lightpaths",
            "status",
            "block_reason",
        ],
    )
    write_csv(
        cfg.ALL_INITIAL_ROUTING_FILE,
        bg_routes + h_routes,
        [
            "demand_id",
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "end_user_node_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "demand_gbps",
            "ip_path",
            "ip_link_path",
            "ip_hops",
            "opened_lightpaths",
            "status",
            "block_reason",
        ],
    )
    write_lightpath_loads(cfg.ALL_INITIAL_IP_LIGHTPATH_LOADS_FILE, lightpath_state)
    write_resource_usage(cfg.ALL_INITIAL_RESOURCE_USAGE_FILE, lightpath_state)

    opened = sum(
        row["num_lightpaths"] - row["initial_lightpaths"]
        for row in lightpath_state["lightpaths"].values()
    )
    blocked_bg = sum(1 for row in bg_routes if row["status"] == "blocked")
    blocked_h = sum(1 for row in h_routes if row["status"] == "blocked")
    routed_bg_volume = sum(
        float(row["demand_gbps"]) for row in bg_routes if row["status"] == "routed"
    )
    routed_h_volume = sum(
        float(row["demand_gbps"]) for row in h_routes if row["status"] == "routed"
    )
    bg_volume = sum(float(row["demand_gbps"]) for row in bg_demands)
    h_volume = sum(float(row["demand_gbps"]) for row in h_demands)
    total_volume = bg_volume + h_volume
    h_share = 0.0 if total_volume == 0 else h_volume / total_volume
    routed_total_volume = routed_bg_volume + routed_h_volume
    routed_h_share = (
        0.0 if routed_total_volume == 0 else routed_h_volume / routed_total_volume
    )
    print(f"Wrote {len(bg_demands)} BG demands and {len(h_demands)} H demands")
    print(f"BG volume: {bg_volume:.3f} Gbps")
    print(f"H volume: {h_volume:.3f} Gbps")
    print(f"H traffic share: {h_share:.3%}")
    print(f"Routed BG volume: {routed_bg_volume:.3f} Gbps")
    print(f"Routed H volume: {routed_h_volume:.3f} Gbps")
    print(f"Routed H traffic share: {routed_h_share:.3%}")
    print(f"Blocked BG demands: {blocked_bg}")
    print(f"Blocked H demands: {blocked_h}")
    print(f"Wrote all initial routing -> {cfg.ALL_INITIAL_ROUTING_FILE}")
    print(f"Opened {opened} extra lightpaths for AllTraffic")


if __name__ == "__main__":
    main()
