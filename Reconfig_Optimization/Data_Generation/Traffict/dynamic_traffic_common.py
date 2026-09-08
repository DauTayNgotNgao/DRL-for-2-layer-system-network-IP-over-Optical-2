# Noi dung/Muc dich:
# Cac ham dung chung de sinh dynamic connection requests. Request den theo
# Poisson process dua tren traffic matrix, duration lay tu exponential
# distribution bi gioi han 5-15 don vi thoi gian, bandwidth lay tu Weibull
# distribution voi coefficient of variation cau hinh trong Config.py.

from __future__ import annotations

import bisect
import math
from collections import defaultdict, deque
from typing import Dict, List, Sequence

import Config as cfg
from topology_common import read_csv, rng, write_csv


def _build_optical_adjacency() -> Dict[str, List[str]]:
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for row in read_csv(cfg.OPTICAL_LINKS_FILE):
        src = row["src_optical_node_id"]
        dst = row["dst_optical_node_id"]
        adjacency[src].append(dst)
        adjacency[dst].append(src)
    for neighbors in adjacency.values():
        neighbors.sort()
    return dict(adjacency)


def _shortest_hops(adjacency: Dict[str, List[str]], src: str, dst: str) -> int:
    if src == dst:
        return 0
    queue = deque([(src, 0)])
    seen = {src}
    while queue:
        node, hops = queue.popleft()
        for neighbor in adjacency.get(node, []):
            if neighbor == dst:
                return hops + 1
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append((neighbor, hops + 1))
    raise ValueError(f"No optical path between {src} and {dst}.")


def _normalize_matrix(rows: List[dict]) -> List[dict]:
    total_weight = sum(float(row["weight"]) for row in rows)
    if total_weight <= 0:
        raise ValueError("Traffic matrix has zero total weight.")
    for row in rows:
        row["probability"] = f"{float(row['weight']) / total_weight:.8f}"
    return rows


def build_bg_optical_traffic_matrix() -> List[dict]:
    optical_nodes = read_csv(cfg.OPTICAL_NODES_FILE)
    adjacency = _build_optical_adjacency()
    degrees = {node["optical_node_id"]: len(adjacency[node["optical_node_id"]]) for node in optical_nodes}

    rows = []
    for src in optical_nodes:
        for dst in optical_nodes:
            src_id = src["optical_node_id"]
            dst_id = dst["optical_node_id"]
            if src_id == dst_id:
                continue
            hops = _shortest_hops(adjacency, src_id, dst_id)
            direct_bonus = 2.0 if dst_id in adjacency[src_id] else 1.0
            weight = direct_bonus * (degrees[src_id] + 1) * (degrees[dst_id] + 1) / (hops ** 2)
            rows.append(
                {
                    "traffic_type": "BG",
                    "src_optical_node_id": src_id,
                    "dst_optical_node_id": dst_id,
                    "shortest_hops": hops,
                    "weight": f"{weight:.6f}",
                }
            )
    return _normalize_matrix(rows)


def _ip_to_optical_map() -> Dict[str, str]:
    return {
        row["ip_node_id"]: row["optical_node_id"]
        for row in read_csv(cfg.IP_OPTICAL_MAPPING_FILE)
    }


def build_h_optical_traffic_matrix() -> List[dict]:
    adjacency = _build_optical_adjacency()
    ip_to_optical = _ip_to_optical_map()
    peerings = read_csv(cfg.CDN_IP_MAPPING_FILE)
    users = read_csv(cfg.END_USER_IP_MAPPING_FILE)

    rows = []
    for peering in peerings:
        src_optical = ip_to_optical[peering["peering_ip_node_id"]]
        peering_capacity = float(peering["peering_capacity_gbps"])
        for user in users:
            dst_optical = ip_to_optical[user["ip_node_id"]]
            if src_optical == dst_optical:
                continue
            hops = _shortest_hops(adjacency, src_optical, dst_optical)
            user_scale = float(user["demand_scale_gbps"])
            weight = peering_capacity * user_scale / (hops ** 2)
            rows.append(
                {
                    "traffic_type": "H",
                    "hypergiant_id": peering["hypergiant_id"],
                    "cdn_node_id": peering["cdn_node_id"],
                    "end_user_node_id": user["end_user_node_id"],
                    "src_ip_node_id": peering["peering_ip_node_id"],
                    "dst_ip_node_id": user["ip_node_id"],
                    "src_optical_node_id": src_optical,
                    "dst_optical_node_id": dst_optical,
                    "shortest_hops": hops,
                    "weight": f"{weight:.6f}",
                }
            )
    return _normalize_matrix(rows)


def _weibull_shape_for_cv(target_cv: float) -> float:
    if target_cv <= 0:
        raise ValueError("BANDWIDTH_WEIBULL_CV must be positive.")

    def cv_for_shape(shape: float) -> float:
        g1 = math.gamma(1.0 + 1.0 / shape)
        g2 = math.gamma(1.0 + 2.0 / shape)
        return math.sqrt(g2 / (g1 * g1) - 1.0)

    low = 0.1
    high = 100.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if cv_for_shape(mid) > target_cv:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _sample_duration(generator) -> float:
    while True:
        value = generator.expovariate(1.0 / cfg.MEAN_CONNECTION_DURATION)
        if cfg.MIN_CONNECTION_DURATION <= value <= cfg.MAX_CONNECTION_DURATION:
            return value


