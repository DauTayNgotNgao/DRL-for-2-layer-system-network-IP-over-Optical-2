# Noi dung/Muc dich:
# Sinh initial connected IP topology. Day la graph baseline/ban dau; ve sau
# optimization co the thay the bang solution IP links va capacities.

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
from topology_common import generate_connected_edges, read_csv, rng, write_csv, format_float


def generate() -> None:
    nodes = read_csv(cfg.IP_NODES_FILE)
    node_ids = [row["ip_node_id"] for row in nodes]
    coordinates = {row["ip_node_id"]: (float(row["x"]), float(row["y"])) for row in nodes}
    edges = generate_connected_edges(
        node_ids,
        coordinates,
        cfg.NUM_IP_LINKS,
        rng(cfg.RANDOM_SEED, salt=606),
    )

    rows = []
    for index, (src, dst, length) in enumerate(edges):
        rows.append(
            {
                "ip_link_id": f"ip_link_{index}",
                "src_ip_node_id": src,
                "dst_ip_node_id": dst,
                "length_geo": format_float(length),
                "link_role": "initial_topology",
            }
        )

    write_csv(
        cfg.IP_LINKS_FILE,
        rows,
        ["ip_link_id", "src_ip_node_id", "dst_ip_node_id", "length_geo", "link_role"],
    )
    print(f"Wrote {len(rows)} initial IP links -> {cfg.IP_LINKS_FILE}")


if __name__ == "__main__":
    generate()
