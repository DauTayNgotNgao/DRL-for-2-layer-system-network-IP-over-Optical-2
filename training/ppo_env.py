from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

import gymnasium as gym
import networkx as nx
import numpy as np
import torch
from gymnasium import spaces

from src_hung.algorithms.spectrum import SpectrumAllocator
from src_hung.model.lightpath import Lightpath


InstanceFactory = Callable[[], dict[str, Any]]


class CrossLayerPPOEnv(gym.Env):
    """Gymnasium environment whose policy reroutes demands without SA/LNS.

    An action is either STOP or ``(demand_index, candidate_path_rank)``.  After
    the policy changes an IP route, the environment performs only mandatory
    capacity/spectrum repair and removes provably redundant lightpaths.  A move
    is committed only when all project hard constraints remain satisfied.
    """

    metadata = {"render_modes": []}

    GLOBAL_FEATURES = 8
    DEMAND_FEATURES = 6

    def __init__(
        self,
        instance_factory: InstanceFactory,
        max_demands: int = 30,
        k_paths: int = 5,
        max_steps: int = 24,
        seed: int = 42,
    ) -> None:
        super().__init__()
        self.instance_factory = instance_factory
        self.max_demands = int(max_demands)
        self.k_paths = int(k_paths)
        self.max_steps = int(max_steps)
        self.base_seed = int(seed)

        self.action_space = spaces.Discrete(1 + self.max_demands * self.k_paths)
        obs_size = self.GLOBAL_FEATURES + self.max_demands * self.DEMAND_FEATURES
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(obs_size,), dtype=np.float32)

        self.initial_state = None
        self.state = None
        self.best_state = None
        self.demands = []
        self.demand_by_id = {}
        self.ip_graph = None
        self.opt_graph = None
        self.ip_to_opt_map = {}
        self.cost_calculator = None
        self.spectrum_allocator = None
        self.lightpath_capacity = 1.0
        self.initial_cost = 0.0
        self.current_cost = 0.0
        self.best_cost = 0.0
        self.step_count = 0
        self.accepted_moves = 0
        self.invalid_moves = 0
        self._ip_path_cache: dict[str, list[list[int]]] = {}
        self._opt_path_cache: dict[tuple[int, int], list[list[int]]] = {}

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        instance = self.instance_factory()
        self.initial_state = instance["initial_state"].deepcopy()
        self.state = self.initial_state.deepcopy()
        self.best_state = self.initial_state.deepcopy()
        self.demands = list(instance["demands"])
        if len(self.demands) > self.max_demands:
            raise ValueError(
                f"Instance has {len(self.demands)} demands but max_demands={self.max_demands}."
            )
        self.demand_by_id = {d.id: d for d in self.demands}
        self.ip_graph = instance["ip_graph"]
        self.opt_graph = instance["opt_graph"]
        self.ip_to_opt_map = instance["ip_to_opt_map"]
        self.cost_calculator = instance["cost_calculator"]
        self.spectrum_allocator = SpectrumAllocator(
            num_slots=int(instance["num_slots"]), guardband=0
        )
        self.lightpath_capacity = float(instance["lightpath_capacity"])
        self._ip_path_cache = {}
        self._opt_path_cache = {}
        self.initial_cost = float(self.cost_calculator.calculate_objective(self.state))
        if not math.isfinite(self.initial_cost):
            raise ValueError("PPO environment requires a feasible initial state.")
        self.current_cost = self.initial_cost
        self.best_cost = self.initial_cost
        self.step_count = 0
        self.accepted_moves = 0
        self.invalid_moves = 0
        return self._observation(), self._info()

    def step(self, action: int):
        self.step_count += 1
        terminated = int(action) == 0
        truncated = self.step_count >= self.max_steps
        reward = -0.01

        if not terminated:
            demand_index, path_rank = self._decode_action(int(action))
            candidate = self._candidate_from_action(demand_index, path_rank)
            if candidate is None:
                self.invalid_moves += 1
                reward = -0.25
            else:
                candidate_cost = float(self.cost_calculator.calculate_objective(candidate))
                if not math.isfinite(candidate_cost):
                    self.invalid_moves += 1
                    reward = -0.25
                else:
                    delta = self.current_cost - candidate_cost
                    self.state = candidate
                    self.current_cost = candidate_cost
                    self.accepted_moves += 1
                    reward = delta / max(self.initial_cost, 1.0) * 10.0 - 0.01
                    if candidate_cost < self.best_cost:
                        self.best_cost = candidate_cost
                        self.best_state = candidate.deepcopy()

        if terminated:
            reward += (self.initial_cost - self.best_cost) / max(self.initial_cost, 1.0)

        return self._observation(), float(reward), terminated, truncated, self._info()

    def action_masks(self) -> np.ndarray:
        mask = np.zeros(self.action_space.n, dtype=bool)
        mask[0] = True
        for demand_index, demand in enumerate(self.demands):
            current_edges = set(self.state.get_demand_edges(demand.id))
            for path_rank, path in enumerate(self._candidate_ip_paths(demand)):
                action = 1 + demand_index * self.k_paths + path_rank
                if set(self._path_edges(path)) != current_edges:
                    mask[action] = True
        return mask

    def _decode_action(self, action: int) -> tuple[int, int]:
        value = action - 1
        return value // self.k_paths, value % self.k_paths

    def _candidate_from_action(self, demand_index: int, path_rank: int):
        if demand_index >= len(self.demands):
            return None
        demand = self.demands[demand_index]
        paths = self._candidate_ip_paths(demand)
        if path_rank >= len(paths):
            return None
        path = paths[path_rank]
        if set(self._path_edges(path)) == set(self.state.get_demand_edges(demand.id)):
            return None

        candidate = self.state.deepcopy()
        candidate.set_demand_path(demand.id, path)
        if not self._repair_capacity(candidate):
            return None
        self._prune_excess_lightpaths(candidate)
        return candidate

    def _repair_capacity(self, state) -> bool:
        traffic = self._traffic_on_ip_links(state)
        installed_counts = Counter(lp.ip_link for lp in state.lightpath_info.values())
        deficits = []
        for edge, load in traffic.items():
            installed = installed_counts.get(edge, 0) * self.lightpath_capacity
            missing = max(0.0, load - installed)
            if missing > 1e-9:
                deficits.append((edge, int(math.ceil(missing / self.lightpath_capacity))))
        deficits.sort(key=lambda item: item[1], reverse=True)
        for edge, missing_count in deficits:
            for _ in range(missing_count):
                if not self._add_lightpath(state, edge):
                    return False
        return True

    def _prune_excess_lightpaths(self, state) -> None:
        traffic = self._traffic_on_ip_links(state)
        by_link: dict[tuple[int, int], list[int]] = {}
        for lp_id, lp in state.lightpath_info.items():
            by_link.setdefault(lp.ip_link, []).append(lp_id)

        current = state.lightpath_signature_counter()
        baseline = state.q0
        keys = set(current).union(baseline)
        distance = sum(abs(current.get(key, 0) - baseline.get(key, 0)) for key in keys)
        rho = self.cost_calculator.rho_limit

        for ip_link, lp_ids in by_link.items():
            load = traffic.get(ip_link, 0.0)
            required = int(math.ceil(load / self.lightpath_capacity)) if load > 1e-9 else 0
            remove_count = max(0, len(lp_ids) - required)
            ranked = []
            for lp_id in lp_ids:
                lp = state.lightpath_info[lp_id]
                signature = state.lightpath_signature(lp)
                before = abs(current.get(signature, 0) - baseline.get(signature, 0))
                after = abs(current.get(signature, 0) - 1 - baseline.get(signature, 0))
                ranked.append((after - before, lp_id, signature))
            ranked.sort(key=lambda item: (item[0], item[1]))

            removed = 0
            for delta, lp_id, signature in ranked:
                if removed >= remove_count:
                    break
                if rho is not None and distance + delta > rho:
                    continue
                state.remove_lightpath(lp_id)
                current[signature] -= 1
                distance += delta
                removed += 1

    def _add_lightpath(self, state, ip_link: tuple[int, int]) -> bool:
        u_ip, v_ip = ip_link
        if u_ip not in self.ip_to_opt_map or v_ip not in self.ip_to_opt_map:
            return False
        source = self.ip_to_opt_map[u_ip]
        target = self.ip_to_opt_map[v_ip]
        for opt_path in self._candidate_optical_paths(source, target):
            ok, slot = self.spectrum_allocator.find_available_slot(
                state=state,
                path_edges=self._path_edges(opt_path),
                required_slots=1,
            )
            if not ok:
                continue
            state.add_lightpath(
                Lightpath(
                    id=state.next_lightpath_id,
                    ip_link=ip_link,
                    opt_path=opt_path,
                    slot_start=slot,
                    slots=1,
                    path_id=self._path_id(state, ip_link, opt_path),
                )
            )
            return True
        return False

    def _candidate_ip_paths(self, demand) -> list[list[int]]:
        if demand.id not in self._ip_path_cache:
            try:
                generator = nx.shortest_simple_paths(
                    self.ip_graph, demand.s, demand.t, weight="weight"
                )
                self._ip_path_cache[demand.id] = [
                    path for _, path in zip(range(self.k_paths), generator)
                ]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._ip_path_cache[demand.id] = []
        return self._ip_path_cache[demand.id]

    def _candidate_optical_paths(self, source: int, target: int) -> list[list[int]]:
        key = (source, target)
        if key not in self._opt_path_cache:
            try:
                generator = nx.shortest_simple_paths(
                    self.opt_graph, source, target, weight="weight"
                )
                self._opt_path_cache[key] = [
                    path for _, path in zip(range(self.k_paths), generator)
                ]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._opt_path_cache[key] = []
        return self._opt_path_cache[key]

    def _observation(self) -> np.ndarray:
        traffic = self._traffic_on_ip_links(self.state)
        total_bw = sum(float(d.bandwidth) for d in self.demands)
        rho = self.cost_calculator.rho_limit
        details = self.cost_calculator.evaluate_constraints(self.state)
        max_node = max(1, self.ip_graph.number_of_nodes() - 1)
        global_values = [
            len(self.demands) / max(1, self.max_demands),
            min(1.0, total_bw / max(1.0, self.max_demands * 100.0)),
            min(1.0, self.current_cost / max(1.0, self.max_demands * 5.0)),
            min(1.0, self.best_cost / max(1.0, self.max_demands * 5.0)),
            self.step_count / max(1, self.max_steps),
            min(1.0, float(details["reconfiguration_distance"]) / max(1.0, float(rho or 1))),
            min(1.0, len(traffic) / max(1, self.ip_graph.number_of_edges())),
            1.0 if details["feasible"] else -1.0,
        ]
        demand_values: list[float] = []
        for index in range(self.max_demands):
            if index >= len(self.demands):
                demand_values.extend([0.0] * self.DEMAND_FEATURES)
                continue
            demand = self.demands[index]
            edges = self.state.get_demand_edges(demand.id)
            saving_score = 0.0
            for edge in edges:
                load = traffic.get(edge, 0.0)
                before = math.ceil(load / self.lightpath_capacity) if load > 0 else 0
                after_load = max(0.0, load - demand.bandwidth)
                after = math.ceil(after_load / self.lightpath_capacity) if after_load > 0 else 0
                saving_score += before - after
            demand_values.extend(
                [
                    1.0,
                    min(1.0, float(demand.bandwidth) / 100.0),
                    float(demand.s) / max_node,
                    float(demand.t) / max_node,
                    min(1.0, len(edges) / max_node),
                    min(1.0, saving_score / max(1.0, len(edges))),
                ]
            )
        return np.asarray(global_values + demand_values, dtype=np.float32)

    def _info(self) -> dict[str, Any]:
        return {
            "initial_cost": self.initial_cost,
            "current_cost": self.current_cost,
            "best_cost": self.best_cost,
            "accepted_moves": self.accepted_moves,
            "invalid_moves": self.invalid_moves,
        }

    def _traffic_on_ip_links(self, state) -> dict[tuple[int, int], float]:
        traffic: dict[tuple[int, int], float] = {}
        for (demand_id, u, v), value in state.x.items():
            if value != 1 or demand_id not in self.demand_by_id:
                continue
            edge = (u, v)
            traffic[edge] = traffic.get(edge, 0.0) + self.demand_by_id[demand_id].bandwidth
        return traffic

    def _installed_capacity(self, state, ip_link: tuple[int, int]) -> float:
        u, v = ip_link
        count = sum(
            max(0, value)
            for (uu, vv, _), value in state.y.items()
            if uu == u and vv == v
        )
        return count * self.lightpath_capacity

    def _path_id(self, state, ip_link: tuple[int, int], opt_path: list[int]) -> int:
        ids = []
        for lp in state.lightpath_info.values():
            if lp.ip_link != ip_link:
                continue
            ids.append(lp.path_id)
            if lp.opt_path == opt_path:
                return lp.path_id
        ids.extend(
            path_id
            for (u, v, path_id) in state.y
            if (u, v) == ip_link
        )
        return max(ids, default=-1) + 1

    @staticmethod
    def _path_edges(path: Iterable[int]) -> list[tuple[int, int]]:
        nodes = list(path)
        return list(zip(nodes, nodes[1:]))

    @staticmethod
    def _replace_state(target, source) -> None:
        target.x = source.x
        target.y = source.y
        target.z = source.z
        target.s = source.s
        target.y0 = source.y0
        target.q0 = source.q0
        target.lightpath_info = source.lightpath_info
        target.next_lightpath_id = source.next_lightpath_id


