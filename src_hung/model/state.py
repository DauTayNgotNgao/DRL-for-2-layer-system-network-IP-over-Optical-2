import copy
from collections import Counter

from .lightpath import Lightpath


class MultiLayerState:
    """
    State đa lớp.

    x[(d, u_ip, v_ip)] = 1 nếu demand d đi qua IP link (u_ip, v_ip)

    y[(u_ip, v_ip, p)] = số lightpath hỗ trợ IP link (u_ip, v_ip)
    theo optical candidate path p.

    z[(k, e)] = 1 nếu lightpath k đi qua fiber edge e = (u_opt, v_opt)

    s[k] = slot bắt đầu của lightpath k

    lightpath_info[k] = Lightpath object
    """

    def __init__(self, demands=None):
        self.demands = demands if demands is not None else []

        self.x: dict[tuple[str, int, int], int] = {}
        self.y: dict[tuple[int, int, int], int] = {}
        self.z: dict[tuple[int, tuple[int, int]], int] = {}
        self.s: dict[int, int] = {}

        self.y0: dict[tuple[int, int, int], int] = {}
        # Baseline q0 dùng cho global reconfiguration budget:
        # added + removed lightpaths phải được so với initial state,
        # không phải so với current state của từng SA move.
        self.q0: Counter = Counter()
        self.lightpath_info: dict[int, Lightpath] = {}

        self.next_lightpath_id: int = 0

    def deepcopy(self) -> "MultiLayerState":
        new_state = MultiLayerState(self.demands)
        new_state.x = copy.deepcopy(self.x)
        new_state.y = copy.deepcopy(self.y)
        new_state.z = copy.deepcopy(self.z)
        new_state.s = copy.deepcopy(self.s)
        new_state.y0 = copy.deepcopy(self.y0)
        new_state.q0 = copy.deepcopy(self.q0)
        new_state.lightpath_info = copy.deepcopy(self.lightpath_info)
        new_state.next_lightpath_id = self.next_lightpath_id
        return new_state

    def clear_demand_route(self, demand_id: str) -> None:
        for key in list(self.x.keys()):
            dd, _, _ = key
            if dd == demand_id:
                del self.x[key]

    def set_demand_path(self, demand_id: str, path_nodes: list[int]) -> None:
        self.clear_demand_route(demand_id)

        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i + 1]
            self.x[(demand_id, u, v)] = 1

    def get_demand_edges(self, demand_id: str) -> list[tuple[int, int]]:
        return [
            (u, v)
            for (dd, u, v), val in self.x.items()
            if dd == demand_id and val == 1
        ]

    def add_lightpath(self, lp: Lightpath) -> None:
        if lp.slots <= 0:
            raise ValueError("Số slot của lightpath phải > 0.")

        self.lightpath_info[lp.id] = lp
        self.s[lp.id] = lp.slot_start

        for edge in lp.opt_edges:
            self.z[(lp.id, edge)] = 1

        u_ip, v_ip = lp.ip_link
        y_key = (u_ip, v_ip, lp.path_id)
        self.y[y_key] = self.y.get(y_key, 0) + 1

        self.next_lightpath_id = max(self.next_lightpath_id, lp.id + 1)

    def remove_lightpath(self, lightpath_id: int) -> bool:
        if lightpath_id not in self.lightpath_info:
            return False

        lp = self.lightpath_info[lightpath_id]
        u_ip, v_ip = lp.ip_link
        y_key = (u_ip, v_ip, lp.path_id)

        if y_key in self.y:
            self.y[y_key] -= 1
            if self.y[y_key] <= 0:
                del self.y[y_key]

        for key in list(self.z.keys()):
            k, _ = key
            if k == lightpath_id:
                del self.z[key]

        if lightpath_id in self.s:
            del self.s[lightpath_id]

        del self.lightpath_info[lightpath_id]
        return True

    def lightpath_signature(self, lp: Lightpath) -> tuple:
        """
        Định danh một lightpath logic để so sánh initial_state với candidate/best_state.

        Không dùng lp.id vì id chỉ là mã nội bộ.
        Signature này phải khớp với cách vẽ added/removed trong demand_sweep.py:
            (ip_link, optical_path, slot_start, slots)
        Vì vậy nếu đổi optical route hoặc đổi slot block thì được tính là:
            1 removed + 1 added
        đúng với make/break reconfiguration.
        """
        return (
            tuple(lp.ip_link),
            tuple(lp.opt_path),
            int(lp.slot_start),
            int(lp.slots),
        )

    def lightpath_signature_counter(self) -> Counter:
        return Counter(
            self.lightpath_signature(lp)
            for lp in self.lightpath_info.values()
        )

    def set_baseline_y0(self) -> None:
        self.y0 = copy.deepcopy(self.y)
        self.q0 = self.lightpath_signature_counter()
