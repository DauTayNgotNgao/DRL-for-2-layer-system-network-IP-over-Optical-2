import csv
import logging
import itertools
import numpy as np

import constants
import model.demand


class AbstractDemandGenerator(object):
    def generate(self) -> tuple:
        """
        Creates demand set describing the enduser to CDN demands
        :return: (algorithm.input.DemandSet, algorithm.input.DemandMatrix)
        """
        raise NotImplementedError


class AbstractDemandGeneratorConfiguration(object):
    def to_dict(self) -> dict:
        raise NotImplementedError

    def produce(self, topology) -> AbstractDemandGenerator:
        raise NotImplementedError

    def config_name_prefix(self):
        """
        Returns a prefix for the name of the configuration
        :return:
        """
        raise NotImplementedError


class DemandMatrixCSVParser(object):
    """ Parses DemandMatrix (s-d demand pairs) from CSV file."""
    INDEX_TIMESTAMP = 0
    INDEX_SRC = 1
    INDEX_DST = 2
    INDEX_DEMAND = 3

    @classmethod
    def parse_demand_data(cls, fname_demand: str) -> dict:
        demands = dict()
        timestamp = None
        with open(fname_demand) as csvfile:
            read_csv = csv.reader(csvfile, delimiter=',')
            for row in read_csv:
                if timestamp is not None and row[DemandMatrixCSVParser.INDEX_TIMESTAMP] != timestamp:
                    break
                if len(row) == 4:
                    # background file
                    timestamp = row[DemandMatrixCSVParser.INDEX_TIMESTAMP]
                    src_node = row[DemandMatrixCSVParser.INDEX_SRC]
                    dst_node = row[DemandMatrixCSVParser.INDEX_DST]
                    rate = float(row[DemandMatrixCSVParser.INDEX_DEMAND])
                elif len(row) == 5:
                    # demand_single file (with AS number)
                    timestamp = row[DemandSetCSVParser.INDEX_TIMESTAMP]
                    src_node = row[DemandSetCSVParser.INDEX_CDN_ROUTER]
                    dst_node = row[DemandSetCSVParser.INDEX_ENDUSER_POP]
                    rate = float(row[DemandSetCSVParser.INDEX_DEMAND])

                if (src_node, dst_node) not in demands:
                    demands[(src_node, dst_node)] = rate
                else:
                    demands[(src_node, dst_node)] += rate
        return demands

    @classmethod
    def write_demand_data(cls, fname_matrix: str, demandset: model.demand.DemandMatrix, timestamp: int = 0) -> None:
        """

        Parameters
        ----------
        fname_demand: path and filename
        demandset: The demandset to be written
        timestamp:

        Returns
        -------

        """
        with open(fname_matrix, "w") as csvfile:
            read_csv = csv.writer(csvfile, delimiter=',')
            for (src, dst), rate in demandset.items():
                read_csv.writerow(
                    (timestamp, rate.node1.id, rate.node2.id, rate.volume)
                )


