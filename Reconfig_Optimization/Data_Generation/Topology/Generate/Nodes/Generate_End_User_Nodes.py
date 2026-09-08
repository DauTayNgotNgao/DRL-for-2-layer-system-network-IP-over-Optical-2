# Noi dung/Muc dich:
# Sinh cac end-user/access-area nodes da duoc gom cum. Moi dong dai dien cho
# mot nhom user lon va ve sau co the duoc mo rong thanh traffic demands.

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
    generator = rng(cfg.RANDOM_SEED, salt=404)
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    candidate_sites = [row for row in ip_nodes if row["role"] in {"user_access", "core"}]
    if not candidate_sites:
        candidate_sites = ip_nodes

    rows = []
    for index in range(cfg.NUM_END_USER_NODES):
        anchor = generator.choice(candidate_sites)
        x, y = jittered_point(
            generator,
            float(anchor["x"]),
            float(anchor["y"]),
            cfg.END_USER_LOCATION_JITTER,
            cfg.AREA_WIDTH,
            cfg.AREA_HEIGHT,
        )
        rows.append(
            {
                "end_user_node_id": f"user_{index}",
                "x": format_float(x),
                "y": format_float(y),
                "user_group_size": generator.randint(
                    cfg.USER_GROUP_SIZE_MIN,
                    cfg.USER_GROUP_SIZE_MAX,
                ),
                "demand_scale_gbps": generator.randint(
                    cfg.END_USER_DEMAND_SCALE_MIN_GBPS,
                    cfg.END_USER_DEMAND_SCALE_MAX_GBPS,
                ),
            }
        )

    write_csv(
        cfg.END_USER_NODES_FILE,
        rows,
        ["end_user_node_id", "x", "y", "user_group_size", "demand_scale_gbps"],
    )
    print(f"Wrote {len(rows)} end-user nodes -> {cfg.END_USER_NODES_FILE}")


if __name__ == "__main__":
    generate()
