from collections import defaultdict
from src_hung.model.state import MultiLayerState


class SpectrumAllocator:
    def __init__(self, num_slots: int = 100, guardband: int = 0):
        self.num_slots = num_slots
        self.guardband = guardband

    def _occupied_slots_by_edge(
        self,
        state: MultiLayerState,
        ignore_lightpath_id: int | None = None,
    ) -> dict[tuple[int, int], set[int]]:
        occupied = defaultdict(set)

        for k, lp in state.lightpath_info.items():
            if ignore_lightpath_id is not None and k == ignore_lightpath_id:
                continue

            if k not in state.s:
                continue

            start = state.s[k]
            end = start + lp.slots

            reserve_start = max(0, start - self.guardband)
            reserve_end = min(self.num_slots, end + self.guardband)

            for edge in lp.opt_edges:
                for slot in range(reserve_start, reserve_end):
                    occupied[edge].add(slot)

        return occupied

    def find_available_slot(
        self,
        state: MultiLayerState,
        path_edges: list[tuple[int, int]],
        required_slots: int = 1,
    ) -> tuple[bool, int]:
        if required_slots <= 0:
            return False, -1

        if required_slots > self.num_slots:
            return False, -1

        occupied = self._occupied_slots_by_edge(state)

        for start in range(0, self.num_slots - required_slots + 1):
            ok = True

            candidate_slots = set(range(start, start + required_slots))

            for edge in path_edges:
                if occupied[edge].intersection(candidate_slots):
                    ok = False
                    break

            if ok:
                return True, start

        return False, -1

    def check_conflict(self, state: MultiLayerState) -> bool:
        used = defaultdict(set)

        for k, lp in state.lightpath_info.items():
            if k not in state.s:
                return False

            start = state.s[k]
            end = start + lp.slots

            if start < 0 or end > self.num_slots:
                return False

            for edge in lp.opt_edges:
                for slot in range(start, end):
                    if slot in used[edge]:
                        return False
                    used[edge].add(slot)

        return True