class DemandSetCSVParser(object):
    """
    Format for demand should be:
        hourTimestamp, cdn, end-user PoP name, demand volume in Gbps
    Format for peering should be:
        hourTimestamp, cdn, peering point name (router), capacity in Gbps
    """
    INDEX_TIMESTAMP = 0
    INDEX_CDN = 1
    INDEX_CDN_ROUTER = 2
    INDEX_ENDUSER_POP = 3
    INDEX_DEMAND = 4

    INDEX_PEERING_POP = 2
    INDEX_PEERING_CAPACITY = 3

    @classmethod
    def parse_demand_data(cls, fname_demand: str) -> dict:
        demands = dict()
        timestamp = None
        with open(fname_demand) as csvfile:
            read_csv = csv.reader(csvfile, delimiter=',')
            for row in read_csv:
                if timestamp is not None and row[DemandSetCSVParser.INDEX_TIMESTAMP] != timestamp:
                    break
                timestamp = row[DemandSetCSVParser.INDEX_TIMESTAMP]
                cdn = row[DemandSetCSVParser.INDEX_CDN]
                cdnrouter = row[DemandSetCSVParser.INDEX_CDN_ROUTER]
                enduser = row[DemandSetCSVParser.INDEX_ENDUSER_POP]
                rate = float(row[DemandSetCSVParser.INDEX_DEMAND])

                if cdn not in demands:
                    demands[cdn] = list()
                demands[cdn].append((cdnrouter, enduser, rate))
        return demands

    @classmethod
    def write_demand_data(cls, fname_demand: str, demandset: model.demand.DemandSet, timestamp: int = 0) -> None:
        """

        Parameters
        ----------
        fname_demand: path and filename
        demandset: The demandset to be written
        timestamp:

        Returns
        -------

        """
        with open(fname_demand, "w") as csvfile:
            read_csv = csv.writer(csvfile, delimiter=',')
            for cdn in demandset:
                for enduser in cdn.user_nodes:
                    unode = enduser.lower_layer.id
                    cdnname = cdn.name
                    cdnrouter = enduser.pre_peering_nodes[0][0].id
                    read_csv.writerow(
                        (timestamp, cdnname, cdnrouter, unode, enduser.demand_volume)
                    )

    @classmethod
    def parse_peering_data(cls, fname_peering: str) -> dict:
        peerings = dict()
        timestamp = None
        with open(fname_peering) as csvfile:
            read_csv = csv.reader(csvfile, delimiter=',')
            for row in read_csv:
                if timestamp is not None and row[DemandSetCSVParser.INDEX_TIMESTAMP] != timestamp:
                    break
                timestamp = row[DemandSetCSVParser.INDEX_TIMESTAMP]
                cdn = row[DemandSetCSVParser.INDEX_CDN]
                peering = row[DemandSetCSVParser.INDEX_PEERING_POP]
                capacity = float(row[DemandSetCSVParser.INDEX_PEERING_CAPACITY])

                if cdn not in peerings:
                    peerings[cdn] = list()
                peerings[cdn].append((peering, capacity))
        return peerings

    @classmethod
    def write_peering_data(cls, fname_peering: str, demandset: model.demand.DemandSet, timestamp: int = 0) -> None:
        with open(fname_peering, "w") as csvfile:
            write_csv = csv.writer(csvfile, delimiter=',')
            for cdn in demandset:
                for peering_node in cdn.peering_nodes:
                    write_csv.writerow(
                            (timestamp, cdn.name, peering_node.id[:-(len(cdn.name)+1)], peering_node.capacity)
                    )


class DemandSetGeneratorFromCSVConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, fname_demand, fname_peering, parameter=None):
        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand,
            'fname_peering': self.fname_peering,
            'parameter': self.parameter
        }

    def produce(self, topology):
        return DemandSetGeneratorFromCSV(
            fname_demand=self.fname_demand,
            fname_peering=self.fname_peering,
            parameter=self.parameter,
            topology=topology
        )

    def config_name_prefix(self):
        # Extract timestamp from fname_demand
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class DemandSetGeneratorFromCSV(AbstractDemandGenerator):
    """
    Generates demand set from CSV files. end-user demand and peering locations
    Format for demand should be:
        hourTimestamp, cdn, end-user PoP name, demand volume in Gbps
    Format for peering should be:
        hourTimestamp, cdn, peering point name (router), capacity in Gbps
    Only for static case, i.e., considers only the first timestamp in the file.

    """

    def __init__(self, fname_demand, fname_peering, parameter, topology):
        """

        :param fname_demand: path to CSV file with demand data
        :param fname_peering: path to CSV file with peering information
        :param topology: topology (IP nodes are relevant to map End-User nodes and peering nodes
        """
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)

        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter
        self.topology = topology

    def generate(self):
        demands = DemandSetCSVParser.parse_demand_data(self.fname_demand)
        peerings = DemandSetCSVParser.parse_peering_data(self.fname_peering)

        # There must be at least as many CDNs in the peering data as in the demand data
        assert len(peerings) >= len(demands)

        cdns = model.demand.DemandSet()
        for cdn_name, values in peerings.items():
            if cdn_name not in demands:
                self.logger.warning("No demand data for CDN {}".format(cdn_name))
                continue

            peering_nodes = list()
            for pnode, capacity in values:
                # Try to map to topology object
                try:
                    parent_node = self.topology.get_node_by_id(
                        pnode
                    )
                except ValueError:
                    self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                    continue

                peering_nodes.append(
                    model.demand.PeeringNode(
                        nid="{}-{}".format(pnode, cdn_name),
                        parent=parent_node,
                        capacity=capacity
                    )
                )

            user_nodes = list()
            for cdnrouter, unode, demand in demands[cdn_name]:
                if demand < constants.MIN_DEMAND:
                    continue
                try:
                    parent_node = self.topology.get_node_by_id(
                        unode
                    )
                except ValueError as e:
                    self.logger.fatal("User node {} not found".format(unode))
                    raise e

                user_nodes.append(
                    model.demand.EndUserNode(
                        nid="{}-{}-{}".format(unode, cdn_name, cdnrouter),
                        parent=parent_node,
                        demand_volume=demand
                    )
                )

            cdns.append(
                model.demand.Hypergiant(
                    name=cdn_name,
                    peering_nodes=peering_nodes,
                    user_nodes=user_nodes,
                    parameters=self.parameter.get(cdn_name, None)
                )
            )
        return cdns, None


class FixedCDNDemandGeneratorFromCSVConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, fname_demand, fname_peering, parameter=None):
        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand,
            'fname_peering': self.fname_peering,
            'parameter': self.parameter
        }

    def produce(self, topology):
        return FixedCDNDemandGeneratorFromCSV(
            fname_demand=self.fname_demand,
            fname_peering=self.fname_peering,
            parameter=self.parameter,
            topology=topology
        )

    def config_name_prefix(self):
        # Extract timestamp from fname_demand
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class FixedCDNDemandGeneratorFromCSV(AbstractDemandGenerator):
    """
    Generates demand set from CSV files. end-user demand and peering locations
    Format for demand should be:
        hourTimestamp, cdn, cdn router, end-user PoP name, demand volume in Gbps
    Format for peering should be:
        hourTimestamp, cdn, peering point name (router), capacity in Gbps
    Only for static case, i.e., considers only the first timestamp in the file.

    """
    def __init__(self, fname_demand, fname_peering, parameter, topology):
        """

        :param fname_demand: path to CSV file with demand data
        :param fname_peering: path to CSV file with peering information
        :param topology: topology (IP nodes are relevant to map End-User nodes and peering nodes
        """
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)

        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter
        self.topology = topology

    def generate(self):
        demands = DemandSetCSVParser.parse_demand_data(self.fname_demand)
        peerings = DemandSetCSVParser.parse_peering_data(self.fname_peering)

        # There must be at least as many CDNs in the peering data as in the demand data
        assert len(peerings) >= len(demands)

        cdns = model.demand.DemandSet()
        for cdn_name, values in peerings.items():
            if cdn_name not in demands:
                self.logger.warning("No demand data for CDN {}".format(cdn_name))
                continue

            peering_nodes = list()
            for pnode, capacity in values:
                # Try to map to topology object
                try:
                    parent_node = self.topology.get_node_by_id(
                        pnode
                    )
                except ValueError:
                    self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                    continue

                peering_nodes.append(
                    model.demand.PeeringNode(
                        nid="{}-{}".format(pnode, cdn_name),
                        parent=parent_node,
                        capacity=capacity
                    )
                )

            # Normalize and add as object
            user_nodes_list = list()
            for cdnnode, unode, demand in demands[cdn_name]:
                if demand < constants.MIN_DEMAND:
                    continue
                try:
                    parent_node = self.topology.get_node_by_id(
                        unode
                    )
                except ValueError as e:
                    self.logger.fatal("User node {} not found".format(unode))
                    raise e

                user_nodes_list.append(
                    model.demand.EndUserNode(
                        nid="{}-{}-{}".format(unode, cdn_name, cdnnode),
                        parent=parent_node,
                        demand_volume=demand,
                        pre_opt_peering_nodes=[(cdnnode, 1)]
                    )
                )

            cdns.append(
                model.demand.Hypergiant(
                    name=cdn_name,
                    peering_nodes=peering_nodes,
                    user_nodes=user_nodes_list,
                    parameters=self.parameter.get(cdn_name, None)
                )
            )
        return cdns, None


class BasicConnectivityDemandMatrixGeneratorConfiguration(AbstractDemandGeneratorConfiguration):
    def to_dict(self):
        return {
            'name': self.__class__.__name__
        }

    def produce(self, topology):
        return BasicConnectivityDemandMatrixGenerator(
            topology=topology
        )

    def config_name_prefix(self):
        return ""


