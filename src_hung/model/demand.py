import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Demand:
    """
    Traffic demand trên tầng IP.

    id: mã demand
    s: source IP node
    t: target IP node
    bandwidth: b_d, đơn vị giả định là Gbps
    """
    id: str
    s: int
    t: int
    bandwidth: float


def generate_random_demands(
    num_demands: int,
    num_ip_nodes: int,
    bw_min: int = 10,
    bw_max: int = 100,
    seed: int | None = None,
) -> list[Demand]:
    if num_ip_nodes < 2:
        raise ValueError("Cần ít nhất 2 node IP để sinh demand.")

    rng = random.Random(seed)
    demands: list[Demand] = []

    for i in range(num_demands):
        s, t = rng.sample(range(num_ip_nodes), 2)
        bandwidth = rng.randint(bw_min, bw_max)
        demands.append(Demand(id=f"d{i}", s=s, t=t, bandwidth=bandwidth))

    return demands