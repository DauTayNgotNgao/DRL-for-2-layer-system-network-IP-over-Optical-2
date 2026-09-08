import networkx as nx
import numpy as np
import collections

import constants


class NodeIdGenerator(object):
    current_id = 1

    @classmethod
    def get_next_id(cls):
        id_to_return = NodeIdGenerator.current_id
        NodeIdGenerator.current_id += 1
        return id_to_return


class Node(object):
    def __init__(self, nid, parent=None):
        self._id = nid
        self._parent = parent
        self._children = list()
        self.edges = list()

    @property
    def id(self):
        return self._id

    @property
    def lower_layer(self):
        return self._parent

    @property
    def upper_layer(self):
        return self._children

    def add_edge(self, edge):
        if edge not in self.edges:
            self.edges.append(edge)
        else:
            raise RuntimeError("Edge already added.")


class OpticalNode(Node):
    def __init__(self, nid):
        super(OpticalNode, self).__init__(nid, parent=None)  # Optical is lowest layer. No parent

    def __repr__(self):
        return "ON-{}".format(self.id)


class IPNode(Node):
    def __init__(self, nid, parent, num_transceiver=0):
        assert isinstance(parent, OpticalNode)
        super(IPNode, self).__init__(nid, parent)
        parent.upper_layer.append(self)

        self._num_transceiver = num_transceiver

    @property
    def num_transceiver(self):
        return self._num_transceiver

    def __repr__(self):
        return "IPN-{}({})".format(self.id, self.lower_layer)


class OpticalLink(object):
    def __init__(self, node1, node2, capacity):
        assert isinstance(node1, OpticalNode)
        assert isinstance(node2, OpticalNode)
        self._node1 = node1
        self._node2 = node2
        self._capacity = capacity

        node1.add_edge(self)
        node2.add_edge(self)

    def get_key(self):
        return self.node1.id, self.node2.id

    @property
    def capacity(self):
        return self._capacity

    @property
    def node1(self):
        return self._node1

    @property
    def node2(self):
        return self._node2

    def __repr__(self):
        return "{}-{}-cap={}".format(
            self.node1.id, self.node2.id, self.capacity
        )


class IPLink(object):
    def __init__(self, node1, node2, num_trunks, opt_links, path_num=None):
        assert isinstance(node1, IPNode)
        assert isinstance(node2, IPNode)
        self._node1 = node1
        self._node2 = node2
        self._num_trunks = num_trunks
        self._opt_links = opt_links
        self.path_num = path_num

    @property
    def node1(self):
        return self._node1

    @property
    def node2(self):
        return self._node2

    @property
    def num_trunks(self):
        return self._num_trunks

    @property
    def opt_links(self):
        return self._opt_links

    def to_dict(self):
        return {
            'node1': self.node1.id,
            'node2': self.node2.id,
            'num_trunks': self.num_trunks,
            'opt_links': [(m.id, n.id, num, path) for m, n, num, path in self.opt_links],
            'path_num': self.path_num
        }


class Topology(object):
    def __init__(self, name="test_topo", parameter=None):
        self.name = name
        self.graph = nx.Graph()

        self.parameter = parameter
        if parameter is None:
            self.parameter = dict()

        self.ip_nodes = list()
        self.opt_nodes = list()

        self.opt_edges = dict()

        self.candidate_paths_per_opt_edge = collections.defaultdict(list)

    @property
    def nodes(self):
        return self.ip_nodes + self.opt_nodes

    def add_node(self, node):
        if node in self.nodes:
            raise RuntimeError("Node already added to topology")
        if isinstance(node, IPNode):
            self.ip_nodes.append(node)
        elif isinstance(node, OpticalNode):
            self.opt_nodes.append(node)
            # Add optical nodes the the networkx Graph since we want to calculate paths between them later
            self.graph.add_node(node.id)
        else:
            raise RuntimeError("Node type unknown")

    def get_node_by_id(self, nid):
        for n in self.nodes:
            if n.id == nid:
                return n
        raise ValueError("Node not found: {}".format(nid))

    def add_edge(self, edge, weight=1):
        assert isinstance(edge, OpticalLink)
        if edge.get_key() not in self.opt_edges:
            self.opt_edges[edge.get_key()] = edge
            self.graph.add_edge(edge.node1.id, edge.node2.id, weight=weight)
            self.candidate_paths_per_opt_edge[(edge.node1.id, edge.node2.id)] = list()
        else:
            raise RuntimeError("Edge already exists")

    def get_all_optical_candidate_paths_between_ip_nodes(self, src, dst):
        paths = list(nx.all_shortest_paths(self.graph, src.lower_layer.id, dst.lower_layer.id, weight='weight'))
        for i, path in enumerate(paths):
            for m, n in zip(path[:-1], path[1:]):
                if (src, dst, i) not in self.candidate_paths_per_opt_edge[(m, n)]:
                    self.candidate_paths_per_opt_edge[(m, n)].append((src, dst, i))
        return paths

    def get_path_length_between_ip_nodes(self, src, dst):
        try:
            return nx.shortest_path_length(self.graph, src.lower_layer.id, dst.lower_layer.id, weight='weight')
        except nx.NetworkXNoPath:
            return np.inf

    def get_required_num_trunks(self, rate_to_allocate):
        """
        Returns the no. trunks required to allocate the given rate. Takes into account the max. link utilization value
        and the lightpath capacity.
        :param rate_to_allocate:
        :return:
        """
        factor = self.parameter.get(constants.KEY_IP_LINK_UTILIZATION, 1)
        return np.ceil(rate_to_allocate / factor /
                       self.parameter[constants.KEY_IP_LIGHTPATH_CAPACITY])
