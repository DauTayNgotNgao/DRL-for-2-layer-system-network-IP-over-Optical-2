# Noi dung/Muc dich:
# Xuat mapping collocation tu IP routers sang optical ROADMs. IP routers nam
# cung PoP voi optical nodes, nen quan he nay la vat ly, khong chi la gan nhat.

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
from topology_common import read_csv, write_csv


def generate() -> None:
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    rows = []
    for ip_node in ip_nodes:
        rows.append(
            {
                "ip_node_id": ip_node["ip_node_id"],
                "pop_id": ip_node["pop_id"],
                "optical_node_id": ip_node["optical_node_id"],
                "collocation_type": "same_pop",
                "distance_to_optical": "0.000",
            }
        )

    write_csv(
        cfg.IP_OPTICAL_MAPPING_FILE,
        rows,
        [
            "ip_node_id",
            "pop_id",
            "optical_node_id",
            "collocation_type",
            "distance_to_optical",
        ],
    )
    print(f"Wrote {len(rows)} IP-optical collocations -> {cfg.IP_OPTICAL_MAPPING_FILE}")


if __name__ == "__main__":
    generate()
