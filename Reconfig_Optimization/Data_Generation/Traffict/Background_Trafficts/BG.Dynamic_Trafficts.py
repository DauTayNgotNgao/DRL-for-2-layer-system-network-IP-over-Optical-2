# Noi dung/Muc dich:
# File du kien sinh dynamic background traffic theo thoi gian giua cac IP
# routers. Phan nay phuc vu danh gia reconfiguration voi traffic bien thien.

import sys
from pathlib import Path

DATA_DIR = None
for parent in Path(__file__).resolve().parents:
    if (parent / "Config.py").exists():
        DATA_DIR = parent
        sys.path.insert(0, str(parent))
        sys.path.insert(0, str(parent / "Traffict"))
        break
if DATA_DIR is None:
    raise RuntimeError("Could not locate Data_Generation directory.")

import Config as cfg
from dynamic_traffic_common import write_bg_dynamic_outputs


def generate() -> None:
    requests = write_bg_dynamic_outputs()
    total_bandwidth = sum(float(row["bandwidth_gbps"]) for row in requests)
    print(f"Wrote {len(requests)} BG dynamic requests -> {cfg.BG_DYNAMIC_REQUESTS_FILE}")
    print(f"Wrote BG dynamic traffic matrix -> {cfg.BG_DYNAMIC_TRAFFIC_MATRIX_FILE}")
    print(f"BG dynamic requested bandwidth sum: {total_bandwidth:.3f} Gbps")


if __name__ == "__main__":
    generate()