def run_policy_episode(model, env: CrossLayerPPOEnv, deterministic: bool = True):
    """Run one PPO-only inference episode and return the best feasible state."""
    observation, _ = env.reset()
    terminated = truncated = False
    while not (terminated or truncated):
        action, _ = model.predict(
            observation,
            action_masks=env.action_masks(),
            deterministic=deterministic,
        )
        observation, _, terminated, truncated, _ = env.step(int(action))
    return env.best_state.deepcopy(), env._info()


def run_fast_policy_search(
    model,
    env: CrossLayerPPOEnv,
    top_k: int = 4,
    max_steps: int = 16,
):
    """Run one monotonic PPO-guided trajectory with bounded proposals."""
    observation, _ = env.reset()
    step_limit = min(int(max_steps), env.max_steps)
    for _ in range(step_limit):
        mask = env.action_masks()
        obs_tensor, _ = model.policy.obs_to_tensor(observation)
        mask_tensor = torch.as_tensor(mask[None, :], device=model.device)
        with torch.no_grad():
            distribution = model.policy.get_distribution(
                obs_tensor, action_masks=mask_tensor
            )
            probabilities = distribution.distribution.probs[0].detach().cpu().numpy()
        ranked_actions = np.argsort(probabilities)[::-1]
        proposals = [
            int(action)
            for action in ranked_actions
            if action != 0 and mask[action]
        ][: max(1, top_k)]

        best_candidate = None
        best_cost = env.current_cost
        for action in proposals:
            demand_index, path_rank = env._decode_action(action)
            candidate = env._candidate_from_action(demand_index, path_rank)
            if candidate is None:
                continue
            cost = float(env.cost_calculator.calculate_objective(candidate))
            if math.isfinite(cost) and cost < best_cost:
                best_candidate = candidate
                best_cost = cost
        if best_candidate is None:
            break

        env.step_count += 1
        env.accepted_moves += 1
        env.state = best_candidate
        env.current_cost = best_cost
        env.best_state = best_candidate.deepcopy()
        env.best_cost = best_cost
        observation = env._observation()
    return env.best_state.deepcopy(), env._info()
