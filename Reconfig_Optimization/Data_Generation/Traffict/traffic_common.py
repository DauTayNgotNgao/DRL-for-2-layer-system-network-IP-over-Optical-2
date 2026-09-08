# Noi dung/Muc dich:
# Cac ham dung chung cho initial traffic: tao BG/H demands ngau nhien, chon
# peering cho hyper-giant, route greedy tren initial IP topology, mo them
# lightpaths khi capacity tren IP link khong du, va block demand neu tai
# nguyen optical fiber hoac IP transceiver da cham gioi han.

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, List, Sequence, Tuple

import Config as cfg
from topology_common import read_csv, rng, write_csv


LinkKey = Tuple[str, str]


def link_key(src: str, dst: str) -> LinkKey:
    return tuple(sorted((src, dst)))


def load_ip_graph() -> Tuple[Dict[str, List[str]], Dict[LinkKey, dict]]:
    links = read_csv(cfg.IP_LINKS_FILE)
    adjacency: Dict[str, List[str]] = defaultdict(list)
    link_by_pair: Dict[LinkKey, dict] = {}
    for row in links:
        src = row["src_ip_node_id"]
        dst = row["dst_ip_node_id"]
        adjacency[src].append(dst)
        adjacency[dst].append(src)
        link_by_pair[link_key(src, dst)] = row

    for neighbors in adjacency.values():
        neighbors.sort()
    return dict(adjacency), link_by_pair


def load_lightpath_state() -> Dict[str, dict]:
    lightpaths = {}
    for row in read_csv(cfg.BASELINE_IP_LIGHTPATHS_FILE):
        num_lightpaths = int(row["num_lightpaths"])
        lightpaths[row["ip_link_id"]] = {
            "ip_link_id": row["ip_link_id"],
            "src_ip_node_id": row["src_ip_node_id"],
            "dst_ip_node_id": row["dst_ip_node_id"],
            "selected_path_id": row["selected_path_id"],
            "initial_lightpaths": num_lightpaths,
            "num_lightpaths": num_lightpaths,
            "load_gbps": 0.0,
        }

    optical_link_capacity = {
        row["optical_link_id"]: int(row["fiber_capacity_lightpaths"])
        for row in read_csv(cfg.OPTICAL_LINKS_FILE)
    }
    ip_link_segments: Dict[str, List[str]] = defaultdict(list)
    optical_link_usage: Dict[str, int] = defaultdict(int)
    for row in read_csv(cfg.BASELINE_OPTICAL_LIGHTPATHS_FILE):
        optical_link_id = row["optical_link_id"]
        if optical_link_id == "local_collocation":
            continue
        ip_link_id = row["ip_link_id"]
        ip_link_segments[ip_link_id].append(optical_link_id)
        optical_link_usage[optical_link_id] += lightpaths[ip_link_id]["num_lightpaths"]

    ip_node_usage: Dict[str, int] = defaultdict(int)
    for row in lightpaths.values():
        ip_node_usage[row["src_ip_node_id"]] += row["num_lightpaths"]
        ip_node_usage[row["dst_ip_node_id"]] += row["num_lightpaths"]

    return {
        "lightpaths": lightpaths,
        "ip_link_segments": dict(ip_link_segments),
        "optical_link_usage": dict(optical_link_usage),
        "optical_link_capacity": optical_link_capacity,
        "ip_node_usage": dict(ip_node_usage),
    }


def random_ip_path(
    adjacency: Dict[str, List[str]],
    src: str,
    dst: str,
    generator,
) -> List[str]:
    if src == dst:
        return [src]

    nodes_limit = max(2, len(adjacency))
    for _ in range(cfg.RANDOM_ROUTE_ATTEMPTS):
        current = src
        path = [src]
        visited = {src}
        for _ in range(nodes_limit):
            candidates = [node for node in adjacency.get(current, []) if node not in visited]
            if not candidates:
                break
            current = generator.choice(candidates)
            path.append(current)
            if current == dst:
                return path
            visited.add(current)

    return shortest_ip_path(adjacency, src, dst)


def shortest_ip_path(adjacency: Dict[str, List[str]], src: str, dst: str) -> List[str]:
    queue = deque([[src]])
    visited = {src}
    while queue:
        path = queue.popleft()
        current = path[-1]
        for neighbor in adjacency.get(current, []):
            if neighbor in visited:
                continue
            next_path = path + [neighbor]
            if neighbor == dst:
                return next_path
            visited.add(neighbor)
            queue.append(next_path)
    raise ValueError(f"No IP path found from {src} to {dst}; check initial IP topology.")


