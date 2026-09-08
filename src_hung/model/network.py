import random
import networkx as nx


class PhysicalNetwork:
    def __init__(self, num_slots: int = 100, lightpath_capacity: int = 80):
        self.graph = nx.DiGraph()
        self.num_slots = num_slots
        self.lightpath_capacity = lightpath_capacity

    def add_link(
        self,
        u: int,
        v: int,
        length: int | None = None,
        capacity: int | None = None,
    ) -> None:
        if u == v:
            return

        if length is None:
            length = random.randint(10, 100)

        if capacity is None:
            capacity = self.lightpath_capacity

        self.graph.add_edge(u, v, weight=length, capacity=capacity)
        self.graph.add_edge(v, u, weight=length, capacity=capacity)

    def create_random_topology(
        self,
        n_node: int,
        n_link: int,
        seed: int | None = None,
    ) -> None:
        if n_node < 2:
            raise ValueError("Mạng vật lý cần ít nhất 2 node.")

        rng = random.Random(seed)
        self.graph.clear()

        max_link = n_node * (n_node - 1) // 2
        n_link = min(max(n_link, n_node - 1), max_link)

        nodes = list(range(n_node))
        self.graph.add_nodes_from(nodes)

        undirected_edges: set[tuple[int, int]] = set()

        perm = nodes[:]
        rng.shuffle(perm)

        for i in range(1, n_node):
            u = perm[i]
            v = perm[rng.randint(0, i - 1)]
            edge = tuple(sorted((u, v)))
            undirected_edges.add(edge)
            self.add_link(u, v, length=rng.randint(10, 100))

        while len(undirected_edges) < n_link:
            u, v = rng.sample(nodes, 2)
            edge = tuple(sorted((u, v)))

            if edge in undirected_edges:
                continue

            undirected_edges.add(edge)
            self.add_link(u, v, length=rng.randint(10, 100))

        print(
            f"[+] Đã tạo mạng quang: "
            f"{n_node} nodes, {len(undirected_edges)} undirected links."
        )


def generate_ip_topology(
    ip_nodes: int,
    ip_links: int,
    seed: int | None = None,
) -> nx.DiGraph:
    if ip_nodes < 2:
        raise ValueError("Mạng IP cần ít nhất 2 node.")

    rng = random.Random(seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(range(ip_nodes))

    max_link = ip_nodes * (ip_nodes - 1) // 2
    ip_links = min(max(ip_links, ip_nodes - 1), max_link)

    undirected_edges: set[tuple[int, int]] = set()
    perm = list(range(ip_nodes))
    rng.shuffle(perm)

    for i in range(1, ip_nodes):
        u = perm[i]
        v = perm[rng.randint(0, i - 1)]
        edge = tuple(sorted((u, v)))
        undirected_edges.add(edge)
        graph.add_edge(u, v, weight=1)
        graph.add_edge(v, u, weight=1)

    while len(undirected_edges) < ip_links:
        u, v = rng.sample(range(ip_nodes), 2)
        edge = tuple(sorted((u, v)))

        if edge in undirected_edges:
            continue

        undirected_edges.add(edge)
        graph.add_edge(u, v, weight=1)
        graph.add_edge(v, u, weight=1)

    print(
        f"[+] Đã tạo mạng IP: "
        f"{ip_nodes} nodes, {len(undirected_edges)} undirected links."
    )

    return graph


def update_ip_edge_weights_by_optical_distance(
    ip_graph: nx.DiGraph,
    opt_graph: nx.DiGraph,
    ip_to_opt_map: dict[int, int],
) -> None:
    """
    Gán weight cho IP edge bằng độ dài shortest path quang giữa hai router IP.
    Như vậy latency ở tầng IP phản ánh khoảng cách vật lý hơn.
    """
    for u_ip, v_ip in ip_graph.edges():
        u_opt = ip_to_opt_map[u_ip]
        v_opt = ip_to_opt_map[v_ip]

        try:
            length = nx.shortest_path_length(
                opt_graph,
                source=u_opt,
                target=v_opt,
                weight="weight",
            )
        except nx.NetworkXNoPath:
            length = 10**9

        ip_graph[u_ip][v_ip]["weight"] = length


def generate_multilayer_topology(
    opt_nodes: int,
    opt_links: int,
    ip_nodes: int,
    ip_links: int,
    num_slots: int = 100,
    lightpath_capacity: int = 80,
    seed: int | None = None,
):
    if ip_nodes > opt_nodes:
        raise ValueError("Số node IP không được vượt quá số node quang.")

    rng = random.Random(seed)

    physical_net = PhysicalNetwork(
        num_slots=num_slots,
        lightpath_capacity=lightpath_capacity,
    )
    physical_net.create_random_topology(
        n_node=opt_nodes,
        n_link=opt_links,
        seed=seed,
    )

    opt_graph = physical_net.graph
    physical_node_ids = list(opt_graph.nodes())

    ip_nodes_mapped = rng.sample(physical_node_ids, ip_nodes)
    ip_to_opt_map = {
        ip_node: ip_nodes_mapped[ip_node]
        for ip_node in range(ip_nodes)
    }

    ip_graph = generate_ip_topology(
        ip_nodes=ip_nodes,
        ip_links=ip_links,
        seed=seed,
    )

    update_ip_edge_weights_by_optical_distance(
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
    )

    print(f"[+] Mapping IP -> Optical: {ip_to_opt_map}")

    return physical_net, ip_graph, ip_to_opt_map