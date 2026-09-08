# Noi dung/Muc dich:
# File du kien sinh initial traffic demands cho hyper-giants/CDN. Phan nay se
# gan demand tu cac cum end-user toi tung hypergiant_id sau khi topology on dinh.

import sys
from pathlib import Path

DATA_DIR = None
for parent in Path(__file__).resolve().parents:
    if (parent / "Config.py").exists():
        DATA_DIR = parent
        sys.path.insert(0, str(parent))
        sys.path.insert(0, str(parent / "Traffict"))
        break
if DATA_DIR is None:
    raise RuntimeError("Could not locate Data_Generation directory.")

import Config as cfg
from topology_common import write_csv
from traffic_common import (
    generate_h_demands,
    route_demands,
    write_lightpath_loads,
    write_resource_usage,
)


def generate() -> None:
    demands, peering_load_rows = generate_h_demands()
    routing_rows, lightpath_state = route_demands(demands, seed_salt=1401)

    write_csv(
        cfg.H_INITIAL_DEMANDS_FILE,
        demands,
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
        cfg.H_INITIAL_ROUTING_FILE,
        routing_rows,
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
    write_lightpath_loads(cfg.H_INITIAL_IP_LIGHTPATH_LOADS_FILE, lightpath_state)
    write_resource_usage(cfg.H_INITIAL_RESOURCE_USAGE_FILE, lightpath_state)

    opened = sum(
        row["num_lightpaths"] - row["initial_lightpaths"]
        for row in lightpath_state["lightpaths"].values()
    )
    blocked = sum(1 for row in routing_rows if row["status"] == "blocked")
    h_volume = sum(float(row["demand_gbps"]) for row in demands)
    print(f"Wrote {len(demands)} H initial demands -> {cfg.H_INITIAL_DEMANDS_FILE}")
    print(f"H volume: {h_volume:.3f} Gbps")
    print(f"Wrote H greedy routing -> {cfg.H_INITIAL_ROUTING_FILE}")
    print(f"Wrote H peering loads -> {cfg.H_INITIAL_PEERING_LOADS_FILE}")
    print(f"Blocked {blocked} H demands")
    print(f"Opened {opened} extra lightpaths for H traffic")


if __name__ == "__main__":
    generate()