def _sample_bandwidth(generator) -> float:
    shape = _weibull_shape_for_cv(cfg.BANDWIDTH_WEIBULL_CV)
    scale = cfg.MEAN_CONNECTION_BANDWIDTH_GBPS / math.gamma(1.0 + 1.0 / shape)
    return generator.weibullvariate(scale, shape)


def _choose_matrix_row(matrix_rows: Sequence[dict], cumulative_probs: Sequence[float], generator) -> dict:
    value = generator.random()
    index = bisect.bisect_left(cumulative_probs, value)
    if index >= len(matrix_rows):
        index = len(matrix_rows) - 1
    return matrix_rows[index]


def generate_dynamic_requests(
    traffic_type: str,
    matrix_rows: Sequence[dict],
    traffic_share: float,
    seed_salt: int,
) -> List[dict]:
    if not 0.0 <= cfg.DYNAMIC_LOAD_FACTOR <= 1.0:
        raise ValueError("DYNAMIC_LOAD_FACTOR must be in [0, 1].")
    if traffic_share < 0.0:
        raise ValueError("traffic_share must be non-negative.")

    generator = rng(cfg.RANDOM_SEED, seed_salt)
    arrival_rate = cfg.DYNAMIC_FULL_LOAD_ARRIVAL_RATE * cfg.DYNAMIC_LOAD_FACTOR * traffic_share
    if arrival_rate <= 0.0:
        return []

    cumulative = []
    running = 0.0
    for row in matrix_rows:
        running += float(row["probability"])
        cumulative.append(running)
    cumulative[-1] = 1.0

    current_time = 0.0
    requests = []
    request_index = 0
    while True:
        current_time += generator.expovariate(arrival_rate)
        if current_time > cfg.DYNAMIC_TIME_HORIZON:
            break

        matrix_row = _choose_matrix_row(matrix_rows, cumulative, generator)
        duration = _sample_duration(generator)
        bandwidth = _sample_bandwidth(generator)
        request = {
            "request_id": f"{traffic_type.lower()}_dyn_{request_index}",
            "traffic_type": traffic_type,
            "arrival_time": f"{current_time:.3f}",
            "duration": f"{duration:.3f}",
            "end_time": f"{current_time + duration:.3f}",
            "bandwidth_gbps": f"{bandwidth:.3f}",
            "src_optical_node_id": matrix_row["src_optical_node_id"],
            "dst_optical_node_id": matrix_row["dst_optical_node_id"],
            "shortest_hops": matrix_row["shortest_hops"],
        }
        for optional_key in [
            "hypergiant_id",
            "cdn_node_id",
            "end_user_node_id",
            "src_ip_node_id",
            "dst_ip_node_id",
        ]:
            if optional_key in matrix_row:
                request[optional_key] = matrix_row[optional_key]
        requests.append(request)
        request_index += 1

    return requests


def dynamic_request_fieldnames(include_h_fields: bool) -> List[str]:
    fields = [
        "request_id",
        "traffic_type",
        "arrival_time",
        "duration",
        "end_time",
        "bandwidth_gbps",
    ]
    if include_h_fields:
        fields.extend(
            [
                "hypergiant_id",
                "cdn_node_id",
                "end_user_node_id",
                "src_ip_node_id",
                "dst_ip_node_id",
            ]
        )
    fields.extend(["src_optical_node_id", "dst_optical_node_id", "shortest_hops"])
    return fields


def write_bg_dynamic_outputs() -> List[dict]:
    matrix = build_bg_optical_traffic_matrix()
    requests = generate_dynamic_requests(
        "BG",
        matrix,
        1.0 - cfg.DYNAMIC_H_TRAFFIC_SHARE,
        seed_salt=2101,
    )
    write_csv(
        cfg.BG_DYNAMIC_TRAFFIC_MATRIX_FILE,
        matrix,
        [
            "traffic_type",
            "src_optical_node_id",
            "dst_optical_node_id",
            "shortest_hops",
            "weight",
            "probability",
        ],
    )
    write_csv(
        cfg.BG_DYNAMIC_REQUESTS_FILE,
        requests,
        dynamic_request_fieldnames(include_h_fields=False),
    )
    return requests


def write_h_dynamic_outputs() -> List[dict]:
    matrix = build_h_optical_traffic_matrix()
    requests = generate_dynamic_requests(
        "H",
        matrix,
        cfg.DYNAMIC_H_TRAFFIC_SHARE,
        seed_salt=2201,
    )
    write_csv(
        cfg.H_DYNAMIC_TRAFFIC_MATRIX_FILE,
        matrix,
        [
            "traffic_type",
            "hypergiant_id",
            "cdn_node_id",
            "end_user_node_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "src_optical_node_id",
            "dst_optical_node_id",
            "shortest_hops",
            "weight",
            "probability",
        ],
    )
    write_csv(
        cfg.H_DYNAMIC_REQUESTS_FILE,
        requests,
        dynamic_request_fieldnames(include_h_fields=True),
    )
    return requests
