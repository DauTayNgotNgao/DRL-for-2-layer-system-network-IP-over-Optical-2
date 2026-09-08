# Noi dung/Muc dich:
# Cac ham dung chung cho qua trinh sinh topology gia lap: doc/ghi CSV,
# validate du lieu, tinh khoang cach hinh hoc, tao graph connected, map node
# gan nhat va tinh k-shortest simple paths tren physical optical topology.

from __future__ import annotations

import csv
import heapq
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


Row = Dict[str, str]
Point = Tuple[float, float]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: Iterable[dict], fieldnames: Sequence[str]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path) -> List[Row]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file does not exist: {path}")
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def find_data_generation_dir(start_file: str) -> Path:
    current = Path(start_file).resolve()
    for parent in current.parents:
        if (parent / "Config.py").exists():
            return parent
    raise RuntimeError("Could not locate Data_Generation directory from script path.")


def rng(seed: int, salt: int = 0) -> random.Random:
    return random.Random(seed + salt)


def distance(a: dict, b: dict) -> float:
    return euclidean((float(a["x"]), float(a["y"])), (float(b["x"]), float(b["y"])))


def euclidean(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def random_point(generator: random.Random, width: float, height: float) -> Point:
    return generator.uniform(0.0, width), generator.uniform(0.0, height)


def jittered_point(
    generator: random.Random,
    base_x: float,
    base_y: float,
    jitter: float,
    width: float,
    height: float,
) -> Point:
    x = min(width, max(0.0, base_x + generator.uniform(-jitter, jitter)))
    y = min(height, max(0.0, base_y + generator.uniform(-jitter, jitter)))
    return x, y


def format_float(value: float) -> str:
    return f"{value:.3f}"


def validate_undirected_link_count(node_count: int, link_count: int, label: str) -> None:
    min_links = node_count - 1
    max_links = node_count * (node_count - 1) // 2
    if node_count <= 0:
        raise ValueError(f"{label}: node_count must be positive.")
    if link_count < min_links:
        raise ValueError(
            f"{label}: {link_count} links are too few for a connected graph. "
            f"Need at least {min_links} links for {node_count} nodes."
        )
    if link_count > max_links:
        raise ValueError(
            f"{label}: {link_count} links exceed the simple undirected maximum "
            f"{max_links} for {node_count} nodes."
        )


def generate_connected_edges(
    node_ids: Sequence[str],
    coordinates: Dict[str, Point],
    link_count: int,
    generator: random.Random,
) -> List[Tuple[str, str, float]]:
    validate_undirected_link_count(len(node_ids), link_count, "connected graph")

    shuffled = list(node_ids)
    generator.shuffle(shuffled)
    edges = set()

    # Connected base: random spanning tree.
    for idx in range(1, len(shuffled)):
        src = shuffled[idx]
        dst = generator.choice(shuffled[:idx])
        edges.add(tuple(sorted((src, dst))))

    # Extra links: prefer shorter geographic links, with random jitter.
    candidates = []
    for i, src in enumerate(node_ids):
        for dst in node_ids[i + 1 :]:
            edge = tuple(sorted((src, dst)))
            if edge in edges:
                continue
            length = euclidean(coordinates[src], coordinates[dst])
            score = length * generator.uniform(0.85, 1.15)
            candidates.append((score, edge))

    candidates.sort(key=lambda item: item[0])
    for _, edge in candidates:
        if len(edges) >= link_count:
            break
        edges.add(edge)

    rows = []
    for src, dst in sorted(edges):
        rows.append((src, dst, euclidean(coordinates[src], coordinates[dst])))
    return rows


def nearest_node(source: dict, targets: Sequence[dict]) -> Tuple[dict, float]:
    if not targets:
        raise ValueError("nearest_node requires at least one target.")
    target = min(targets, key=lambda row: distance(source, row))
    return target, distance(source, target)


def build_undirected_adjacency(
    link_rows: Sequence[dict],
    src_key: str,
    dst_key: str,
    length_key: str,
) -> Dict[str, List[Tuple[str, float, str]]]:
    adjacency: Dict[str, List[Tuple[str, float, str]]] = {}
    for row in link_rows:
        src = row[src_key]
        dst = row[dst_key]
        length = float(row[length_key])
        link_id = row.get("optical_link_id") or row.get("ip_link_id") or f"{src}--{dst}"
        adjacency.setdefault(src, []).append((dst, length, link_id))
        adjacency.setdefault(dst, []).append((src, length, link_id))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (item[1], item[0]))
    return adjacency


def k_shortest_simple_paths(
    adjacency: Dict[str, List[Tuple[str, float, str]]],
    src: str,
    dst: str,
    k: int,
) -> List[Tuple[List[str], float]]:
    if src == dst:
        return [([src], 0.0)]
    if src not in adjacency or dst not in adjacency:
        return []

    heap = [(0.0, src, [src])]
    results: List[Tuple[List[str], float]] = []
    seen_paths = set()

    while heap and len(results) < k:
        cost, node, path = heapq.heappop(heap)
        if node == dst:
            key = tuple(path)
            if key not in seen_paths:
                seen_paths.add(key)
                results.append((path, cost))
            continue

        for neighbor, edge_cost, _ in adjacency.get(node, []):
            if neighbor in path:
                continue
            heapq.heappush(heap, (cost + edge_cost, neighbor, path + [neighbor]))

    return results


def optical_edge_lookup(link_rows: Sequence[dict]) -> Dict[Tuple[str, str], str]:
    lookup: Dict[Tuple[str, str], str] = {}
    for row in link_rows:
        src = row["src_optical_node_id"]
        dst = row["dst_optical_node_id"]
        lookup[tuple(sorted((src, dst)))] = row["optical_link_id"]
    return lookup


def load_ip_to_optical(mapping_rows: Sequence[dict]) -> Dict[str, str]:
    return {
        row["ip_node_id"]: row["optical_node_id"]
        for row in mapping_rows
    }
