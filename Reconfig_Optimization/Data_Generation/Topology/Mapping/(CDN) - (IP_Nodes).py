# Noi dung/Muc dich:
# Map cac CDN/hyper-giant peering sites toi IP routers gan nhat va gan peering
# capacity. File nay quan ly hypergiant_id, peering_capacity va
# peering_ip_node_id.

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
from topology_common import format_float, nearest_node, read_csv, rng, write_csv


def _random_peering_capacity(generator) -> int:
    values = list(
        range(
            cfg.PEERING_CAPACITY_MIN_GBPS,
            cfg.PEERING_CAPACITY_MAX_GBPS + 1,
            cfg.PEERING_CAPACITY_STEP_GBPS,
        )
    )
    return generator.choice(values)


def generate() -> None:
    generator = rng(cfg.RANDOM_SEED, salt=707)
    cdn_nodes = read_csv(cfg.CDN_NODES_FILE)
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    targets = [row for row in ip_nodes if row["role"] in {"cdn_peering", "core"}]
    if not targets:
        targets = ip_nodes

    rows = []
    used_ip_by_hypergiant = {}
    for cdn in cdn_nodes:
        used_ips = used_ip_by_hypergiant.setdefault(cdn["hypergiant_id"], set())
        available_targets = [
            row for row in targets if row["ip_node_id"] not in used_ips
        ]
        if not available_targets:
            available_targets = targets

        ip_node, dist = nearest_node(cdn, available_targets)
        used_ips.add(ip_node["ip_node_id"])
        rows.append(
            {
                "cdn_node_id": cdn["cdn_node_id"],
                "hypergiant_id": cdn["hypergiant_id"],
                "peering_ip_node_id": ip_node["ip_node_id"],
                "peering_pop_id": ip_node["pop_id"],
                "peering_capacity_gbps": _random_peering_capacity(generator),
                "distance_to_ip": format_float(dist),
            }
        )

    write_csv(
        cfg.CDN_IP_MAPPING_FILE,
        rows,
        [
            "cdn_node_id",
            "hypergiant_id",
            "peering_ip_node_id",
            "peering_pop_id",
            "peering_capacity_gbps",
            "distance_to_ip",
        ],
    )
    print(f"Wrote {len(rows)} CDN-IP peering mappings -> {cfg.CDN_IP_MAPPING_FILE}")


if __name__ == "__main__":
    generate()