class BasicConnectivityDemandMatrixGenerator(AbstractDemandGenerator):
    def __init__(self, topology):
        self.topology = topology

    def generate(self):
        matrix = model.demand.DemandMatrix()

        for e, f in itertools.product(self.topology.ip_nodes, repeat=2):
            if e == f or \
                    len(list(filter(lambda x: type(x) == model.demand.EndUserNode, e.upper_layer))) == 0 or \
                    len(list(filter(lambda x: type(x) == model.demand.EndUserNode, f.upper_layer))):
                continue
            dem = model.demand.EndToEndDemand(e, f, volume=1)  # Just for connectivity
            matrix[dem.key] = dem
        return None, matrix


class DemandMatrixFromCSVGeneratorConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, fname_demand):
        self.fname_demand = fname_demand

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand
        }

    def produce(self, topology):
        return DemandMatrixFromCSVGenerator(
            topology=topology,
            fname_demand=self.fname_demand
        )

    def config_name_prefix(self):
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class DemandMatrixFromCSVGenerator(AbstractDemandGenerator):
    def __init__(self, topology, fname_demand):
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.topology = topology
        self.fname_demand = fname_demand

    def generate(self):
        demands = DemandMatrixCSVParser.parse_demand_data(self.fname_demand)
        matrix = model.demand.DemandMatrix()

        for (e, f), rate in demands.items():
            try:
                e_node = self.topology.get_node_by_id(e)
            except ValueError as ex:
                self.logger.fatal("Source node {} not found".format(e))
                raise ex
            try:
                f_node = self.topology.get_node_by_id(f)
            except ValueError as ex:
                self.logger.fatal("Destination node {} not found".format(f))
                raise ex
            dem = model.demand.EndToEndDemand(e_node, f_node, volume=rate)
            matrix[dem.key] = dem
        return None, matrix


class CombinedDemandGeneratorConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, cdn_demand_config, bg_demand_config):
        self.cdn_demand_config = cdn_demand_config
        self.bg_demand_config = bg_demand_config

    def produce(self, topology):
        return CombinedDemandGenerator(
            self.cdn_demand_config.produce(topology),
            self.bg_demand_config.produce(topology)
        )

    def config_name_prefix(self):
        return self.cdn_demand_config.config_name_prefix()

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'cdn_demand': self.cdn_demand_config.to_dict(),
            'e2e_demand': self.bg_demand_config.to_dict()
        }


class CombinedDemandGenerator(AbstractDemandGenerator):
    def __init__(self, cdn_demand_gen, bg_demand_gen):
        self.cdn_demand_gen = cdn_demand_gen
        self.bg_demand_gen = bg_demand_gen

    def generate(self) -> tuple:
        cdn_demand, cdn_demand_matr = self.cdn_demand_gen.generate()
        _, bg_demand = self.bg_demand_gen.generate()

        if type(cdn_demand_matr) == model.demand.DemandMatrix and bg_demand is not None:
            bg_demand.merge(cdn_demand_matr)
        elif bg_demand is None:
            bg_demand = cdn_demand_matr

        return cdn_demand, bg_demand


