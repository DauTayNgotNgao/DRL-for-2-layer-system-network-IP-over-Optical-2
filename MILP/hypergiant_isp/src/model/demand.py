from model.topology import Node, IPNode


class EndUserNode(Node):
    def __init__(self, nid, parent, demand_volume, pre_opt_peering_nodes=None):
        """

        :param nid:
        :param parent:
        :param demand_volume: Rate of demand
        :param pre_opt_peering_nodes: List of tuples of (peering_node, fraction) to indicate assignment before
            optimization. This is used to fix CDN assignments
        """
        assert isinstance(parent, IPNode)
        super(EndUserNode, self).__init__(nid, parent)
        parent.upper_layer.append(self)
        self._demand_volume = demand_volume

        self._pre_peering_nodes = pre_opt_peering_nodes

    @property
    def demand_volume(self):
        return self._demand_volume

    @property
    def pre_peering_nodes(self):
        return self._pre_peering_nodes

    def __repr__(self):
        return "EUN-{}({})".format(self.id, self.lower_layer)


class PeeringNode(Node):
    def __init__(self, nid, parent, capacity):
        """

        :param nid:
        :param parent:
        :param capacity: Capacity of peering link (rate)
        """
        assert isinstance(parent, IPNode)
        super(PeeringNode, self).__init__(nid, parent)
        parent.upper_layer.append(self)
        self._capacity = capacity

    @property
    def capacity(self):
        return self._capacity

    def __repr__(self):
        return "PN-{}({})".format(self.id, self.lower_layer)


class DemandSet(list):
    pass


class Hypergiant(object):
    def __init__(self, name, peering_nodes=None, user_nodes=None, parameters=None):
        self.name = name
        self._peering_nodes = peering_nodes
        if self._peering_nodes is None:
            self._peering_nodes = list()

        self._user_nodes = user_nodes
        if self._user_nodes is None:
            self._user_nodes = list()

        self._parameters = parameters
        if self._parameters is None:
            self._parameters = dict()

    @property
    def peering_nodes(self):
        return self._peering_nodes

    @property
    def user_nodes(self):
        return self._user_nodes

    @property
    def parameters(self):
        return self._parameters

    def get_peering_node(self, name):
        for p in self.peering_nodes:
            if name in p.id:
                return p
        raise ValueError("Peering node not found.")


class UserNodeAssignment(object):
    def __init__(self, unode, peering_nodes, ip_routes):
        self._unode = unode
        self._peering_nodes = peering_nodes
        self._ip_routes = ip_routes

    @property
    def id(self):
        return self._unode.id

    @property
    def peering_nodes(self):
        return self._peering_nodes

    @property
    def routes(self):
        return self._ip_routes

    def to_dict(self):
        return {
            'node_id': self.id,
            'peering_nodes': [(pnode.id, frac) for (pnode, frac) in self.peering_nodes.items()],
            'routes': [(r.node1.id, r.node2.id, r.volume) for r in self._ip_routes]
        }


class Allocation(object):
    def __init__(self, node1, node2, vol):
        self._node1 = node1
        self._node2 = node2
        self._volume = vol

    @property
    def node1(self):
        return self._node1

    @property
    def node2(self):
        return self._node2

    @property
    def volume(self):
        return self._volume


class HypergiantAssignment(object):
    def __init__(self, hg_name, unodes):
        self._name = hg_name
        self._unodes = unodes

    @property
    def name(self):
        return self._name

    @property
    def user_nodes(self):
        return self._unodes

    def to_dict(self):
        return {
            'name': self.name,
            'user_nodes': [unode.to_dict() for unode in self.user_nodes]
        }


class DemandMatrix(dict):
    def merge(self, other_matrix):
        assert type(other_matrix) == DemandMatrix

        for k, e2edemand in other_matrix.items():
            if k in self:
                self[k].volume += e2edemand.volume
            else:
                self[k] = e2edemand


class EndToEndDemand(object):
    """
    Directed IP node to IP node demand
    """

    def __init__(self, start, end, volume):
        self.node1 = start
        self.node2 = end
        self.volume = volume

    @property
    def key(self):
        return str(self.node1), str(self.node2)


class RoutedEndToEndDemand(object):
    def __init__(self, start, end):
        self.node1 = start
        self.node2 = end
        self.paths = list()

    def add_path(self, path, volume):
        self.paths.append((path, volume))

    def to_dict(self):
        return {
            'node1': self.node1.id,
            'node2': self.node2.id,
            'paths': self.paths
        }
