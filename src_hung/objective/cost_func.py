from __future__ import annotations

import math
from collections import defaultdict

import networkx as nx

from src_hung.model.demand import Demand
from src_hung.model.state import MultiLayerState


class CostCalculator:
    """
    Objective mới : minimize J = number_of_lightpaths
    """

    def __init__(
        self,
        demands: list[Demand],
        ip_graph: nx.DiGraph,
        opt_graph: nx.DiGraph,
        ip_to_opt_map: dict[int, int],
        lightpath_capacity: float = 80,
        num_slots: int = 100,
        weight_energy: float = 1.0,
        weight_latency: float = 0.0,
        p_transponder: float = 1.0,
        rho_limit: int | None = None,
        penalty_flow: float = 0.0,
        penalty_capacity: float = 0.0,
        penalty_spectrum: float = 0.0,
        penalty_lightpath_consistency: float = 0.0,
        penalty_non_disruptive: float = 0.0,
    ):
        self.demands = demands
        self.ip_graph = ip_graph
        self.opt_graph = opt_graph
        self.ip_to_opt_map = ip_to_opt_map

        self.lightpath_capacity = lightpath_capacity
        self.num_slots = num_slots
        self.p_transponder = p_transponder
        self.rho_limit = rho_limit

        # Giữ lại để tương thích cấu hình cũ. Không dùng trong objective.
        self.weight_energy = weight_energy
        self.weight_latency = weight_latency
        self.penalty_flow = penalty_flow
        self.penalty_capacity = penalty_capacity
        self.penalty_spectrum = penalty_spectrum
        self.penalty_lightpath_consistency = penalty_lightpath_consistency
        self.penalty_non_disruptive = penalty_non_disruptive

    def calculate_objective(
        self,
        state: MultiLayerState,
        return_details: bool = False,
    ):
        details = self.evaluate_constraints(state, check_reconfiguration=True)

        # Objective chỉ là số lightpath. Energy cost để report = p_transponder * số lightpath.
        total_lightpaths = len(state.lightpath_info)
        details["lightpaths"] = total_lightpaths
        details["energy_cost"] = self.p_transponder * total_lightpaths
        details["objective_cost"] = total_lightpaths

        # Các key cũ để không làm vỡ code vẽ CSV cũ, nhưng không còn ý nghĩa trong objective.
        details["delay_cost"] = 0.0
        details["penalty"] = 0.0
        details["penalty_flow"] = 0.0
        details["penalty_capacity"] = 0.0
        details["penalty_spectrum"] = 0.0
        details["penalty_lightpath_consistency"] = 0.0
        details["penalty_non_disruptive"] = 0.0

        total_cost = float(total_lightpaths) if details["feasible"] else math.inf

        if return_details:
            return total_cost, details

        return total_cost

    def is_feasible(
        self,
        state: MultiLayerState,
        check_reconfiguration: bool = True,
    ) -> bool:
        return self.evaluate_constraints(
            state,
            check_reconfiguration=check_reconfiguration,
        )["feasible"]

    def evaluate_constraints(
        self,
        state: MultiLayerState,
        check_reconfiguration: bool = True,
    ) -> dict:
        details = {
            "lightpaths": len(state.lightpath_info),
            "energy_cost": self.p_transponder * len(state.lightpath_info),
            "objective_cost": len(state.lightpath_info),
            "feasible": True,
            "constraint_violations": 0,
            "flow_violations": 0,
            "capacity_violations": 0,
            "capacity_excess_bandwidth": 0.0,
            "spectrum_violations": 0,
            "mapping_violations": 0,
            "z_consistency_violations": 0,
            "y_consistency_violations": 0,
            "non_disruptive_violations": 0,
            "reconfiguration_distance": 0,
            "rho_limit": self.rho_limit,
        }

        traffic_on_ip_link = defaultdict(float)

        # 1. Flow conservation + single path hợp lệ cho từng demand.
        for demand in self.demands:
            route_edges, ok = self._extract_valid_ordered_route(state, demand)
            if not ok:
                details["flow_violations"] += 1
                continue

            for u, v in route_edges:
                traffic_on_ip_link[(u, v)] += demand.bandwidth

        # 2. Capacity trên từng IP link.
        for ip_link, load in traffic_on_ip_link.items():
            installed = self._installed_capacity_on_ip_link(state, ip_link)
            excess = max(0.0, load - installed)
            if excess > 1e-9:
                details["capacity_violations"] += 1
                details["capacity_excess_bandwidth"] += excess

        # 3. y phải khớp với danh sách lightpath thật.
        details["y_consistency_violations"] = self._count_y_lightpath_inconsistency(state)

        # 4. Mapping, z và spectrum.
        mapping_v, z_v, spectrum_v = self._count_lightpath_mapping_z_spectrum_violations(state)
        details["mapping_violations"] = mapping_v
        details["z_consistency_violations"] = z_v
        details["spectrum_violations"] = spectrum_v

        # 5. Non-disruptive constraint theo y so với y0.
        details["reconfiguration_distance"] = self._reconfiguration_distance(state)
        if (
            check_reconfiguration
            and self.rho_limit is not None
            and details["reconfiguration_distance"] > self.rho_limit
        ):
            details["non_disruptive_violations"] = (
                details["reconfiguration_distance"] - self.rho_limit
            )

        details["constraint_violations"] = (
            details["flow_violations"]
            + details["capacity_violations"]
            + details["y_consistency_violations"]
            + details["mapping_violations"]
            + details["z_consistency_violations"]
            + details["spectrum_violations"]
            + details["non_disruptive_violations"]
        )
        details["feasible"] = details["constraint_violations"] == 0
        return details

    def _extract_valid_ordered_route(
        self,
        state: MultiLayerState,
        demand: Demand,
    ) -> tuple[list[tuple[int, int]], bool]:
        edges = state.get_demand_edges(demand.id)

        if not edges:
            return [], False

        outgoing = defaultdict(list)

        for u, v in edges:
            outgoing[u].append(v)
            if not self.ip_graph.has_edge(u, v):
                return [], False

        if len(outgoing[demand.s]) != 1:
            return [], False

        # Target không được có cạnh ra trong single-path route.
        if len(outgoing[demand.t]) != 0:
            return [], False

        ordered_edges = []
        visited_edges = set()
        current = demand.s

        for _ in range(len(edges) + 1):
            if current == demand.t:
                break

            if len(outgoing[current]) != 1:
                return [], False

            nxt = outgoing[current][0]
            edge = (current, nxt)

            if edge in visited_edges:
                return [], False

            visited_edges.add(edge)
            ordered_edges.append(edge)
            current = nxt

        if current != demand.t:
            return [], False

        if len(ordered_edges) != len(edges):
            return [], False

        return ordered_edges, True

    def _installed_capacity_on_ip_link(
        self,
        state: MultiLayerState,
        ip_link: tuple[int, int],
    ) -> float:
        u, v = ip_link
        count = 0

        for (uu, vv, _), value in state.y.items():
            if uu == u and vv == v:
                count += max(0, value)

        return count * self.lightpath_capacity

    def _count_y_lightpath_inconsistency(self, state: MultiLayerState) -> int:
        y_from_lightpaths = defaultdict(int)

        for lp in state.lightpath_info.values():
            u_ip, v_ip = lp.ip_link
            y_from_lightpaths[(u_ip, v_ip, lp.path_id)] += 1

        keys = set(state.y.keys()).union(y_from_lightpaths.keys())
        return sum(abs(state.y.get(key, 0) - y_from_lightpaths.get(key, 0)) for key in keys)

    def _count_lightpath_mapping_z_spectrum_violations(
        self,
        state: MultiLayerState,
    ) -> tuple[int, int, int]:
        mapping_violations = 0
        z_violations = 0
        spectrum_violations = 0
        used_slots = defaultdict(set)

        # z không được tham chiếu tới lightpath không tồn tại.
        for (k, _), val in state.z.items():
            if val == 1 and k not in state.lightpath_info:
                z_violations += 1

        for k, lp in state.lightpath_info.items():
            u_ip, v_ip = lp.ip_link

            if u_ip not in self.ip_to_opt_map or v_ip not in self.ip_to_opt_map:
                mapping_violations += 1
                continue

            expected_src = self.ip_to_opt_map[u_ip]
            expected_dst = self.ip_to_opt_map[v_ip]

            if not lp.opt_path or lp.opt_path[0] != expected_src or lp.opt_path[-1] != expected_dst:
                mapping_violations += 1

            for edge in lp.opt_edges:
                if not self.opt_graph.has_edge(*edge):
                    mapping_violations += 1

            expected_z_edges = set(lp.opt_edges)
            actual_z_edges = {
                edge
                for (kk, edge), val in state.z.items()
                if kk == k and val == 1
            }
            z_violations += len(expected_z_edges.symmetric_difference(actual_z_edges))

            if k not in state.s:
                spectrum_violations += 1
                continue

            start = state.s[k]
            end = start + lp.slots

            if lp.slots <= 0 or start < 0 or end > self.num_slots:
                spectrum_violations += 1
                continue

            for edge in lp.opt_edges:
                for slot in range(start, end):
                    if slot in used_slots[edge]:
                        spectrum_violations += 1
                    used_slots[edge].add(slot)

        return mapping_violations, z_violations, spectrum_violations

    def _reconfiguration_distance(self, state: MultiLayerState) -> int:
        """
        Global reconfiguration budget theo initial state:
            added_lightpaths + removed_lightpaths <= rho_limit

        Trước đây hàm này chỉ so sánh y với y0 theo số lượng lightpath trên
        từng (IP link, optical path id), nên không trùng với hình Added/Removed.
        Bây giờ nó dùng cùng signature với metric vẽ hình:
            (ip_link, optical_path, slot_start, slots)

        Nhờ vậy nếu candidate/best_state có add + removed > rho thì bị coi là
        infeasible và SA sẽ reject candidate đó.
        """
        current = state.lightpath_signature_counter()
        baseline = getattr(state, "q0", None)

        # Fallback cho state cũ chưa gọi set_baseline_y0().
        if not baseline:
            keys = set(state.y.keys()).union(state.y0.keys())
            return sum(abs(state.y.get(key, 0) - state.y0.get(key, 0)) for key in keys)

        keys = set(current.keys()).union(baseline.keys())
        return sum(abs(current.get(key, 0) - baseline.get(key, 0)) for key in keys)