def _required_extra_lightpaths(link_state: dict, added_load_gbps: float) -> int:
    required_load = link_state["load_gbps"] + added_load_gbps
    usable_per_lightpath = cfg.LIGHTPATH_CAPACITY_GBPS * cfg.MAX_IP_LINK_UTILIZATION
    required_lightpaths = max(1, math.ceil(required_load / usable_per_lightpath))
    return max(0, required_lightpaths - link_state["num_lightpaths"])


def _block_reason_for_extra_lightpaths(
    state: Dict[str, dict],
    link_state: dict,
    extra_lightpaths: int,
) -> str:
    if extra_lightpaths <= 0:
        return ""

    src_ip = link_state["src_ip_node_id"]
    dst_ip = link_state["dst_ip_node_id"]
    ip_node_usage = state["ip_node_usage"]
    if ip_node_usage.get(src_ip, 0) + extra_lightpaths > cfg.IP_ROUTER_TRANSCEIVERS:
        return f"ip_transceiver_limit:{src_ip}"
    if ip_node_usage.get(dst_ip, 0) + extra_lightpaths > cfg.IP_ROUTER_TRANSCEIVERS:
        return f"ip_transceiver_limit:{dst_ip}"

    for optical_link_id in state["ip_link_segments"].get(link_state["ip_link_id"], []):
        used = state["optical_link_usage"].get(optical_link_id, 0)
        capacity = state["optical_link_capacity"][optical_link_id]
        if used + extra_lightpaths > capacity:
            return f"optical_fiber_limit:{optical_link_id}"

    return ""


def _block_reason_for_extra_plan(
    state: Dict[str, dict],
    required_extra_by_link: Sequence[Tuple[dict, int]],
) -> str:
    ip_node_delta: Dict[str, int] = defaultdict(int)
    optical_link_delta: Dict[str, int] = defaultdict(int)

    for link_state, extra_lightpaths in required_extra_by_link:
        if extra_lightpaths <= 0:
            continue
        ip_node_delta[link_state["src_ip_node_id"]] += extra_lightpaths
        ip_node_delta[link_state["dst_ip_node_id"]] += extra_lightpaths
        for optical_link_id in state["ip_link_segments"].get(link_state["ip_link_id"], []):
            optical_link_delta[optical_link_id] += extra_lightpaths

    for ip_node_id, delta in ip_node_delta.items():
        used = state["ip_node_usage"].get(ip_node_id, 0)
        if used + delta > cfg.IP_ROUTER_TRANSCEIVERS:
            return f"ip_transceiver_limit:{ip_node_id}"

    for optical_link_id, delta in optical_link_delta.items():
        used = state["optical_link_usage"].get(optical_link_id, 0)
        capacity = state["optical_link_capacity"][optical_link_id]
        if used + delta > capacity:
            return f"optical_fiber_limit:{optical_link_id}"

    return ""


def _apply_link_load(state: Dict[str, dict], link_state: dict, added_load_gbps: float) -> int:
    extra_lightpaths = _required_extra_lightpaths(link_state, added_load_gbps)
    if extra_lightpaths > 0:
        link_state["num_lightpaths"] += extra_lightpaths
        state["ip_node_usage"][link_state["src_ip_node_id"]] = (
            state["ip_node_usage"].get(link_state["src_ip_node_id"], 0) + extra_lightpaths
        )
        state["ip_node_usage"][link_state["dst_ip_node_id"]] = (
            state["ip_node_usage"].get(link_state["dst_ip_node_id"], 0) + extra_lightpaths
        )
        for optical_link_id in state["ip_link_segments"].get(link_state["ip_link_id"], []):
            state["optical_link_usage"][optical_link_id] = (
                state["optical_link_usage"].get(optical_link_id, 0) + extra_lightpaths
            )

    link_state["load_gbps"] += added_load_gbps
    return extra_lightpaths


