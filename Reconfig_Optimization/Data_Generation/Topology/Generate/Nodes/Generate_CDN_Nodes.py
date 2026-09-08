# Noi dung/Muc dich:
# Sinh cac CDN/hyper-giant peering-site nodes. Peering capacity va IP router
# cua ISP duoc chon se nam trong file mapping CDN-IP, khong nam o file nay.

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
from topology_common import format_float, jittered_point, read_csv, rng, write_csv


def generate() -> None:
    generator = rng(cfg.RANDOM_SEED, salt=303)
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    candidate_sites = [row for row in ip_nodes if row["role"] in {"cdn_peering", "core"}]
    if not candidate_sites:
        candidate_sites = ip_nodes

    rows = []
    index = 0
    for hypergiant_id in cfg.HYPERGIANT_IDS:
        for peering_index in range(cfg.CDN_PEERINGS_PER_HYPERGIANT):
            anchor = generator.choice(candidate_sites)
            x, y = jittered_point(
                generator,
                float(anchor["x"]),
                float(anchor["y"]),
                cfg.CDN_LOCATION_JITTER,
                cfg.AREA_WIDTH,
                cfg.AREA_HEIGHT,
            )
            rows.append(
                {
                    "cdn_node_id": f"cdn_{index}",
                    "hypergiant_id": hypergiant_id,
                    "peering_index": peering_index,
                    "x": format_float(x),
                    "y": format_float(y),
                }
            )
            index += 1

    write_csv(
        cfg.CDN_NODES_FILE,
        rows,
        ["cdn_node_id", "hypergiant_id", "peering_index", "x", "y"],
    )
    print(f"Wrote {len(rows)} CDN nodes -> {cfg.CDN_NODES_FILE}")


if __name__ == "__main__":
    generate()
