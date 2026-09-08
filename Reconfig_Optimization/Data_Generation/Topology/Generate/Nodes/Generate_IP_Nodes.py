# Noi dung/Muc dich:
# Sinh cac IP router nodes va collocate moi IP router voi mot optical PoP.
# Nhieu IP router co the dung chung mot optical node/PoP, phu hop voi mo hinh
# IP-over-optical trong bai bao.

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
from topology_common import jittered_point, read_csv, rng, write_csv, format_float


def _role_for_index(index: int) -> str:
    if index % 5 == 0:
        return "cdn_peering"
    if index % 3 == 0:
        return "user_access"
    return "core"


def generate() -> None:
    if cfg.NUM_IP_NODES < cfg.NUM_OPTICAL_NODES:
        raise ValueError(
            "NUM_IP_NODES should be >= NUM_OPTICAL_NODES so every optical PoP "
            "has at least one IP router."
        )

    optical_nodes = read_csv(cfg.OPTICAL_NODES_FILE)
    generator = rng(cfg.RANDOM_SEED, salt=202)
    rows = []

    assigned_optical = []
    for index in range(cfg.NUM_IP_NODES):
        if index < len(optical_nodes):
            optical = optical_nodes[index]
        else:
            optical = generator.choice(optical_nodes)
        assigned_optical.append(optical)

        x, y = jittered_point(
            generator,
            float(optical["x"]),
            float(optical["y"]),
            cfg.IP_COLLOCATION_JITTER,
            cfg.AREA_WIDTH,
            cfg.AREA_HEIGHT,
        )

        rows.append(
            {
                "ip_node_id": f"ip_{index}",
                "pop_id": optical["pop_id"],
                "optical_node_id": optical["optical_node_id"],
                "role": _role_for_index(index),
                "x": format_float(x),
                "y": format_float(y),
                "transceivers": cfg.IP_ROUTER_TRANSCEIVERS,
            }
        )

    write_csv(
        cfg.IP_NODES_FILE,
        rows,
        ["ip_node_id", "pop_id", "optical_node_id", "role", "x", "y", "transceivers"],
    )
    print(f"Wrote {len(rows)} IP nodes -> {cfg.IP_NODES_FILE}")


if __name__ == "__main__":
    generate()
