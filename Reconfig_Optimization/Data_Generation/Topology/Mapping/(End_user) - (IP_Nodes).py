# Noi dung/Muc dich:
# Map cac end-user/access-area nodes da gom cum toi IP routers gan nhat. Moi
# end-user node dai dien cho mot nhom user lon, khong phai mot user ca nhan.

import sys
from pathlib import Path

DATA_DIR = None
for parent in Path(__file__).resolve().parents:
    if (parent / "Config.py").exists():
        DATA_DIR = parent
        sys.path.insert(0, str(parent))
        break
if DATA_DIR is None:
    raise RuntimeError("Could not locate Data_Generation directory.")

import Config as cfg
from topology_common import format_float, nearest_node, read_csv, write_csv


def generate() -> None:
    users = read_csv(cfg.END_USER_NODES_FILE)
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    targets = [row for row in ip_nodes if row["role"] in {"user_access", "core"}]
    if not targets:
        targets = ip_nodes

    rows = []
    for user in users:
        ip_node, dist = nearest_node(user, targets)
        rows.append(
            {
                "end_user_node_id": user["end_user_node_id"],
                "ip_node_id": ip_node["ip_node_id"],
                "pop_id": ip_node["pop_id"],
                "user_group_size": user["user_group_size"],
                "demand_scale_gbps": user["demand_scale_gbps"],
                "distance_to_ip": format_float(dist),
            }
        )

    write_csv(
        cfg.END_USER_IP_MAPPING_FILE,
        rows,
        [
            "end_user_node_id",
            "ip_node_id",
            "pop_id",
            "user_group_size",
            "demand_scale_gbps",
            "distance_to_ip",
        ],
    )
    print(f"Wrote {len(rows)} end-user-IP mappings -> {cfg.END_USER_IP_MAPPING_FILE}")


if __name__ == "__main__":
    generate()