class ShuffledDemandSetGeneratorFromCSVConfiguration(AbstractDemandGeneratorConfiguration):
    """

    """
    def __init__(self, fname_demand, fname_peering, seed=0, shuffle_peering=False, parameter=None):
        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter
        self.seed = seed
        self.shuffle_peering = shuffle_peering

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand,
            'fname_peering': self.fname_peering,
            'parameter': self.parameter,
            'seed': self.seed,
            'shuffle_peering': self.shuffle_peering
        }

    def produce(self, topology, rng=None):
        return ShuffledDemandSetGeneratorFromCSV(
            fname_demand=self.fname_demand,
            fname_peering=self.fname_peering,
            seed=self.seed,
            shuffle_peering=self.shuffle_peering,
            parameter=self.parameter,
            topology=topology,
            rng=rng
        )

    def config_name_prefix(self):
        # Extract timestamp from fname_demand
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class ShuffledDemandSetGeneratorFromCSV(AbstractDemandGenerator):
    """
    Generates demand set from CSV files. Shuffles end-user demands. Peering locations and CDNs are fixed
    Format for demand should be:
        hourTimestamp, cdn, end-user PoP name, demand volume in Gbps
    Format for peering should be:
        hourTimestamp, cdn, peering point name (router), capacity in Gbps
    Only for static case, i.e., considers only the first timestamp in the file.

    """

    def __init__(self, fname_demand, fname_peering, seed, shuffle_peering, parameter, topology, rng=None):
        """

        :param fname_demand: path to CSV file with demand data
        :param fname_peering: path to CSV file with peering information
        :param topology: topology (IP nodes are relevant to map End-User nodes and peering nodes
        """
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)

        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.shuffle_peering = shuffle_peering
        self.parameter = parameter
        self.topology = topology
        self.rng = rng
        if self.rng is None:
            self.rng = np.random.RandomState(seed=seed)

    def __shuffle_peering(self, parsed_peerings: list, cdn_name: str):
        # Re-shuffle for each CDN
        ip_peering_nodes = list()
        for ipn in self.topology.ip_nodes:
            city, router = ipn.id.split("-")
            if router[0] == "E":
                ip_peering_nodes.append(ipn)
        self.rng.shuffle(ip_peering_nodes)

        peering_node_mapping = dict()
        peering_nodes = list()
        for pnode, capacity in parsed_peerings:
            try:
                self.topology.get_node_by_id(pnode)
            except ValueError:
                self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                continue

            parent_node = ip_peering_nodes.pop()

            # Selected node is already a peering node. just add it
            peering_node_mapping[pnode] = parent_node
            peering_nodes.append(
                model.demand.PeeringNode(
                    nid="{}-{}".format(parent_node.id, cdn_name),
                    parent=parent_node,
                    capacity=capacity
                )
            )
        return peering_nodes, peering_node_mapping

    def generate(self):
        demands = DemandSetCSVParser.parse_demand_data(self.fname_demand)
        peerings = DemandSetCSVParser.parse_peering_data(self.fname_peering)

        # There must be at least as many CDNs in the peering data as in the demand data
        assert len(peerings) >= len(demands)

        cdns = model.demand.DemandSet()
        for cdn_name, values in peerings.items():
            if cdn_name not in demands:
                self.logger.warning("No demand data for CDN {}".format(cdn_name))
                continue

            if self.shuffle_peering:
                peering_nodes, peering_node_mapping = self.__shuffle_peering(parsed_peerings=values, cdn_name=cdn_name)
            else:
                # do not shuffle peerings
                peering_nodes = list()
                for pnode, capacity in values:
                    # Try to map to topology object
                    try:
                        parent_node = self.topology.get_node_by_id(
                            pnode
                        )
                    except ValueError:
                        self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                        continue

                    peering_nodes.append(
                        model.demand.PeeringNode(
                            nid="{}-{}".format(pnode, cdn_name),
                            parent=parent_node,
                            capacity=capacity
                        )
                    )

            # Get all end-user locations of this CDN and shuffle them
            unodes_shuffled = list()
            for _, unode, _ in demands[cdn_name]:
                unodes_shuffled.append(unode)
            self.rng.shuffle(unodes_shuffled)

            user_nodes = list()
            for cdnrouter, _, demand in demands[cdn_name]:
                if demand < constants.MIN_DEMAND:
                    continue
                # Pop last element from shuffled nodes
                unode = unodes_shuffled.pop()
                try:
                    parent_node = self.topology.get_node_by_id(
                        unode
                    )
                except ValueError as e:
                    self.logger.fatal("User node {} not found".format(unode))
                    raise e

                if self.shuffle_peering:
                    # Map CDN router to new one
                    cdnrouter = peering_node_mapping[cdnrouter]

                user_nodes.append(
                    model.demand.EndUserNode(
                        nid="{}-{}-{}".format(unode, cdn_name, cdnrouter),
                        parent=parent_node,
                        demand_volume=demand
                    )
                )

            cdns.append(
                model.demand.Hypergiant(
                    name=cdn_name,
                    peering_nodes=peering_nodes,
                    user_nodes=user_nodes,
                    parameters=self.parameter.get(cdn_name, None)
                )
            )
        return cdns, None


