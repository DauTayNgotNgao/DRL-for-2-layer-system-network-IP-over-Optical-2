# Noi dung/Muc dich:
# Pipeline sinh dynamic traffic cho ca BG va H. File nay tao traffic matrix
# rieng cho tung loai traffic, sinh connection requests theo Poisson process,
# roi gop thanh mot file all_dynamic_requests.csv sap xep theo arrival_time.

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "Traffict"))

import Config as cfg
from dynamic_traffic_common import (
    dynamic_request_fieldnames,
    write_bg_dynamic_outputs,
    write_h_dynamic_outputs,
)
from topology_common import write_csv


def main() -> None:
    bg_requests = write_bg_dynamic_outputs()
    h_requests = write_h_dynamic_outputs()
    all_requests = bg_requests + h_requests
    all_requests.sort(key=lambda row: float(row["arrival_time"]))

    write_csv(
        cfg.ALL_DYNAMIC_REQUESTS_FILE,
        all_requests,
        dynamic_request_fieldnames(include_h_fields=True),
    )

    bg_bandwidth = sum(float(row["bandwidth_gbps"]) for row in bg_requests)
    h_bandwidth = sum(float(row["bandwidth_gbps"]) for row in h_requests)
    total_bandwidth = bg_bandwidth + h_bandwidth
    h_share = 0.0 if total_bandwidth == 0 else h_bandwidth / total_bandwidth

    print(f"Wrote {len(bg_requests)} BG dynamic requests")
    print(f"Wrote {len(h_requests)} H dynamic requests")
    print(f"BG requested bandwidth sum: {bg_bandwidth:.3f} Gbps")
    print(f"H requested bandwidth sum: {h_bandwidth:.3f} Gbps")
    print(f"H dynamic bandwidth share: {h_share:.3%}")
    print(f"Wrote all dynamic requests -> {cfg.ALL_DYNAMIC_REQUESTS_FILE}")


if __name__ == "__main__":
    main()
