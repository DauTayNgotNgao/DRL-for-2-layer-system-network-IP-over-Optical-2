# Noi dung/Muc dich:
# Sinh cac ban ghi optical slot/wavelength kha dung cho tung fiber. Day la tai
# nguyen vat ly tho; optimization ve sau co the reserve slots cho lightpaths.

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
    optical_links = read_csv(cfg.OPTICAL_LINKS_FILE)
    rows = []
    for link in optical_links:
        capacity = int(link["fiber_capacity_lightpaths"])
        for slot_index in range(capacity):
            rows.append(
                {
                    "optical_link_id": link["optical_link_id"],
                    "src_optical_node_id": link["src_optical_node_id"],
                    "dst_optical_node_id": link["dst_optical_node_id"],
                    "slot_index": slot_index,
                    "status": "free",
                }
            )

    write_csv(
        cfg.OPTICAL_FIBER_SLOTS_FILE,
        rows,
        [
            "optical_link_id",
            "src_optical_node_id",
            "dst_optical_node_id",
            "slot_index",
            "status",
        ],
    )
    print(f"Wrote {len(rows)} optical fiber slots -> {cfg.OPTICAL_FIBER_SLOTS_FILE}")


if __name__ == "__main__":
    generate()
