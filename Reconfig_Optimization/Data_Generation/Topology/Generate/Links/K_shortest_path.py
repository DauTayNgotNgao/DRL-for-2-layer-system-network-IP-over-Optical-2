# Noi dung/Muc dich:
# Tinh truoc candidate optical paths giua moi cap IP routers. Day la cac lua
# chon kha thi cho optimization ve sau; chung chua phai selected lightpaths.

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
from topology_common import (
    build_undirected_adjacency,
    format_float,
    k_shortest_simple_paths,
    load_ip_to_optical,
    read_csv,
    write_csv,
)


def generate() -> None:
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    optical_links = read_csv(cfg.OPTICAL_LINKS_FILE)
    ip_optical = read_csv(cfg.IP_OPTICAL_MAPPING_FILE)
    ip_to_optical = load_ip_to_optical(ip_optical)
    adjacency = build_undirected_adjacency(
        optical_links,
        "src_optical_node_id",
        "dst_optical_node_id",
        "length_km",
    )

    rows = []
    for i, src_ip in enumerate(ip_nodes):
        for dst_ip in ip_nodes[i + 1 :]:
            src = src_ip["ip_node_id"]
            dst = dst_ip["ip_node_id"]
            src_opt = ip_to_optical[src]
            dst_opt = ip_to_optical[dst]
            paths = k_shortest_simple_paths(adjacency, src_opt, dst_opt, cfg.K_SHORTEST_PATHS)
            if not paths:
                raise ValueError(
                    f"No optical path found between {src_opt} and {dst_opt}; "
                    "check optical physical topology connectivity."
                )
            for path_index, (path, length) in enumerate(paths):
                rows.append(
                    {
                        "ip_src": src,
                        "ip_dst": dst,
                        "path_id": f"{src}_{dst}_p{path_index}",
                        "src_optical_node_id": src_opt,
                        "dst_optical_node_id": dst_opt,
                        "optical_path": "-".join(path),
                        "optical_hops": max(0, len(path) - 1),
                        "total_length_km": format_float(length),
                    }
                )

    write_csv(
        cfg.CANDIDATE_OPTICAL_PATHS_FILE,
        rows,
        [
            "ip_src",
            "ip_dst",
            "path_id",
            "src_optical_node_id",
            "dst_optical_node_id",
            "optical_path",
            "optical_hops",
            "total_length_km",
        ],
    )
    print(f"Wrote {len(rows)} candidate optical paths -> {cfg.CANDIDATE_OPTICAL_PATHS_FILE}")


if __name__ == "__main__":
    generate()
