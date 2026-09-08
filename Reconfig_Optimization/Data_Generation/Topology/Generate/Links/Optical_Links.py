# Noi dung/Muc dich:
# Sinh optical physical fiber topology. Graph duoc dam bao connected neu
# NUM_OPTICAL_LINKS >= NUM_OPTICAL_NODES - 1; neu khong, script se bao loi ro.

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
    nodes = read_csv(cfg.OPTICAL_NODES_FILE)
    node_ids = [row["optical_node_id"] for row in nodes]
    coordinates = {
        row["optical_node_id"]: (float(row["x"]), float(row["y"]))
        for row in nodes
    }
    edges = generate_connected_edges(
        node_ids,
        coordinates,
        cfg.NUM_OPTICAL_LINKS,
        rng(cfg.RANDOM_SEED, salt=505),
    )

    rows = []
    for index, (src, dst, length) in enumerate(edges):
        rows.append(
            {
                "optical_link_id": f"of_{index}",
                "src_optical_node_id": src,
                "dst_optical_node_id": dst,
                "length_km": format_float(length),
                "fiber_capacity_lightpaths": cfg.FIBER_CAPACITY_LIGHTPATHS,
            }
        )

    write_csv(
        cfg.OPTICAL_LINKS_FILE,
        rows,
        [
            "optical_link_id",
            "src_optical_node_id",
            "dst_optical_node_id",
            "length_km",
            "fiber_capacity_lightpaths",
        ],
    )
    print(f"Wrote {len(rows)} optical physical links -> {cfg.OPTICAL_LINKS_FILE}")


if __name__ == "__main__":
    generate()
