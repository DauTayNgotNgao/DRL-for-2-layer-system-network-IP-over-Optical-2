from __future__ import annotations

import itertools
import re
import sys
import time
from collections import defaultdict
from typing import Any

import networkx as nx


class NativeCplexPathMixedIntegerProgram:
    """SA-compatible CPLEX model using Hypergiant's path-based MILP logic.

    This keeps the path-based MILP structure, but matches this project's SA/RL
    hard constraints: directed IP links, generated IP graph only, one-slot
    lightpaths, explicit spectrum conflict constraints, and optional rho budget.
    """

    def __init__(
        self,
        inputinstance,
        *,
        num_threads: int | None = 1,
        time_limit: int | None = None,
        enable_output: bool = False,
    ):
        try:
            import cplex
        except ImportError as exc:
            raise RuntimeError(
                "Cannot import IBM CPLEX Python API. Activate the environment "
                "that has your licensed CPLEX install, then run this command again."
            ) from exc

        self.cplex = cplex
        self.inputinstance = inputinstance
        self.problem = cplex.Cplex()
        if enable_output:
            self.problem.set_log_stream(sys.stdout)
            self.problem.set_results_stream(sys.stdout)
            self.problem.set_warning_stream(sys.stdout)
            self.problem.set_error_stream(sys.stdout)
        else:
            self.problem.set_log_stream(None)
            self.problem.set_results_stream(None)
            self.problem.set_warning_stream(None)
            self.problem.set_error_stream(None)
        self.problem.objective.set_sense(self.problem.objective.sense.minimize)
        self.num_threads = num_threads
        self.time_limit = time_limit
        self.result_status: int | None = None
        self.build_time_ms: float | None = None
        self.solver_time_ms: float | None = None

        self.flow_e2e: dict[tuple[Any, Any, Any], str] = {}
        self.lightpath: dict[tuple[Any, Any, int, int], str] = {}
        self._candidate_cache: dict[tuple[Any, Any], list[list[str]]] = {}

    def build(self) -> None:
        start = time.perf_counter()
        self._build_variables()
        self._build_constraints()
        self._build_objective()
        self.build_time_ms = (time.perf_counter() - start) * 1000.0

    def solve(self) -> None:
        if self.num_threads is not None:
            self.problem.parameters.threads.set(int(self.num_threads))
        if self.time_limit is not None:
            self.problem.parameters.timelimit.set(float(self.time_limit))

        start = time.perf_counter()
        self.problem.solve()
        self.solver_time_ms = (time.perf_counter() - start) * 1000.0
        self.result_status = self.problem.solution.get_status()

    def write(self, fname: str) -> None:
        self.problem.write(fname)

    def get_solution_dict(self) -> dict[str, Any]:
        if not self._has_solution():
            return {
                "ip_links": [],
                "lightpaths": [],
                "cdn_assignment": [],
                "e2e_routing": [],
                "metrics": self._base_metrics(),
            }

        lightpaths = self._extract_lightpaths()
        ip_links = self._extract_ip_links(lightpaths)
        routes = self._extract_e2e_routing()
        metrics = self._calculate_metrics(ip_links, routes, lightpaths)
        metrics.update(self._base_metrics())
        metrics["objective"] = self.problem.solution.get_objective_value()
        metrics["best_bound"] = self._best_bound()
        return {
            "ip_links": ip_links,
            "lightpaths": lightpaths,
            "cdn_assignment": [],
            "e2e_routing": routes,
            "metrics": metrics,
        }

    @property
    def status_name(self) -> str:
        if self.result_status is None:
            return "NOT_SOLVED"
        try:
            return self.problem.solution.get_status_string(self.result_status)
        except TypeError:
            return self.problem.solution.get_status_string()

    def stats(self) -> dict[str, Any]:
        return {
            "variables": self.problem.variables.get_num(),
            "binary_variables": len(self.flow_e2e) + len(self.lightpath),
            "flow_variables": len(self.flow_e2e),
            "lightpath_variables": len(self.lightpath),
            "constraints": self.problem.linear_constraints.get_num(),
            "allowed_ip_edges": len(list(self._allowed_ip_node_pairs())),
            "num_slots": self._num_slots,
            "optical_candidate_k": int(getattr(self.inputinstance, "optical_candidate_k", 10)),
        }

    def _build_variables(self) -> None:
        flow_names = []
        for dem_key in self.inputinstance.background_demand.keys():
            for e, f in self._allowed_ip_node_pairs():
                name = _var_name("flow_e2e", *dem_key, e.id, f.id)
                self.flow_e2e[(dem_key, e, f)] = name
                flow_names.append(name)

        if flow_names:
            self.problem.variables.add(
                names=flow_names,
                lb=[0.0] * len(flow_names),
                ub=[1.0] * len(flow_names),
                types=[self.problem.variables.type.binary] * len(flow_names),
                obj=[0.0] * len(flow_names),
            )

        lp_names = []
        for e, f in self._allowed_ip_node_pairs():
            for path_num, _ in enumerate(self._candidate_paths(e, f)):
                for slot in range(self._num_slots):
                    name = _var_name("lp", e.id, f.id, path_num, slot)
                    self.lightpath[(e, f, path_num, slot)] = name
                    lp_names.append(name)

        if lp_names:
            self.problem.variables.add(
                names=lp_names,
                lb=[0.0] * len(lp_names),
                ub=[1.0] * len(lp_names),
                types=[self.problem.variables.type.binary] * len(lp_names),
                obj=[1.0] * len(lp_names),
            )

    def _build_constraints(self) -> None:
        self._build_constraint_flow_conservation_e2e()
        self._build_constraint_ip_link_capacity()
        self._build_constraint_spectrum_conflict()
        self._build_constraint_max_ip_utilization()
        self._build_constraint_reconfiguration_budget()

    def _build_objective(self) -> None:
        self.problem.objective.set_linear(
            [(var_name, 1.0) for var_name in self.lightpath.values()]
        )

    def _build_constraint_flow_conservation_e2e(self) -> None:
        for dem_key, demand in self.inputinstance.background_demand.items():
            for node in self.inputinstance.topology.ip_nodes:
                outgoing = [
                    (self.flow_e2e[(dem_key, node, dst)], 1.0)
                    for dst in self._allowed_successors(node)
                ]
                incoming = [
                    (self.flow_e2e[(dem_key, src, node)], -1.0)
                    for src in self._allowed_predecessors(node)
                ]

                if demand.node1 == node:
                    rhs = 1.0
                elif demand.node2 == node:
                    rhs = -1.0
                else:
                    rhs = 0.0

                self._add_constraint(
                    outgoing + incoming,
                    "E",
                    rhs,
                    _var_name("ip_flow_conservation_e2e", *dem_key, node.id),
                )
                self._add_constraint(
                    outgoing,
                    "L",
                    1.0,
                    _var_name("ip_routing_restriction_e2e_out", *dem_key, node.id),
                )
                self._add_constraint(
                    [(name, -coef) for name, coef in incoming],
                    "L",
                    1.0,
                    _var_name("ip_routing_restriction_e2e_in", *dem_key, node.id),
                )

    def _build_constraint_ip_link_capacity(self) -> None:
        for e, f in self._allowed_ip_node_pairs():
            terms = []
            for dem_key, demand in self.inputinstance.background_demand.items():
                terms.append((self.flow_e2e[(dem_key, e, f)], float(demand.volume)))
            for path_num, _ in enumerate(self._candidate_paths(e, f)):
                for slot in range(self._num_slots):
                    terms.append(
                        (
                            self.lightpath[(e, f, path_num, slot)],
                            -self._lightpath_capacity,
                        )
                    )
            self._add_constraint(terms, "L", 0.0, _var_name("ip_capacity", e.id, f.id))

    def _build_constraint_spectrum_conflict(self) -> None:
        for optical_edge in self.inputinstance.topology.opt_edges.values():
            edge = (optical_edge.node1.id, optical_edge.node2.id)
            for slot in range(self._num_slots):
                terms = []
                for e, f in self._allowed_ip_node_pairs():
                    for path_num, path in enumerate(self._candidate_paths(e, f)):
                        if _path_uses_edge(path, edge):
                            terms.append((self.lightpath[(e, f, path_num, slot)], 1.0))
                self._add_constraint(
                    terms,
                    "L",
                    1.0,
                    _var_name("spectrum", edge[0], edge[1], slot),
                )

    def _build_constraint_max_ip_utilization(self) -> None:
        if self._ip_utilization is None:
            return

        for e, f in self._allowed_ip_node_pairs():
            terms = []
            for dem_key, demand in self.inputinstance.background_demand.items():
                terms.append((self.flow_e2e[(dem_key, e, f)], float(demand.volume)))
            for path_num, _ in enumerate(self._candidate_paths(e, f)):
                for slot in range(self._num_slots):
                    terms.append(
                        (
                            self.lightpath[(e, f, path_num, slot)],
                            -self._ip_utilization * self._lightpath_capacity,
                        )
                    )
            self._add_constraint(terms, "L", 0.0, _var_name("max_ip_link_util", e.id, f.id))

    def _build_constraint_reconfiguration_budget(self) -> None:
        baseline = getattr(self.inputinstance, "baseline_lightpaths", None)
        rho_limit = getattr(self.inputinstance, "rho_limit", None)
        if baseline is None or rho_limit is None:
            return

        baseline_keys = set()
        for item in baseline:
            key = self._signature_to_lightpath_key(item)
            if key is not None:
                baseline_keys.add(key)

        terms = []
        baseline_total = len(baseline)
        for key, var_name in self.lightpath.items():
            if key in baseline_keys:
                terms.append((var_name, -1.0))
            else:
                terms.append((var_name, 1.0))

        self._add_constraint(
            terms,
            "L",
            float(rho_limit - baseline_total),
            "rho_reconfiguration_budget",
        )

    def _extract_lightpaths(self) -> list[dict[str, Any]]:
        lightpaths = []
        lp_id = 0
        for (e, f, path_num, slot), var_name in self.lightpath.items():
            if self._value(var_name) <= 0.5:
                continue
            lightpaths.append(
                {
                    "id": lp_id,
                    "ip_link": [_from_ip_id(e.id), _from_ip_id(f.id)],
                    "opt_path": [
                        _from_optical_id(node_id)
                        for node_id in self._candidate_paths(e, f)[path_num]
                    ],
                    "slot_start": slot,
                    "slots": 1,
                    "path_id": path_num,
                }
            )
            lp_id += 1
        return lightpaths

    def _extract_ip_links(self, lightpaths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_ip_link: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for lp in lightpaths:
            by_ip_link[tuple(lp["ip_link"])].append(lp)

        ip_links = []
        for (u_ip, v_ip), lps in sorted(by_ip_link.items()):
            opt_links = []
            for lp in lps:
                opt_path = lp["opt_path"]
                for u_opt, v_opt in zip(opt_path[:-1], opt_path[1:]):
                    opt_links.append(
                        [
                            _optical_id(u_opt),
                            _optical_id(v_opt),
                            1.0,
                            lp["path_id"],
                            lp["slot_start"],
                        ]
                    )
            ip_links.append(
                {
                    "node1": _ip_id(u_ip),
                    "node2": _ip_id(v_ip),
                    "num_trunks": float(len(lps)),
                    "opt_links": opt_links,
                    "path_num": None,
                }
            )
        return ip_links

    def _extract_e2e_routing(self) -> list[dict[str, Any]]:
        routes = []
        for dem_key, demand in self.inputinstance.background_demand.items():
            paths = []
            for e, f in self._allowed_ip_node_pairs():
                value = self._value(self.flow_e2e[(dem_key, e, f)])
                if value > 0.5:
                    paths.append([[e.id, f.id], value * float(demand.volume)])
            routes.append(
                {
                    "demand_id": dem_key[0],
                    "node1": demand.node1.id,
                    "node2": demand.node2.id,
                    "paths": paths,
                }
            )
        return routes

    def _calculate_metrics(
        self,
        ip_links: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        lightpaths: list[dict[str, Any]],
    ) -> dict[str, Any]:
        route_lengths = [len(route["paths"]) for route in routes]
        return {
            "num_ip_links": len(ip_links),
            "deployed_ip_trunks": float(len(lightpaths)),
            "total_num_lightpath_hops": sum(
                max(0, len(lp["opt_path"]) - 1)
                for lp in lightpaths
            ),
            "max_path_length_ip_hops": max(route_lengths, default=0),
            "min_path_length_ip_hops": min(route_lengths, default=0),
            "mean_path_length_ip_hops": (
                sum(route_lengths) / len(route_lengths)
                if route_lengths
                else 0.0
            ),
        }

    def _allowed_ip_node_pairs(self):
        allowed_edges = getattr(self.inputinstance, "allowed_ip_edges", None)
        ip_nodes_by_id = {node.id: node for node in self.inputinstance.topology.ip_nodes}
        if allowed_edges is None:
            return itertools.filterfalse(
                lambda pair: pair[0] == pair[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2),
            )
        return (
            (ip_nodes_by_id[u], ip_nodes_by_id[v])
            for u, v in allowed_edges
            if u in ip_nodes_by_id and v in ip_nodes_by_id and u != v
        )

    def _allowed_successors(self, node):
        return [f for e, f in self._allowed_ip_node_pairs() if e == node]

    def _allowed_predecessors(self, node):
        return [e for e, f in self._allowed_ip_node_pairs() if f == node]

    def _candidate_paths(self, e, f) -> list[list[str]]:
        key = (e, f)
        if key in self._candidate_cache:
            return self._candidate_cache[key]

        max_candidates = int(getattr(self.inputinstance, "optical_candidate_k", 10))
        graph = self.inputinstance.topology.graph
        try:
            paths_iter = nx.shortest_simple_paths(
                graph,
                source=e.lower_layer.id,
                target=f.lower_layer.id,
                weight="weight",
            )
            paths = [path for _, path in zip(range(max_candidates), paths_iter)]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            paths = []
        self._candidate_cache[key] = paths
        return paths

    def _signature_to_lightpath_key(self, item: dict[str, Any]):
        u_ip, v_ip = item["ip_link"]
        slot = int(item["slot_start"])
        opt_path = [_optical_id(node) for node in item["opt_path"]]

        for e, f in self._allowed_ip_node_pairs():
            if e.id != _ip_id(u_ip) or f.id != _ip_id(v_ip):
                continue
            for path_num, candidate in enumerate(self._candidate_paths(e, f)):
                if candidate == opt_path and (e, f, path_num, slot) in self.lightpath:
                    return e, f, path_num, slot
        return None

    @property
    def _num_slots(self) -> int:
        return int(getattr(self.inputinstance, "num_slots"))

    @property
    def _lightpath_capacity(self) -> float:
        return float(self.inputinstance.topology.parameter["IP_LIGHTPATH_CAPACITY"])

    @property
    def _ip_utilization(self) -> float | None:
        return self.inputinstance.topology.parameter.get("IP_LINK_UTILIZATION")

    def _add_constraint(
        self,
        terms: list[tuple[str, float]],
        sense: str,
        rhs: float,
        name: str,
    ) -> None:
        merged = defaultdict(float)
        for var_name, coef in terms:
            if abs(coef) > 1e-12:
                merged[var_name] += float(coef)
        sparse_pair = self.cplex.SparsePair(
            ind=list(merged.keys()),
            val=list(merged.values()),
        )
        self.problem.linear_constraints.add(
            lin_expr=[sparse_pair],
            senses=[sense],
            rhs=[float(rhs)],
            names=[name],
        )

    def _has_solution(self) -> bool:
        try:
            self.problem.solution.get_objective_value()
            return True
        except Exception:
            return False

    def _value(self, var_name: str) -> float:
        return float(self.problem.solution.get_values(var_name))

    def _best_bound(self) -> float | None:
        try:
            return float(self.problem.solution.MIP.get_best_objective())
        except Exception:
            return None

    def _base_metrics(self) -> dict[str, Any]:
        total_time = None
        if self.build_time_ms is not None and self.solver_time_ms is not None:
            total_time = self.build_time_ms + self.solver_time_ms
        return {
            "model_build_time": self.build_time_ms,
            "solver_time": self.solver_time_ms,
            "total_milp_time": total_time,
            "status": self.result_status,
            "status_name": self.status_name,
        }


def _path_uses_edge(path: list[str], edge: tuple[str, str]) -> bool:
    return any((u, v) == edge for u, v in zip(path[:-1], path[1:]))


def _ip_id(ip_id: int) -> str:
    return f"IP-{ip_id}"


def _optical_id(opt_id: int) -> str:
    return f"O-{opt_id}"


def _from_ip_id(value: str) -> int:
    return int(str(value).replace("IP-", ""))


def _from_optical_id(value: str) -> int:
    return int(str(value).replace("O-", ""))


def _var_name(*parts: Any) -> str:
    raw = "_".join(str(part) for part in parts)
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", raw)
    return safe.strip("_")[:240]
