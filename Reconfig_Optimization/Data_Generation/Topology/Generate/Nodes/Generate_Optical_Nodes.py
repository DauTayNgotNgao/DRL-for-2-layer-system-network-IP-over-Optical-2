# Noi dung/Muc dich:
# Sinh cac optical ROADM nodes. Moi optical node dai dien cho mot PoP/vị tri
# vat ly trong optical transport network.

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
from topology_common import format_float, random_point, rng, write_csv


def generate() -> None:
    generator = rng(cfg.RANDOM_SEED, salt=101)
    rows = []
    for index in range(cfg.NUM_OPTICAL_NODES):
        x, y = random_point(generator, cfg.AREA_WIDTH, cfg.AREA_HEIGHT)
        rows.append(
            {
                "optical_node_id": f"opt_{index}",
                "pop_id": f"pop_{index}",
                "x": format_float(x),
                "y": format_float(y),
                "node_type": "roadm",
            }
        )

    write_csv(
        cfg.OPTICAL_NODES_FILE,
        rows,
        ["optical_node_id", "pop_id", "x", "y", "node_type"],
    )
    print(f"Wrote {len(rows)} optical nodes -> {cfg.OPTICAL_NODES_FILE}")


if __name__ == "__main__":
    generate()
