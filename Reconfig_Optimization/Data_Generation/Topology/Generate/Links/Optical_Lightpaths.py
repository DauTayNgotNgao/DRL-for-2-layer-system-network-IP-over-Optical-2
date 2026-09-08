# Noi dung/Muc dich:
# Mo rong cac baseline IP lightpaths da chon thanh cac optical fiber segments.
# File nay bieu dien phan solution dang su dung tren physical optical topology.

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
from topology_common import optical_edge_lookup, read_csv, write_csv


def generate() -> None:
    baseline_lightpaths = read_csv(cfg.BASELINE_IP_LIGHTPATHS_FILE)
    candidate_paths = {row["path_id"]: row for row in read_csv(cfg.CANDIDATE_OPTICAL_PATHS_FILE)}
    optical_links = read_csv(cfg.OPTICAL_LINKS_FILE)
    edge_to_link = optical_edge_lookup(optical_links)

    rows = []
    for lightpath in baseline_lightpaths:
        candidate = candidate_paths[lightpath["selected_path_id"]]
        optical_nodes = candidate["optical_path"].split("-") if candidate["optical_path"] else []
        if len(optical_nodes) <= 1:
            rows.append(
                {
                    "lightpath_id": lightpath["lightpath_id"],
                    "ip_link_id": lightpath["ip_link_id"],
                    "segment_order": 0,
                    "optical_link_id": "local_collocation",
                    "src_optical_node_id": candidate["src_optical_node_id"],
                    "dst_optical_node_id": candidate["dst_optical_node_id"],
                    "slot_index": "",
                    "status": "local",
                }
            )
            continue

        for segment_order, (src, dst) in enumerate(zip(optical_nodes, optical_nodes[1:])):
            edge_key = tuple(sorted((src, dst)))
            optical_link_id = edge_to_link.get(edge_key)
            if optical_link_id is None:
                raise ValueError(
                    f"Candidate path uses missing optical edge {src}-{dst} "
                    f"for lightpath {lightpath['lightpath_id']}"
                )
            rows.append(
                {
                    "lightpath_id": lightpath["lightpath_id"],
                    "ip_link_id": lightpath["ip_link_id"],
                    "segment_order": segment_order,
                    "optical_link_id": optical_link_id,
                    "src_optical_node_id": src,
                    "dst_optical_node_id": dst,
                    "slot_index": "",
                    "status": "planned",
                }
            )

    write_csv(
        cfg.BASELINE_OPTICAL_LIGHTPATHS_FILE,
        rows,
        [
            "lightpath_id",
            "ip_link_id",
            "segment_order",
            "optical_link_id",
            "src_optical_node_id",
            "dst_optical_node_id",
            "slot_index",
            "status",
        ],
    )
    print(
        f"Wrote {len(rows)} baseline optical lightpath segments -> "
        f"{cfg.BASELINE_OPTICAL_LIGHTPATHS_FILE}"
    )


if __name__ == "__main__":
    generate()
