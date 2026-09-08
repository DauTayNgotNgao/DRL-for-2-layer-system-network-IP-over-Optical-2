from dataclasses import dataclass
from typing import Tuple


@dataclass
class Lightpath:
    """
    Một lightpath hỗ trợ cho một IP link.

    ip_link: link logic tầng IP, ví dụ (u_ip, v_ip)
    opt_path: đường đi quang vật lý dạng list node, ví dụ [1, 4, 7]
    slot_start: khe phổ bắt đầu
    slots: số khe phổ cần dùng, hiện tại có thể để 1 theo mô hình w_k = 1
    path_id: id đường quang ứng viên, hiện tại có thể để 0
    """
    id: int
    ip_link: Tuple[int, int]
    opt_path: list[int]
    slot_start: int
    slots: int = 1
    path_id: int = 0

    @property
    def opt_edges(self) -> list[Tuple[int, int]]:
        return [
            (self.opt_path[i], self.opt_path[i + 1])
            for i in range(len(self.opt_path) - 1)
        ]