# Noi dung/Muc dich:
# Tao baseline IP-lightpath solution tu initial IP topology bang cach chon
# candidate optical path ngan nhat cho moi IP link. Day la solution khoi tao,
# tach rieng voi physical topology va candidate paths.

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


def _candidate_key(row: dict) -> tuple:
    return tuple(sorted((row["ip_src"], row["ip_dst"])))


def generate() -> None:
    ip_links = read_csv(cfg.IP_LINKS_FILE)
    candidates = read_csv(cfg.CANDIDATE_OPTICAL_PATHS_FILE)

    best_candidate = {}
    for row in candidates:
        key = _candidate_key(row)
        current = best_candidate.get(key)
        if current is None or float(row["total_length_km"]) < float(current["total_length_km"]):
            best_candidate[key] = row

    rows = []
    for index, link in enumerate(ip_links):
        key = tuple(sorted((link["src_ip_node_id"], link["dst_ip_node_id"])))
        candidate = best_candidate.get(key)
        if candidate is None:
            raise ValueError(f"No candidate optical path for IP link {link['ip_link_id']}")
        rows.append(
            {
                "lightpath_id": f"lp_{index}",
                "ip_link_id": link["ip_link_id"],
                "src_ip_node_id": link["src_ip_node_id"],
                "dst_ip_node_id": link["dst_ip_node_id"],
                "selected_path_id": candidate["path_id"],
                "num_lightpaths": 1,
                "capacity_gbps": cfg.LIGHTPATH_CAPACITY_GBPS,
                "solution_type": "baseline_initial",
            }
        )

    write_csv(
        cfg.BASELINE_IP_LIGHTPATHS_FILE,
        rows,
        [
            "lightpath_id",
            "ip_link_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "selected_path_id",
            "num_lightpaths",
            "capacity_gbps",
            "solution_type",
        ],
    )
    print(f"Wrote {len(rows)} baseline IP lightpaths -> {cfg.BASELINE_IP_LIGHTPATHS_FILE}")


if __name__ == "__main__":
    generate()
