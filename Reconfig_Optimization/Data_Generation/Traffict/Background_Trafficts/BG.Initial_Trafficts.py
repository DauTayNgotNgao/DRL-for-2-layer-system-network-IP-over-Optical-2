# Noi dung/Muc dich:
# File du kien sinh initial background traffic giua cac IP routers. Background
# traffic khong thuoc top hyper-giants va se duoc dung de bo sung AllTraffic.

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
    generate_bg_demands,
    route_demands,
    write_lightpath_loads,
    write_resource_usage,
)


def generate() -> None:
    demands = generate_bg_demands()
    routing_rows, lightpath_state = route_demands(demands, seed_salt=1301)

    write_csv(
        cfg.BG_INITIAL_DEMANDS_FILE,
        demands,
        ["demand_id", "traffic_type", "src_ip_node_id", "dst_ip_node_id", "demand_gbps"],
    )
    write_csv(
        cfg.BG_INITIAL_ROUTING_FILE,
        routing_rows,
        [
            "demand_id",
            "traffic_type",
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
    write_lightpath_loads(cfg.BG_INITIAL_IP_LIGHTPATH_LOADS_FILE, lightpath_state)
    write_resource_usage(cfg.BG_INITIAL_RESOURCE_USAGE_FILE, lightpath_state)

    opened = sum(
        row["num_lightpaths"] - row["initial_lightpaths"]
        for row in lightpath_state["lightpaths"].values()
    )
    blocked = sum(1 for row in routing_rows if row["status"] == "blocked")
    bg_volume = sum(float(row["demand_gbps"]) for row in demands)
    print(f"Wrote {len(demands)} BG initial demands -> {cfg.BG_INITIAL_DEMANDS_FILE}")
    print(f"BG volume: {bg_volume:.3f} Gbps")
    print(f"Wrote BG greedy routing -> {cfg.BG_INITIAL_ROUTING_FILE}")
    print(f"Blocked {blocked} BG demands")
    print(f"Opened {opened} extra lightpaths for BG traffic")


if __name__ == "__main__":
    generate()