class ShuffledFixedCDNDemandGeneratorFromCSV(AbstractDemandGenerator):
    """
    Generates demand set from CSV files. Shuffles end-user demands. Peering locations and CDNs are fixed
    Format for demand should be:
        hourTimestamp, cdn, cdn router, end-user PoP name, demand volume in Gbps
    Format for peering should be:
        hourTimestamp, cdn, peering point name (router), capacity in Gbps
    Only for static case, i.e., considers only the first timestamp in the file.

    """
    def __init__(self, fname_demand, fname_peering, seed, shuffle_peering, parameter, topology, rng=None):
        """

        :param fname_demand: path to CSV file with demand data
        :param fname_peering: path to CSV file with peering information
        :param topology: topology (IP nodes are relevant to map End-User nodes and peering nodes
        """
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)

        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter
        self.topology = topology
        self.shuffle_peering = shuffle_peering
        self.rng = rng
        if self.rng is None:
            self.rng = np.random.RandomState(seed=seed)

    def __shuffle_peering(self, parsed_peerings: list, cdn_name: str):
        # Re-shuffle for each CDN
        ip_peering_nodes = list()
        for ipn in self.topology.ip_nodes:
            city, router = ipn.id.split("-")
            if router[0] == "E":
                ip_peering_nodes.append(ipn)
        self.rng.shuffle(ip_peering_nodes)

        peering_node_mapping = dict()
        peering_nodes = list()
        for pnode, capacity in parsed_peerings:
            try:
                self.topology.get_node_by_id(pnode)
            except ValueError:
                self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                continue

            parent_node = ip_peering_nodes.pop()

            # Selected node is already a peering node. just add it
            peering_node_mapping[pnode] = parent_node
            peering_nodes.append(
                model.demand.PeeringNode(
                    nid="{}-{}".format(parent_node.id, cdn_name),
                    parent=parent_node,
                    capacity=capacity
                )
            )
        return peering_nodes, peering_node_mapping

    def generate(self) -> (model.demand.DemandSet, None):
        demands = DemandSetCSVParser.parse_demand_data(self.fname_demand)
        peerings = DemandSetCSVParser.parse_peering_data(self.fname_peering)

        # There must be at least as many CDNs in the peering data as in the demand data
        assert len(peerings) >= len(demands)

        cdns = model.demand.DemandSet()
        for cdn_name, values in peerings.items():
            if cdn_name not in demands:
                self.logger.warning("No demand data for CDN {}".format(cdn_name))
                continue

            if self.shuffle_peering:
                peering_nodes, peering_node_mapping = self.__shuffle_peering(parsed_peerings=values, cdn_name=cdn_name)
            else:
                peering_nodes = list()
                for pnode, capacity in values:
                    try:
                        parent_node = self.topology.get_node_by_id(
                            pnode
                        )
                    except ValueError:
                        self.logger.warning("Peering node {} not found. Ignoring it.".format(pnode))
                        continue

                    peering_nodes.append(
                        model.demand.PeeringNode(
                            nid="{}-{}".format(pnode, cdn_name),
                            parent=parent_node,
                            capacity=capacity
                        )
                    )

            # Get all end-user locations of this CDN and shuffle them
            unodes_shuffled = list()
            for _, unode, _ in demands[cdn_name]:
                if unode not in unodes_shuffled:
                    unodes_shuffled.append(unode)
            unodes_non_shuffled = list(unodes_shuffled)
            self.rng.shuffle(unodes_shuffled)

            unode_mapping = dict(zip(unodes_non_shuffled, unodes_shuffled))
            user_nodes = list()
            # Use cdnrouter and demand to meet capacity constraint on the peering links
            for cdnrouter, orig_unode, demand in demands[cdn_name]:
                if demand < constants.MIN_DEMAND:
                    continue
                # Pop last element from shuffled nodes
                unode = unode_mapping[orig_unode]
                try:
                    parent_node = self.topology.get_node_by_id(
                        unode
                    )
                except ValueError as e:
                    self.logger.fatal("User node {} not found".format(unode))
                    raise e

                if self.shuffle_peering:
                    # Map CDN router to new one
                    cdnrouter = peering_node_mapping[cdnrouter]

                user_nodes.append(
                    model.demand.EndUserNode(
                        nid="{}-{}-{}".format(unode, cdn_name, cdnrouter),
                        parent=parent_node,
                        demand_volume=demand,
                        pre_opt_peering_nodes=[(cdnrouter, 1)]
                    )
                )

            cdns.append(
                model.demand.Hypergiant(
                    name=cdn_name,
                    peering_nodes=peering_nodes,
                    user_nodes=user_nodes,
                    parameters=self.parameter.get(cdn_name, None)
                )
            )
        return cdns, None