def route_demands(
    demands: Sequence[dict],
    seed_salt: int,
    lightpath_state: Dict[str, dict] | None = None,
) -> Tuple[List[dict], Dict[str, dict]]:
    adjacency, link_by_pair = load_ip_graph()
    if lightpath_state is None:
        lightpath_state = load_lightpath_state()
    if "lightpaths" not in lightpath_state:
        lightpath_state = {
            "lightpaths": lightpath_state,
            "ip_link_segments": {},
            "optical_link_usage": {},
            "optical_link_capacity": {},
            "ip_node_usage": {},
        }
    generator = rng(cfg.RANDOM_SEED, salt=seed_salt)

    routed_rows = []
    for demand in demands:
        demand_gbps = float(demand["demand_gbps"])
        path = []
        traversed_links = []
        required_extra_by_link = []
        block_reason = "no_feasible_path"
        seen_paths = set()

        for _ in range(cfg.RANDOM_ROUTE_ATTEMPTS):
            candidate_path = random_ip_path(
                adjacency,
                demand["src_ip_node_id"],
                demand["dst_ip_node_id"],
                generator,
            )
            path_key = tuple(candidate_path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)

            candidate_links = []
            candidate_extra = []
            candidate_block_reason = ""

            for src, dst in zip(candidate_path, candidate_path[1:]):
                link = link_by_pair[link_key(src, dst)]
                candidate_links.append(link["ip_link_id"])
                link_state = lightpath_state["lightpaths"][link["ip_link_id"]]
                extra = _required_extra_lightpaths(link_state, demand_gbps)
                candidate_extra.append((link_state, extra))

            candidate_block_reason = _block_reason_for_extra_plan(
                lightpath_state,
                candidate_extra,
            )

            path = candidate_path
            traversed_links = candidate_links
            required_extra_by_link = candidate_extra
            block_reason = candidate_block_reason
            if not block_reason:
                break

        status = "blocked" if block_reason else "routed"
        opened_lightpaths = 0
        if status == "routed":
            for link_state, _ in required_extra_by_link:
                opened_lightpaths += _apply_link_load(lightpath_state, link_state, demand_gbps)

        routed_rows.append(
            {
                "demand_id": demand["demand_id"],
                "traffic_type": demand["traffic_type"],
                **{
                    key: demand[key]
                    for key in ["hypergiant_id", "cdn_node_id", "end_user_node_id"]
                    if key in demand
                },
                "src_ip_node_id": demand["src_ip_node_id"],
                "dst_ip_node_id": demand["dst_ip_node_id"],
                "demand_gbps": f"{demand_gbps:.3f}",
                "ip_path": "-".join(path),
                "ip_link_path": "-".join(traversed_links),
                "ip_hops": max(0, len(path) - 1),
                "opened_lightpaths": opened_lightpaths,
                "status": status,
                "block_reason": block_reason,
            }
        )

    return routed_rows, lightpath_state


def lightpath_load_rows(lightpath_state: Dict[str, dict]) -> List[dict]:
    if "lightpaths" in lightpath_state:
        lightpath_state = lightpath_state["lightpaths"]
    rows = []
    for link_id in sorted(lightpath_state):
        row = lightpath_state[link_id]
        capacity = row["num_lightpaths"] * cfg.LIGHTPATH_CAPACITY_GBPS
        usable_capacity = capacity * cfg.MAX_IP_LINK_UTILIZATION
        utilization = 0.0 if usable_capacity == 0 else row["load_gbps"] / usable_capacity
        rows.append(
            {
                "ip_link_id": row["ip_link_id"],
                "src_ip_node_id": row["src_ip_node_id"],
                "dst_ip_node_id": row["dst_ip_node_id"],
                "selected_path_id": row["selected_path_id"],
                "initial_lightpaths": row["initial_lightpaths"],
                "num_lightpaths": row["num_lightpaths"],
                "added_lightpaths": row["num_lightpaths"] - row["initial_lightpaths"],
                "capacity_gbps": capacity,
                "usable_capacity_gbps": f"{usable_capacity:.3f}",
                "load_gbps": f"{row['load_gbps']:.3f}",
                "utilization_of_allowed_capacity": f"{utilization:.3f}",
            }
        )
    return rows


def write_lightpath_loads(path, lightpath_state: Dict[str, dict]) -> None:
    write_csv(
        path,
        lightpath_load_rows(lightpath_state),
        [
            "ip_link_id",
            "src_ip_node_id",
            "dst_ip_node_id",
            "selected_path_id",
            "initial_lightpaths",
            "num_lightpaths",
            "added_lightpaths",
            "capacity_gbps",
            "usable_capacity_gbps",
            "load_gbps",
            "utilization_of_allowed_capacity",
        ],
    )


def resource_usage_rows(lightpath_state: Dict[str, dict]) -> List[dict]:
    rows = []
    for optical_link_id in sorted(lightpath_state["optical_link_capacity"]):
        capacity = lightpath_state["optical_link_capacity"][optical_link_id]
        used = lightpath_state["optical_link_usage"].get(optical_link_id, 0)
        rows.append(
            {
                "resource_type": "optical_fiber",
                "resource_id": optical_link_id,
                "used_lightpaths": used,
                "capacity_lightpaths": capacity,
                "free_lightpaths": capacity - used,
                "utilization": f"{0.0 if capacity == 0 else used / capacity:.3f}",
            }
        )

    for ip_node_id in sorted(lightpath_state["ip_node_usage"]):
        used = lightpath_state["ip_node_usage"].get(ip_node_id, 0)
        capacity = cfg.IP_ROUTER_TRANSCEIVERS
        rows.append(
            {
                "resource_type": "ip_transceiver",
                "resource_id": ip_node_id,
                "used_lightpaths": used,
                "capacity_lightpaths": capacity,
                "free_lightpaths": capacity - used,
                "utilization": f"{0.0 if capacity == 0 else used / capacity:.3f}",
            }
        )
    return rows


