import logging
import csv
import constants


import model.topology


class AbstractTopologyGeneratorConfiguration(object):
    def to_dict(self):
        raise NotImplementedError

    def produce(self):
        raise NotImplementedError

    def config_name_prefix(self):
        """
        Returns a prefix for the name of the configuration
        :return:
        """
        raise NotImplementedError


class AbstractTopologyGenerator(object):
    def __init__(self):
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)

    def generate(self, topology=None):
        raise NotImplementedError


class SimpleOpticalTopologyGeneratorConfiguration(AbstractTopologyGeneratorConfiguration):
    FIBER_CAPACITY = 10

    def __init__(self, fiber_capacity=None):
        self.fiber_capacity = fiber_capacity
        if self.fiber_capacity is None:
            self.fiber_capacity = self.FIBER_CAPACITY

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fiber_capacity': self.fiber_capacity
        }

    def produce(self):
        return SimpleOpticalTopologyGenerator(self.fiber_capacity)

    def config_name_prefix(self):
        return ""


class SimpleOpticalTopologyWithFailureGeneratorConfiguration(SimpleOpticalTopologyGeneratorConfiguration):
    def __init__(self, fiber_capacity=None, failed_links=None):
        super(SimpleOpticalTopologyWithFailureGeneratorConfiguration, self).__init__(fiber_capacity)
        self.failed_links = failed_links

    def to_dict(self):
        out = super(SimpleOpticalTopologyWithFailureGeneratorConfiguration, self).to_dict()
        out["failed_links"] = self.failed_links
        return out

    def produce(self):
        return SimpleOpticalTopologyGenerator(self.fiber_capacity, self.failed_links)


class FiberFailureTopologyConfigurationGenerator(object):
    def __init__(self, basic_config):
        self.basic_config = basic_config
        self.failures = list(SimpleOpticalTopologyGenerator.OPT_EDGES)

    def __next__(self):
        try:
            failed_link = self.failures.pop()
            return SimpleOpticalTopologyWithFailureGeneratorConfiguration(
                fiber_capacity=self.basic_config.fiber_capacity,
                failed_links=[failed_link]
            )
        except IndexError:
            raise StopIteration

    def __iter__(self):
        return self


class SimpleOpticalTopologyGenerator(AbstractTopologyGenerator):
    """
    Generates the basic optical topology with edges
    """
    OPT_EDGES = [
        # FIXME REDACTED due to data privacy
    ]

    OPT_EDGE_WEIGHTS = {
        # FIXME REDACTED due to data privacy
    }

    def __init__(self, fiber_capacity, failed_links=None):
        super(SimpleOpticalTopologyGenerator, self).__init__()
        self.fiber_capacity = fiber_capacity
        self.failed_links = failed_links
        if failed_links is None:
            self.failed_links = list()

    def generate(self, topology=None):
        if topology is None:
            topology = model.topology.Topology()
        cities = [
            # FIXME REDACTED due to data privacy
        ]
        for name in cities:
            opt_node = model.topology.OpticalNode(nid=name)
            topology.add_node(opt_node)

        # Add edges between the PoPs
        for e, f in self.OPT_EDGES:
            if (e, f) in self.failed_links:
                continue
            weight = self.OPT_EDGE_WEIGHTS[(e, f)]
            e = topology.get_node_by_id(e)
            f = topology.get_node_by_id(f)
            # For fiber failure set the capacity to 0 so that we still have the same shortest paths in optical domain
            # so that they are compatible with input from previous solution
            cap = self.fiber_capacity if str((e, f)) not in self.failed_links else 0
            topology.add_edge(
                # ON provides us the same number of lambdas on all fibers
                model.topology.OpticalLink(e, f, capacity=cap),
                weight
            )
            topology.add_edge(
                model.topology.OpticalLink(f, e, capacity=cap),
                weight
            )
        return topology


class HardCodedOpticalTopologyGeneratorConfiguration(AbstractTopologyGeneratorConfiguration):
    FIBER_CAPACITY = 10

    def __init__(self, nodes, links, fiber_capacity=None):
        self.fiber_capacity = fiber_capacity
        if self.fiber_capacity is None:
            self.fiber_capacity = self.FIBER_CAPACITY

        self.nodes = nodes
        self.links = links

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fiber_capacity': self.fiber_capacity,
            'nodes': self.nodes,
            'links': self.links
        }

    def produce(self):
        return HardCodedOpticalTopologyGenerator(self.nodes, self.links, self.fiber_capacity)

    def config_name_prefix(self):
        return ""