class ShuffledFixedCDNDemandGeneratorFromCSVConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, fname_demand, fname_peering, seed=0, shuffle_peering=False, parameter=None):
        self.fname_demand = fname_demand
        self.fname_peering = fname_peering
        self.parameter = parameter
        self.seed = seed
        self.shuffle_peering = shuffle_peering

    def to_dict(self) -> dict:
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand,
            'fname_peering': self.fname_peering,
            'parameter': self.parameter,
            'seed': self.seed,
            'shuffle_peering': self.shuffle_peering
        }

    def produce(self, topology, rng=None) -> ShuffledFixedCDNDemandGeneratorFromCSV:
        return ShuffledFixedCDNDemandGeneratorFromCSV(
            fname_demand=self.fname_demand,
            fname_peering=self.fname_peering,
            parameter=self.parameter,
            topology=topology,
            seed=self.seed,
            shuffle_peering=self.shuffle_peering,
            rng=rng
        )

    def config_name_prefix(self):
        # Extract timestamp from fname_demand
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class ShuffledDemandMatrixFromCSVGeneratorConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, fname_demand, seed=0):
        self.fname_demand = fname_demand
        self.seed = seed

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'fname_demand': self.fname_demand,
            'seed': self.seed
        }

    def produce(self, topology, rng=None):
        return ShuffledDemandMatrixFromCSVGenerator(
            topology=topology,
            fname_demand=self.fname_demand,
            seed=self.seed,
            rng=rng
        )

    def config_name_prefix(self):
        return self.fname_demand.split("/")[-1].replace(".csv", "").replace("demand", "")


class ShuffledDemandMatrixFromCSVGenerator(AbstractDemandGenerator):
    def __init__(self, topology, fname_demand, seed, rng=None):
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.topology = topology
        self.fname_demand = fname_demand
        self.rng = rng
        if self.rng is None:
            self.rng = np.random.RandomState(seed=seed)

    def generate(self):
        demands = DemandMatrixCSVParser.parse_demand_data(self.fname_demand)
        matrix = model.demand.DemandMatrix()

        rates = list()
        pairs = list()
        for (e, f), rate in demands.items():
            try:
                e_node = self.topology.get_node_by_id(e)
            except ValueError as ex:
                self.logger.fatal("Source node {} not found".format(e))
                raise ex
            try:
                f_node = self.topology.get_node_by_id(f)
            except ValueError as ex:
                self.logger.fatal("Destination node {} not found".format(f))
                raise ex
            pairs.append((e_node, f_node))
            rates.append(rate)
        self.rng.shuffle(rates)
        for (e_node, f_node), rate in zip(pairs, rates):
            dem = model.demand.EndToEndDemand(e_node, f_node, volume=rate)
            matrix[dem.key] = dem
        return None, matrix


class ShuffledCombinedDemandGeneratorConfiguration(AbstractDemandGeneratorConfiguration):
    def __init__(self, cdn_demand_config, bg_demand_config, seed=0):
        self.cdn_demand_config = cdn_demand_config
        self.bg_demand_config = bg_demand_config
        self.seed = seed

    def produce(self, topology):
        return ShuffledCombinedDemandGenerator(
            self.cdn_demand_config.produce(topology),
            self.bg_demand_config.produce(topology),
            self.seed
        )

    def config_name_prefix(self):
        return self.cdn_demand_config.config_name_prefix()

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'cdn_demand': self.cdn_demand_config.to_dict(),
            'e2e_demand': self.bg_demand_config.to_dict(),
            'seed': self.seed
        }


class ShuffledCombinedDemandGenerator(AbstractDemandGenerator):
    def __init__(self, cdn_demand_gen, bg_demand_gen, seed, rng=None):
        self.cdn_demand_gen = cdn_demand_gen
        self.bg_demand_gen = bg_demand_gen
        self.rng = rng
        if self.rng is None:
            self.rng = np.random.RandomState(seed)

    def generate(self) -> tuple:
        cdn_demand, cdn_demand_matr = self.cdn_demand_gen.generate(self.rng)
        _, bg_demand = self.bg_demand_gen.generate(self.rng)

        if type(cdn_demand_matr) == model.demand.DemandMatrix and bg_demand is not None:
            bg_demand.merge(cdn_demand_matr)
        elif bg_demand is None:
            bg_demand = cdn_demand_matr

        return cdn_demand, bg_demand
