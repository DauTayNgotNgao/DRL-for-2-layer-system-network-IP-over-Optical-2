from __future__ import annotations

import math
import random

import networkx as nx

from src_hung.algorithms.routing import RoutingEngine
from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.model.lightpath import Lightpath
from src_hung.model.state import MultiLayerState


class CrossLayerSA:
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
        T_max: float = 1000.0,
        T_min: float = 1.0,
        cooling_rate: float = 0.95,
        iterations_per_temperature: int = 80,
        seed: int | None = None,
        allowed_actions: list[str] | None = None,
        phase_name: str = "GENERIC",
        repair_lightpaths_after_ip_reroute: bool = False,
    ):
        self.current_state = initial_state.deepcopy()
        self.best_state = initial_state.deepcopy()

        self.demands = demands
        self.ip_graph = ip_graph
        self.opt_graph = opt_graph
        self.ip_to_opt_map = ip_to_opt_map

        self.cost_calculator = cost_calculator
        self.spectrum_allocator = spectrum_allocator
        self.lightpath_capacity = lightpath_capacity

        self.T = T_max
        self.T_min = T_min
        self.cooling_rate = cooling_rate
        self.iterations_per_temperature = iterations_per_temperature

        self.rng = random.Random(seed)
        self.routing_engine = RoutingEngine(ip_graph)
        self.history: list[float] = []

        self.allowed_actions = allowed_actions or [
            "REROUTE_IP",
            "ADD_LIGHTPATH",
            "REMOVE_LIGHTPATH",
            "REROUTE_LIGHTPATH",
        ]
        self.phase_name = phase_name
        self.repair_lightpaths_after_ip_reroute = repair_lightpaths_after_ip_reroute

        self.stats = {
            "accepted_moves": 0,
            "rejected_infeasible_moves": 0,
            "mbb_attempts": 0,
            "mbb_success": 0,
            "mbb_failed_no_candidate": 0,
            "mbb_failed_no_spectrum": 0,
        }

    def run(self) -> MultiLayerState:
        current_cost = self.cost_calculator.calculate_objective(self.current_state)
        best_cost = self.cost_calculator.calculate_objective(self.best_state)

        if not math.isfinite(current_cost):
            raise ValueError(
                "Initial state is infeasible. With hard constraints, SA needs a feasible initial state."
            )

        self.history.append(best_cost)

        while self.T > self.T_min:
            for _ in range(self.iterations_per_temperature):
                new_state = self.generate_neighbor(self.current_state)
                new_cost = self.cost_calculator.calculate_objective(new_state)

                # Hard constraints: infeasible neighbor is rejected, not penalized.
                if not math.isfinite(new_cost):
                    self.stats["rejected_infeasible_moves"] += 1
                    continue

                delta = new_cost - current_cost

                if self._accept(delta):
                    self.current_state = new_state
                    current_cost = new_cost
                    self.stats["accepted_moves"] += 1

                    if current_cost < best_cost:
                        self.best_state = new_state.deepcopy()
                        best_cost = current_cost

            self.history.append(best_cost)
            self.T *= self.cooling_rate

        return self.best_state

    def _accept(self, delta: float) -> bool:
        if delta < 0:
            return True

        if self.T <= 0 or not math.isfinite(delta):
            return False

        try:
            probability = math.exp(-delta / self.T)
        except OverflowError:
            probability = 0.0

        return probability > self.rng.random()

    def generate_neighbor(self, state: MultiLayerState) -> MultiLayerState:
        new_state = state.deepcopy()
        action = self.rng.choice(self.allowed_actions)

        if action == "REROUTE_IP":
            self._neighbor_reroute_ip(new_state)
        elif action == "ADD_LIGHTPATH":
            self._neighbor_add_lightpath(new_state)
        elif action == "REMOVE_LIGHTPATH":
            self._neighbor_remove_lightpath(new_state)
        elif action == "REROUTE_LIGHTPATH":
            self._neighbor_reroute_lightpath_make_before_break(new_state)

        return new_state

    def _neighbor_reroute_ip(self, state: MultiLayerState) -> None:
        if not self.demands:
            return

        demand = self.rng.choice(self.demands)
        old_edges = state.get_demand_edges(demand.id)

        path = self.routing_engine.random_path(
            demand=demand,
            max_candidates=10,
            seed=self.rng.randint(0, 10**9),
        )

        if path is None:
            return

        state.set_demand_path(demand.id, path)

        # Không tự thêm/xóa lightpath ở đây. Nếu route mới thiếu capacity thì hard
        # constraint sẽ reject neighbor này. ADD_LIGHTPATH/REMOVE_LIGHTPATH xử lý tài nguyên.
        if self.repair_lightpaths_after_ip_reroute:
            self._repair_capacity_for_current_routes(state)

        # Tránh sinh đúng route cũ quá nhiều.
        if state.get_demand_edges(demand.id) == old_edges:
            return

    def _neighbor_add_lightpath(self, state: MultiLayerState) -> None:
        ip_link = self._choose_ip_link_for_new_lightpath(state)
        if ip_link is None:
            return
        self._add_lightpath_for_ip_link(state, ip_link)

    def _neighbor_remove_lightpath(self, state: MultiLayerState) -> None:
        """Chỉ xóa lightpath nếu sau khi xóa vẫn đủ capacity cho IP link đó."""
        if not state.lightpath_info:
            return

        traffic = self._traffic_on_ip_links(state)
        ids = list(state.lightpath_info.keys())
        self.rng.shuffle(ids)

        for k in ids:
            lp = state.lightpath_info[k]
            ip_link = lp.ip_link
            load = traffic.get(ip_link, 0.0)
            installed_after_remove = self._installed_capacity(state, ip_link) - self.lightpath_capacity

            if load <= installed_after_remove + 1e-9:
                state.remove_lightpath(k)
                return

    def _neighbor_reroute_lightpath_make_before_break(self, state: MultiLayerState) -> None:
        """
        Make-before-break cho optical lightpath:

        1. Giữ old lightpath đang chạy.
        2. Tìm optical path mới và slot mới trong khi old lightpath vẫn chiếm phổ.
        3. Nếu trạng thái trung gian old+new feasible về mapping/spectrum/capacity,
           mới remove old lightpath.
        4. Nếu không có path/slot hợp lệ, giữ nguyên state.
        """
        if not state.lightpath_info:
            return

        self.stats["mbb_attempts"] += 1
        candidate_ids = list(state.lightpath_info.keys())
        self.rng.shuffle(candidate_ids)

        found_candidate = False
        found_spectrum = False

        for old_id in candidate_ids:
            old_lp = state.lightpath_info.get(old_id)
            if old_lp is None:
                continue

            u_ip, v_ip = old_lp.ip_link
            if u_ip not in self.ip_to_opt_map or v_ip not in self.ip_to_opt_map:
                continue

            u_opt = self.ip_to_opt_map[u_ip]
            v_opt = self.ip_to_opt_map[v_ip]
            candidate_paths = self._candidate_optical_paths(u_opt, v_opt, max_candidates=10)
            candidate_paths = [p for p in candidate_paths if p != old_lp.opt_path]
            self.rng.shuffle(candidate_paths)

            if candidate_paths:
                found_candidate = True

            for opt_path in candidate_paths:
                opt_edges = self._path_edges(opt_path)
                ok, slot = self.spectrum_allocator.find_available_slot(
                    state=state,
                    path_edges=opt_edges,
                    required_slots=old_lp.slots,
                )

                if not ok:
                    continue

                found_spectrum = True
                new_lp = Lightpath(
                    id=state.next_lightpath_id,
                    ip_link=old_lp.ip_link,
                    opt_path=opt_path,
                    slot_start=slot,
                    slots=old_lp.slots,
                    path_id=self._path_id_for_opt_path(state, old_lp.ip_link, opt_path),
                )

                # MAKE: thêm lightpath mới khi old vẫn còn tồn tại.
                state.add_lightpath(new_lp)

                # Kiểm tra trạng thái trung gian old+new. Không check rho_limit ở
                # trạng thái trung gian vì MBB có thể tạm thời dùng thêm 1 LP.
                if not self.cost_calculator.is_feasible(state, check_reconfiguration=False):
                    state.remove_lightpath(new_lp.id)
                    continue

                # sau khi new LP đã feasible mới bỏ old LP.
                state.remove_lightpath(old_id)
                self.stats["mbb_success"] += 1
                return

        if not found_candidate:
            self.stats["mbb_failed_no_candidate"] += 1
        elif not found_spectrum:
            self.stats["mbb_failed_no_spectrum"] += 1

    def _repair_capacity_for_current_routes(self, state: MultiLayerState) -> None:
        traffic = self._traffic_on_ip_links(state)
        for ip_link, load in traffic.items():
            while load > self._installed_capacity(state, ip_link) + 1e-9:
                if not self._add_lightpath_for_ip_link(state, ip_link):
                    return

    def _choose_ip_link_for_new_lightpath(
        self,
        state: MultiLayerState,
    ) -> tuple[int, int] | None:
        traffic = self._traffic_on_ip_links(state)
        overloaded = []

        for ip_link, load in traffic.items():
            installed = self._installed_capacity(state, ip_link)
            if load > installed:
                overloaded.append(ip_link)

        if overloaded:
            return self.rng.choice(overloaded)

        used_links = list(traffic.keys())
        if used_links:
            return self.rng.choice(used_links)

        all_links = list(self.ip_graph.edges())
        if not all_links:
            return None
        return self.rng.choice(all_links)

    def _traffic_on_ip_links(
        self,
        state: MultiLayerState,
    ) -> dict[tuple[int, int], float]:
        traffic = {}
        demand_by_id = {d.id: d for d in self.demands}

        for (d_id, u, v), val in state.x.items():
            if val != 1 or d_id not in demand_by_id:
                continue
            traffic[(u, v)] = traffic.get((u, v), 0.0) + demand_by_id[d_id].bandwidth

        return traffic

    def _installed_capacity(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> float:
        u, v = ip_link
        count = 0

        for (uu, vv, _), y_val in state.y.items():
            if uu == u and vv == v:
                count += max(0, y_val)

        return count * self.lightpath_capacity

    def _add_lightpath_for_ip_link(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> bool:
        u_ip, v_ip = ip_link
        if u_ip not in self.ip_to_opt_map or v_ip not in self.ip_to_opt_map:
            return False

        u_opt = self.ip_to_opt_map[u_ip]
        v_opt = self.ip_to_opt_map[v_ip]
        candidate_paths = self._candidate_optical_paths(u_opt, v_opt, max_candidates=10)

        # Ưu tiên path ngắn trước, nhưng vẫn thử path khác nếu spectrum của path ngắn bị nghẽn.
        for opt_path in candidate_paths:
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

    def _candidate_optical_paths(
        self,
        source: int,
        target: int,
        max_candidates: int = 10,
    ) -> list[list[int]]:
        try:
            generator = nx.shortest_simple_paths(
                self.opt_graph,
                source=source,
                target=target,
                weight="weight",
            )
            paths = []
            for _, path in zip(range(max_candidates), generator):
                paths.append(path)
            return paths
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    @staticmethod
    def _path_edges(path: list[int]) -> list[tuple[int, int]]:
        return [(path[i], path[i + 1]) for i in range(len(path) - 1)]

    def _path_id_for_opt_path(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
        opt_path: list[int],
    ) -> int:
        """Dùng lại path_id nếu optical path đã tồn tại, nếu chưa thì cấp id mới."""
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