class HardCodedOpticalTopologyGenerator(AbstractTopologyGenerator):
    """
    Generates the optical topology with edges from hardcoded lists
    """

    def __init__(self, nodes, links, fiber_capacity):
        super(HardCodedOpticalTopologyGenerator, self).__init__()
        self.fiber_capacity = fiber_capacity
        self.nodes = nodes
        self.links = links

    def generate(self, topology=None):
        if topology is None:
            topology = model.topology.Topology()
        for name in self.nodes:
            opt_node = model.topology.OpticalNode(nid=name)
            topology.add_node(opt_node)

        # Add edges between the PoPs
        for e, f in self.links:
            e = topology.get_node_by_id(e)
            f = topology.get_node_by_id(f)
            topology.add_edge(
                # OTN provides us the same number of lambdas on all fibers
                model.topology.OpticalLink(e, f, capacity=self.fiber_capacity)
            )
            topology.add_edge(
                model.topology.OpticalLink(f, e, capacity=self.fiber_capacity)
            )
        return topology


class IPNodesFromCSVGeneratorConfiguration(AbstractTopologyGeneratorConfiguration):
    NUM_TRANSCEIVER = 10

    def __init__(self, fname, num_transceiver=None):
        self.fname = fname

        self.num_transceiver = num_transceiver
        if self.num_transceiver is None:
            self.num_transceiver = self.NUM_TRANSCEIVER

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname': self.fname,
            'num_transceiver': self.num_transceiver
        }

    def produce(self):
        return IPNodesFromCSVGenerator(self.fname, self.num_transceiver)

    def config_name_prefix(self):
        return ""


class IPNodesFromCSVGenerator(AbstractTopologyGenerator):
    """
    Reads IP nodes from CSV file.
    Format must be:
        node_id

    where node id is something like 'X' or 'X-Y' and X is identifier of optical nodes

    """
    INDEX_IP_NODE = 0

    def __init__(self, fname, num_transceiver):
        super(IPNodesFromCSVGenerator, self).__init__()

        self.fname = fname
        self.ip_nodes = list()

        self.num_transceiver = num_transceiver

    def parse_ip_node_data(self):
        with open(self.fname) as csvfile:
            read_csv = csv.reader(csvfile, delimiter=',')
            for row in read_csv:
                self.ip_nodes.append(row[IPNodesFromCSVGenerator.INDEX_IP_NODE])

    def generate(self, topology=None):
        self.parse_ip_node_data()
        if topology is None:
            raise ValueError("No optical topology provided.")

        for n in self.ip_nodes:
            parent = topology.get_node_by_id(
                "O-{}".format(n.split("-")[0])
            )
            topology.add_node(
                model.topology.IPNode(
                    nid=n,
                    parent=parent,
                    num_transceiver=self.num_transceiver
                )
            )
        return topology


class ComposedTopologyGeneratorConfiguration(AbstractTopologyGeneratorConfiguration):
    def __init__(self, opt_topo_gen_config, ip_topo_gen_config, parameter=None):
        self.opt_topo_gen_config = opt_topo_gen_config
        self.ip_topo_gen_config = ip_topo_gen_config
        self.parameter = parameter

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'opt_topo': self.opt_topo_gen_config.to_dict(),
            'ip_topo': self.ip_topo_gen_config.to_dict(),
            'parameter': self.parameter
        }

    def produce(self):
        return ComposedTopologyGenerator(
            opt_topo_generator=self.opt_topo_gen_config.produce(),
            ip_topo_generator=self.ip_topo_gen_config.produce(),
            parameter=self.parameter
        )

    def config_name_prefix(self):
        prefix = self.opt_topo_gen_config.config_name_prefix() + self.ip_topo_gen_config.config_name_prefix()
        if constants.KEY_IP_LINK_UTILIZATION in self.parameter:
            prefix += "_link_util"
        return prefix


class ComposedTopologyGenerator(AbstractTopologyGenerator):
    def __init__(self, opt_topo_generator, ip_topo_generator, parameter=None):
        super(ComposedTopologyGenerator, self).__init__()
        self.opt_topo_generator = opt_topo_generator
        self.ip_topo_generator = ip_topo_generator
        self.parameter = parameter

    def generate(self, topology=None):
        if topology is None:
            topology = model.topology.Topology(parameter=self.parameter)
        topology = self.opt_topo_generator.generate(topology)
        return self.ip_topo_generator.generate(topology)
