from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx

from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.model.lightpath import Lightpath
from src_hung.model.state import MultiLayerState


@dataclass
class LNSRepairStats:
    iterations: int = 0
    candidate_moves: int = 0
    accepted_moves: int = 0
    rejected_infeasible: int = 0
    repair_success: int = 0
    repair_fail: int = 0
    pruned_lightpaths: int = 0
    best_cost_history: list[float] = field(default_factory=list)


class CrossLayerLNSRepair:
    """
    Fast large-neighborhood search for the current cross-layer model.

    The controller chooses a small neighborhood at the IP layer, changes one
    demand route, then runs deterministic repair:
      1. add lightpaths only on IP links with missing capacity;
      2. remove lightpaths that are provably excess;
      3. accept only hard-feasible states that improve the true objective.

    This keeps the same feasibility contract as SA because every accepted state
    is evaluated by CostCalculator.
    """

    def __init__(
        self,
        initial_state: MultiLayerState,
        demands,
        ip_graph: nx.DiGraph,
        opt_graph: nx.DiGraph,
        ip_to_opt_map: dict[int, int],
        cost_calculator,
        spectrum_allocator: SpectrumAllocator,
        lightpath_capacity: float = 80,
        max_ip_paths: int = 10,
        max_optical_paths: int = 10,
        max_destroy_candidates: int = 8,
        repack_trials: int = 8,
        seed: int | None = None,
    ) -> None:
        self.initial_state = initial_state.deepcopy()
        self.current_state = initial_state.deepcopy()
        self.best_state = initial_state.deepcopy()

        self.demands = list(demands)
        self.demand_by_id = {d.id: d for d in self.demands}
        self.ip_graph = ip_graph
        self.opt_graph = opt_graph
        self.ip_to_opt_map = ip_to_opt_map
        self.cost_calculator = cost_calculator
        self.spectrum_allocator = spectrum_allocator
        self.lightpath_capacity = lightpath_capacity
        self.max_ip_paths = max_ip_paths
        self.max_optical_paths = max_optical_paths
        self.max_destroy_candidates = max_destroy_candidates
        self.repack_trials = repack_trials
        self.rng = random.Random(seed)

        self._ip_path_cache: dict[str, list[list[int]]] = {}
        self._opt_path_cache: dict[tuple[int, int], list[list[int]]] = {}
        self.stats = LNSRepairStats()

    def run(self, max_iterations: int = 60) -> MultiLayerState:
        current_cost = self.cost_calculator.calculate_objective(self.current_state)
        if not math.isfinite(current_cost):
            raise ValueError("Initial state is infeasible, LNS-Repair needs a feasible start.")

        best_cost = current_cost
        self.stats.best_cost_history.append(best_cost)

        for _ in range(max(1, max_iterations)):
            self.stats.iterations += 1
            current_key = self._state_key(self.current_state)
            candidate, candidate_key = self._best_neighbor(self.current_state, current_key)

            if candidate is None:
                break

            self.current_state = candidate
            current_cost = candidate_key[0]
            self.stats.accepted_moves += 1

            if current_cost < best_cost:
                self.best_state = candidate.deepcopy()
                best_cost = current_cost

            self.stats.best_cost_history.append(best_cost)

        return self.best_state

    def _best_neighbor(
        self,
        state: MultiLayerState,
        current_key: tuple[float, float, float, float],
    ) -> tuple[MultiLayerState | None, tuple[float, float, float, float]]:
        best_candidate = None
        best_key = current_key

        for demand in self._rank_demands_for_destroy(state):
            current_edges = set(state.get_demand_edges(demand.id))
            paths = self._candidate_ip_paths(demand)

            for path in paths:
                path_edges = self._path_edges(path)
                if set(path_edges) == current_edges:
                    continue

                self.stats.candidate_moves += 1
                candidate = state.deepcopy()
                candidate.set_demand_path(demand.id, path)

                if not self._repair_capacity(candidate):
                    self.stats.rejected_infeasible += 1
                    continue

                self._prune_excess_lightpaths(candidate)

                key = self._state_key(candidate)
                if not math.isfinite(key[0]):
                    self.stats.rejected_infeasible += 1
                    continue

                if key < best_key:
                    best_candidate = candidate
                    best_key = key

        for candidate in self._route_repacking_neighbors(state):
            key = self._state_key(candidate)
            if not math.isfinite(key[0]):
                self.stats.rejected_infeasible += 1
                continue

            if key < best_key:
                best_candidate = candidate
                best_key = key

        if best_candidate is None:
            return None, current_key

        return best_candidate, best_key

    def _state_key(self, state: MultiLayerState) -> tuple[float, float, float, float]:
        cost, details = self.cost_calculator.calculate_objective(state, return_details=True)
        if not math.isfinite(cost):
            return (math.inf, math.inf, math.inf, math.inf)

        return (
            float(cost),
            self._capacity_waste_score(state),
            self._fragmentation_score(state),
            float(details.get("reconfiguration_distance", 0)),
        )

    def _rank_demands_for_destroy(self, state: MultiLayerState):
        traffic = self._traffic_on_ip_links(state)
        ranked = []

        for demand in self.demands:
            score = 0.0
            for ip_link in state.get_demand_edges(demand.id):
                load = traffic.get(ip_link, 0.0)
                before = self._required_lightpaths(load)
                after = self._required_lightpaths(max(0.0, load - demand.bandwidth))
                installed = self._installed_lightpath_count(state, ip_link)
                score += 10.0 * max(0, before - after)
                score += max(0.0, installed * self.lightpath_capacity - load) / self.lightpath_capacity

            ranked.append((score, self.rng.random(), demand))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[: self.max_destroy_candidates]]

    def _route_repacking_neighbors(self, state: MultiLayerState):
        ranked = self._rank_demands_for_destroy(state)
        if not ranked:
            return

        orders = [
            ranked,
            list(reversed(ranked)),
        ]
        for _ in range(max(0, self.repack_trials - len(orders))):
            order = ranked[:]
            self.rng.shuffle(order)
            orders.append(order)

        seen_orders = set()
        for order in orders:
            order_key = tuple(d.id for d in order)
            if order_key in seen_orders:
                continue
            seen_orders.add(order_key)

            candidate = state.deepcopy()
            changed = False

            for demand in order:
                best_path = None
                best_key = self._route_lower_bound_key(candidate)
                current_edges = set(candidate.get_demand_edges(demand.id))

                for path in self._candidate_ip_paths(demand):
                    path_edges = self._path_edges(path)
                    if set(path_edges) == current_edges:
                        continue

                    trial = candidate.deepcopy()
                    trial.set_demand_path(demand.id, path)
                    route_len = sum(self.ip_graph[u][v].get("weight", 1) for u, v in path_edges)
                    key = self._route_lower_bound_key(trial) + (route_len,)
                    if key < best_key + (math.inf,):
                        best_path = path
                        best_key = key[:-1]

                if best_path is not None:
                    candidate.set_demand_path(demand.id, best_path)
                    changed = True

            if not changed:
                continue

            self.stats.candidate_moves += 1
            if not self._repair_capacity(candidate):
                self.stats.rejected_infeasible += 1
                continue

            self._prune_excess_lightpaths(candidate)
            yield candidate

    def _repair_capacity(self, state: MultiLayerState) -> bool:
        for _ in range(len(self.ip_graph.edges()) + len(self.demands) + 10):
            deficit_links = self._capacity_deficits(state)
            if not deficit_links:
                self.stats.repair_success += 1
                return True

            ip_link, _deficit = deficit_links[0]
            if not self._add_lightpath_for_ip_link(state, ip_link):
                self.stats.repair_fail += 1
                return False

        self.stats.repair_fail += 1
        return False

    def _capacity_deficits(self, state: MultiLayerState) -> list[tuple[tuple[int, int], float]]:
        traffic = self._traffic_on_ip_links(state)
        deficits = []

        for ip_link, load in traffic.items():
            installed = self._installed_capacity(state, ip_link)
            deficit = load - installed
            if deficit > 1e-9:
                deficits.append((ip_link, deficit))

        deficits.sort(key=lambda item: item[1], reverse=True)
        return deficits

    def _route_lower_bound_key(self, state: MultiLayerState) -> tuple[int, float]:
        traffic = self._traffic_on_ip_links(state)
        required = sum(self._required_lightpaths(load) for load in traffic.values())
        waste = sum(
            self._required_lightpaths(load) * self.lightpath_capacity - load
            for load in traffic.values()
        )
        return required, waste

    def _capacity_waste_score(self, state: MultiLayerState) -> float:
        traffic = self._traffic_on_ip_links(state)
        ip_links = set(traffic.keys())
        ip_links.update(lp.ip_link for lp in state.lightpath_info.values())

        waste = 0.0
        for ip_link in ip_links:
            waste += max(0.0, self._installed_capacity(state, ip_link) - traffic.get(ip_link, 0.0))
        return waste

    def _prune_excess_lightpaths(self, state: MultiLayerState) -> None:
        changed = True
        while changed:
            changed = False
            traffic = self._traffic_on_ip_links(state)
            lp_ids = list(state.lightpath_info.keys())
            lp_ids.sort(
                key=lambda lp_id: self._lightpath_remove_score(state, lp_id, traffic),
                reverse=True,
            )

            for lp_id in lp_ids:
                lp = state.lightpath_info.get(lp_id)
                if lp is None:
                    continue

                load = traffic.get(lp.ip_link, 0.0)
                remaining_capacity = self._installed_capacity(state, lp.ip_link) - self.lightpath_capacity
                if load > remaining_capacity + 1e-9:
                    continue

                candidate = state.deepcopy()
                candidate.remove_lightpath(lp_id)
                if self.cost_calculator.is_feasible(candidate):
                    self._replace_state_contents(state, candidate)
                    self.stats.pruned_lightpaths += 1
                    changed = True
                    break

    def _lightpath_remove_score(
        self,
        state: MultiLayerState,
        lp_id: int,
        traffic: dict[tuple[int, int], float],
    ) -> float:
        lp = state.lightpath_info[lp_id]
        load = traffic.get(lp.ip_link, 0.0)
        spare = self._installed_capacity(state, lp.ip_link) - load
        optical_len = sum(self.opt_graph[u][v].get("weight", 1) for u, v in lp.opt_edges)
        return spare / max(self.lightpath_capacity, 1e-9) + 0.001 * optical_len

    def _add_lightpath_for_ip_link(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> bool:
        u_ip, v_ip = ip_link
        if u_ip not in self.ip_to_opt_map or v_ip not in self.ip_to_opt_map:
            return False

        opt_src = self.ip_to_opt_map[u_ip]
        opt_dst = self.ip_to_opt_map[v_ip]

        for opt_path in self._candidate_optical_paths(opt_src, opt_dst):
            opt_edges = self._path_edges(opt_path)
            ok, slot = self.spectrum_allocator.find_available_slot(
                state=state,
                path_edges=opt_edges,
                required_slots=1,
            )
            if not ok:
                continue

            lp = Lightpath(
                id=state.next_lightpath_id,
                ip_link=ip_link,
                opt_path=opt_path,
                slot_start=slot,
                slots=1,
                path_id=self._path_id_for_opt_path(state, ip_link, opt_path),
            )
            state.add_lightpath(lp)
            return True

        return False

    def _candidate_ip_paths(self, demand) -> list[list[int]]:
        if demand.id not in self._ip_path_cache:
            try:
                paths = []
                generator = nx.shortest_simple_paths(
                    self.ip_graph,
                    demand.s,
                    demand.t,
                    weight="weight",
                )
                for _, path in zip(range(self.max_ip_paths), generator):
                    paths.append(path)
                self._ip_path_cache[demand.id] = paths
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._ip_path_cache[demand.id] = []

        return self._ip_path_cache[demand.id]

    def _candidate_optical_paths(self, source: int, target: int) -> list[list[int]]:
        key = (source, target)
        if key not in self._opt_path_cache:
            try:
                paths = []
                generator = nx.shortest_simple_paths(
                    self.opt_graph,
                    source,
                    target,
                    weight="weight",
                )
                for _, path in zip(range(self.max_optical_paths), generator):
                    paths.append(path)
                self._opt_path_cache[key] = paths
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._opt_path_cache[key] = []

        return self._opt_path_cache[key]

    def _fragmentation_score(self, state: MultiLayerState) -> float:
        occupied_by_edge = self.spectrum_allocator._occupied_slots_by_edge(state)
        score = 0.0

        for edge in self.opt_graph.edges():
            occupied = occupied_by_edge.get(edge, set())
            free_runs = self._free_slot_runs(occupied)
            if not free_runs:
                score += self.spectrum_allocator.num_slots
                continue

            total_free = sum(free_runs)
            largest_free = max(free_runs)
            score += total_free - largest_free

        return score

    def _free_slot_runs(self, occupied: set[int]) -> list[int]:
        runs = []
        current = 0
        for slot in range(self.spectrum_allocator.num_slots):
            if slot in occupied:
                if current:
                    runs.append(current)
                    current = 0
            else:
                current += 1

        if current:
            runs.append(current)
        return runs

    def _traffic_on_ip_links(
        self,
        state: MultiLayerState,
    ) -> dict[tuple[int, int], float]:
        traffic = {}
        for (d_id, u, v), val in state.x.items():
            if val != 1 or d_id not in self.demand_by_id:
                continue
            traffic[(u, v)] = traffic.get((u, v), 0.0) + self.demand_by_id[d_id].bandwidth
        return traffic

    def _installed_lightpath_count(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> int:
        u, v = ip_link
        return sum(
            max(0, count)
            for (uu, vv, _), count in state.y.items()
            if uu == u and vv == v
        )

    def _installed_capacity(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> float:
        return self._installed_lightpath_count(state, ip_link) * self.lightpath_capacity

    def _required_lightpaths(self, load: float) -> int:
        if load <= 1e-9:
            return 0
        return int(math.ceil(load / self.lightpath_capacity))

    def _path_id_for_opt_path(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
        opt_path: list[int],
    ) -> int:
        existing_ids = []
        for lp in state.lightpath_info.values():
            if lp.ip_link != ip_link:
                continue
            existing_ids.append(lp.path_id)
            if lp.opt_path == opt_path:
                return lp.path_id

        for (u, v, path_id), _ in state.y.items():
            if (u, v) == ip_link:
                existing_ids.append(path_id)

        return max(existing_ids, default=-1) + 1

    @staticmethod
    def _path_edges(path: Iterable[int]) -> list[tuple[int, int]]:
        path = list(path)
        return [(path[i], path[i + 1]) for i in range(len(path) - 1)]

    @staticmethod
    def _replace_state_contents(target: MultiLayerState, source: MultiLayerState) -> None:
        target.x = source.x
        target.y = source.y
        target.z = source.z
        target.s = source.s
        target.y0 = source.y0
        target.q0 = source.q0
        target.lightpath_info = source.lightpath_info
        target.next_lightpath_id = source.next_lightpath_id
