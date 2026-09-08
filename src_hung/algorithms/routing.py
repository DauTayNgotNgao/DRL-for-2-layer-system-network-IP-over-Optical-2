import random
from itertools import islice

import networkx as nx

from src_hung.model.demand import Demand
from src_hung.model.state import MultiLayerState


class RoutingEngine:
    def __init__(self, ip_graph: nx.DiGraph):
        self.ip_graph = ip_graph

    def shortest_path(self, demand: Demand, weight: str = "weight") -> list[int] | None:
        try:
            return nx.shortest_path(
                self.ip_graph,
                source=demand.s,
                target=demand.t,
                weight=weight,
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def kth_shortest_path(
        self,
        demand: Demand,
        k: int = 5,
        weight: str = "weight",
    ) -> list[int] | None:
        """
        Lấy đường đi ngắn nhất thứ k trên tầng IP.

        Quy ước:
        - k = 1 tương đương shortest path.
        - Nếu không đủ k đường đi đơn giản thì lấy đường cuối cùng tìm được.
        """
        if k <= 1:
            return self.shortest_path(demand, weight=weight)

        try:
            generator = nx.shortest_simple_paths(
                self.ip_graph,
                source=demand.s,
                target=demand.t,
                weight=weight,
            )
            candidates = []
            for _, path in zip(range(k), generator):
                candidates.append(path)

            if not candidates:
                return None

            if len(candidates) >= k:
                return candidates[k - 1]

            return candidates[-1]

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def random_path(
        self,
        demand: Demand,
        max_candidates: int = 20,
        weight: str = "weight",
        seed: int | None = None,
    ) -> list[int] | None:
        rng = random.Random(seed)

        try:
            generator = nx.shortest_simple_paths(
                self.ip_graph,
                source=demand.s,
                target=demand.t,
                weight=weight,
            )

            candidates = []
            for _, path in zip(range(max_candidates), generator):
                candidates.append(path)

            if not candidates:
                return None

            return rng.choice(candidates)

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def apply_path(
        self,
        state: MultiLayerState,
        demand: Demand,
        path_nodes: list[int],
    ) -> None:
        if path_nodes is None or len(path_nodes) < 2:
            return

        state.set_demand_path(demand.id, path_nodes)

    def route_all_shortest(
        self,
        state: MultiLayerState,
        demands: list[Demand],
    ) -> None:
        for d in demands:
            path = self.shortest_path(d)
            if path is not None:
                self.apply_path(state, d, path)

    def route_all_kth_shortest(
        self,
        state: MultiLayerState,
        demands: list[Demand],
        k: int = 5,
    ) -> None:
        for d in demands:
            path = self.kth_shortest_path(d, k=k)
            if path is not None:
                self.apply_path(state, d, path)
    