def write_resource_usage(path, lightpath_state: Dict[str, dict]) -> None:
    write_csv(
        path,
        resource_usage_rows(lightpath_state),
        [
            "resource_type",
            "resource_id",
            "used_lightpaths",
            "capacity_lightpaths",
            "free_lightpaths",
            "utilization",
        ],
    )


def generate_bg_demands() -> List[dict]:
    generator = rng(cfg.RANDOM_SEED, salt=1101)
    ip_nodes = read_csv(cfg.IP_NODES_FILE)
    ip_ids = [row["ip_node_id"] for row in ip_nodes]

    demands = []
    for index in range(cfg.INITIAL_BG_DEMAND_COUNT):
        src, dst = generator.sample(ip_ids, 2)
        demands.append(
            {
                "demand_id": f"bg_{index}",
                "traffic_type": "BG",
                "src_ip_node_id": src,
                "dst_ip_node_id": dst,
                "demand_gbps": generator.randint(
                    cfg.BG_TRAFFICT_MIN_GBPS,
                    cfg.BG_TRAFFICT_MAX_GBPS,
                ),
            }
        )
    return demands


def generate_h_demands() -> Tuple[List[dict], List[dict]]:
    generator = rng(cfg.RANDOM_SEED, salt=1201)
    user_mappings = read_csv(cfg.END_USER_IP_MAPPING_FILE)
    peering_rows = read_csv(cfg.CDN_IP_MAPPING_FILE)

    peerings_by_hg: Dict[str, List[dict]] = defaultdict(list)
    peering_loads = {}
    for row in peering_rows:
        peerings_by_hg[row["hypergiant_id"]].append(row)
        peering_loads[row["cdn_node_id"]] = {
            "cdn_node_id": row["cdn_node_id"],
            "hypergiant_id": row["hypergiant_id"],
            "peering_ip_node_id": row["peering_ip_node_id"],
            "peering_capacity_gbps": float(row["peering_capacity_gbps"]),
            "allocated_gbps": 0.0,
        }

    demands = []
    for demand_index in range(cfg.INITIAL_H_DEMAND_COUNT):
        hypergiant_id = cfg.HYPERGIANT_IDS[demand_index % len(cfg.HYPERGIANT_IDS)]
        peerings = peerings_by_hg.get(hypergiant_id, [])
        if not peerings:
            raise ValueError(f"Hypergiant {hypergiant_id} has no CDN peering rows.")

        user = generator.choice(user_mappings)
        demand_gbps = generator.randint(
            cfg.H_TRAFFICT_MIN_GBPS,
            cfg.H_TRAFFICT_MAX_GBPS,
        )
        candidates = [
            peering
            for peering in peerings
            if peering_loads[peering["cdn_node_id"]]["allocated_gbps"] + demand_gbps
            <= peering_loads[peering["cdn_node_id"]]["peering_capacity_gbps"]
        ]
        if not candidates:
            raise ValueError(
                f"Not enough peering capacity for {hypergiant_id}. "
                "Increase CDN_PEERINGS_PER_HYPERGIANT or peering capacity range, "
                "or reduce INITIAL_H_DEMAND_COUNT / H_TRAFFICT_* demand values."
            )

        peering = generator.choice(candidates)
        peering_loads[peering["cdn_node_id"]]["allocated_gbps"] += demand_gbps
        demands.append(
            {
                "demand_id": f"h_{demand_index}",
                "traffic_type": "H",
                "hypergiant_id": hypergiant_id,
                "cdn_node_id": peering["cdn_node_id"],
                "src_ip_node_id": peering["peering_ip_node_id"],
                "end_user_node_id": user["end_user_node_id"],
                "dst_ip_node_id": user["ip_node_id"],
                "demand_gbps": demand_gbps,
            }
        )

    peering_load_rows = []
    for row in peering_loads.values():
        utilization = row["allocated_gbps"] / row["peering_capacity_gbps"]
        peering_load_rows.append(
            {
                "cdn_node_id": row["cdn_node_id"],
                "hypergiant_id": row["hypergiant_id"],
                "peering_ip_node_id": row["peering_ip_node_id"],
                "peering_capacity_gbps": f"{row['peering_capacity_gbps']:.3f}",
                "allocated_gbps": f"{row['allocated_gbps']:.3f}",
                "peering_utilization": f"{utilization:.3f}",
            }
        )

    return demands, peering_load_rows
