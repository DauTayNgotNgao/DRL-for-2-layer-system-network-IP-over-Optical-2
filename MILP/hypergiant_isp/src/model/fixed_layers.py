import constants
import json


class AbstractFixedLayersConfiguration(object):
    def to_dict(self):
        raise NotImplementedError

    def produce(self):
        raise NotImplementedError

    def config_name_prefix(self):
        raise NotImplementedError


class HardCodedFixedLayersConfiguration(AbstractFixedLayersConfiguration):
    def __init__(self, ip_links=None, cdn_assignment=None):
        """

        :param ip_links: dict of ip links, key like "x<->Y" and value like
            {'num_trunks': 2, 'opt_links': [('O-B', 'O-A', 2)]}
        :param cdn_assignment: dict of cdn assignment
        """
        self.ip_links = ip_links
        if self.ip_links is not None:
            assert isinstance(self.ip_links, dict)
        self.cdn_assignment = cdn_assignment
        if self.cdn_assignment is not None:
            assert isinstance(self.cdn_assignment, dict)

    def to_dict(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = self.ip_links

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        return out

    def produce(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER_FULL] = dict()
            for k, val in self.ip_links.items():
                out[constants.KEY_IP_LINK_LAYER_FULL][tuple(k.split("<->"))] = val

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        return out

    def config_name_prefix(self):
        out = ""
        if self.ip_links is not None:
            out += "_ip_links"
        if self.cdn_assignment is not None:
            out += "_cdn_assignment"
        return out


class HardCodedFixedLayersLimitedReconfigurationConfiguration(AbstractFixedLayersConfiguration):
    def __init__(self, ip_links=None, limit_links=0.0, cdn_assignment=None, limit_cdn=0.0):
        """

        :param ip_links: dict of ip links, key like "x<->Y" and value like
            {'num_trunks': 2, 'opt_links': [('O-B', 'O-A', 2)]}
        :param cdn_assignment: dict of cdn assignment
        """
        self.ip_links = ip_links
        if self.ip_links is not None:
            assert isinstance(self.ip_links, dict)
        self.cdn_assignment = cdn_assignment
        if self.cdn_assignment is not None:
            assert isinstance(self.cdn_assignment, dict)
        self.limit_ip = limit_links
        self.limit_cdn = limit_cdn

    def to_dict(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = self.ip_links
        out['fix_ip_links'] = self.limit_ip

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        out['fix_cdn_assignment'] = self.limit_cdn
        return out

    def produce(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = dict()
            for k, val in self.ip_links.items():
                out[constants.KEY_IP_LINK_LAYER][tuple(k.split("<->"))] = val
            out[constants.KEY_RECONF_FRACTION_IP] = self.limit_ip

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        return out

    def config_name_prefix(self):
        out = ""
        if self.ip_links is not None:
            out += "_ip_links"
        if self.cdn_assignment is not None:
            out += "_cdn_assignment"
        return out


class HardCodedWithOptPathLimitedReconfigurationConfiguration(AbstractFixedLayersConfiguration):
    def __init__(self, ip_links=None, limit_links=0.0, cdn_assignment=None, limit_cdn=0.0):
        """

        :param ip_links: dict of ip links, key like "x<->Y" and value like
            [[cap, [(O-A,O-B),(O-B,O-C)...]]
        :param cdn_assignment: dict of cdn assignment
        """
        self.ip_links = ip_links
        if self.ip_links is not None:
            assert isinstance(self.ip_links, dict)
        self.cdn_assignment = cdn_assignment
        if self.cdn_assignment is not None:
            assert isinstance(self.cdn_assignment, dict)
        self.limit_ip = limit_links
        self.limit_cdn = limit_cdn

    def to_dict(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = self.ip_links
        out['fix_ip_links_w_opt'] = self.limit_ip

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        out['fix_cdn_assignment'] = self.limit_cdn
        return out

    def produce(self):
        out = dict()
        if self.ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = dict()
            for k, val in self.ip_links.items():
                out[constants.KEY_IP_LINK_LAYER][tuple(k.split("<->"))] = [ol[0] for ol in val]
            out[constants.KEY_RECONF_FRACTION_IP_W_OPT] = self.limit_ip

        if self.cdn_assignment is not None:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = self.cdn_assignment
        return out

    def config_name_prefix(self):
        out = ""
        if self.ip_links is not None:
            out += "_ip_links"
        if self.cdn_assignment is not None:
            out += "_cdn_assignment"
        return out


class FromSolutionFileFixedLayersConfiguration(AbstractFixedLayersConfiguration):
    def __init__(self, path_to_file, ip_links=False, ip_connectivity=False, cdn_assignment=False, strict=False):
        """

        :param path_to_file (str): path to solution file (json)
        :param ip_links (bool): True to fully fix IP links
        :param ip_connectivity (bool): True to fix only IP adjacencies but not capacity (overwritten by ip_links)
        :param cdn_assignment (bool): True to fix CDN assignment
        :param strict (bool): Enforce exact link capacities
        """
        self.path_to_file = path_to_file
        self.fix_ip_links = ip_links
        self.fix_ip_connectivity = ip_connectivity
        self.fix_cdn_assignment = cdn_assignment
        self.strict = strict

        self.ip_links = None
        self.ip_connectivity = None
        self.cdn_assignment = None

    def to_dict(self):
        return {
            'path_to_solution_file': self.path_to_file,
            'fix_ip_links': self.fix_ip_links,
            'fix_ip_connectivity': self.fix_ip_connectivity,
            'fix_cdn_assignment': self.fix_cdn_assignment,
            'strict': self.strict
        }

    def produce(self):
        out = dict()
        with open(self.path_to_file, "r") as fd:
            solution = json.load(fd)
        print(self.path_to_file)
        iplayer_key = constants.KEY_IP_LINK_LAYER_FULL if self.strict else constants.KEY_IP_LINK_LAYER
        if self.fix_ip_links:
            out[iplayer_key] = dict()
            for link in solution["ip_links"]:
                if self.strict:
                    out[iplayer_key][(link["node1"], link["node2"])] = {"num_trunks": link["num_trunks"]}
                else:
                    out[iplayer_key][(link["node1"], link["node2"])] = link["num_trunks"]

        elif self.fix_ip_connectivity:
            out[constants.KEY_IP_CONNECTIVITY] = list()
            for link in solution["ip_links"]:
                out[constants.KEY_IP_CONNECTIVITY].append((link["node1"], link["node2"]))

        if self.fix_cdn_assignment:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = dict()
            for cdn in solution["cdn_assignment"]:
                out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]] = dict()
                for unode in cdn["user_nodes"]:
                    out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]][unode["node_id"]] = list()
                    for pnode in unode["peering_nodes"]:
                        out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]][unode["node_id"]].append((pnode[0], pnode[1]))
        return out

    def config_name_prefix(self):
        out = ""
        if self.fix_ip_links:
            out += "_ip_links"
        elif self.fix_ip_connectivity:
            out += "_ip_links"
        if self.fix_cdn_assignment:
            out += "_cdn_assignment"
        return out


class FromSolutionFileLimitedReconfigurationConfiguration(AbstractFixedLayersConfiguration):
    def __init__(self, path_to_file, ip_links=None, ip_connectivity=None, cdn_assignment=None):
        """

        :param path_to_file (str): path to solution file (json)
        :param ip_links (float): fraction of allowed IP link reconfigurations w.r.t. squared number of IP nodes
        :param ip_connectivity (bool): True to fix only IP adjacencies but not capacity (overwritten by ip_links)
        :param cdn_assignment (bool): True to fix CDN assignment
        """
        self.path_to_file = path_to_file
        self.fix_ip_links = ip_links
        self.fix_ip_connectivity = ip_connectivity
        self.fix_cdn_assignment = cdn_assignment

        self.ip_links = None
        self.ip_connectivity = None
        self.cdn_assignment = None

    def to_dict(self):
        return {
            'path_to_solution_file': self.path_to_file,
            'fix_ip_links': self.fix_ip_links,
            'fix_ip_connectivity': self.fix_ip_connectivity,
            'fix_cdn_assignment': self.fix_cdn_assignment
        }

    def produce(self):
        out = dict()
        with open(self.path_to_file, "r") as fd:
            solution = json.load(fd)
        print(self.path_to_file)
        if self.fix_ip_links is not None:
            out[constants.KEY_IP_LINK_LAYER] = dict()
            for link in solution["ip_links"]:
                out[constants.KEY_IP_LINK_LAYER][(link["node1"], link["node2"])] = link["num_trunks"]
            out[constants.KEY_RECONF_FRACTION_IP] = self.fix_ip_links

        elif self.fix_ip_connectivity:
            out[constants.KEY_IP_CONNECTIVITY] = list()
            for link in solution["ip_links"]:
                out[constants.KEY_IP_CONNECTIVITY].append((link["node1"], link["node2"]))
            out[constants.KEY_RECONF_FRACTION_IP] = self.fix_ip_links

        if self.fix_cdn_assignment:
            out[constants.KEY_CDN_ASSIGNMENT_LAYER] = dict()
            for cdn in solution["cdn_assignment"]:
               out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]] = dict()
               for unode in cdn["user_nodes"]:
                   out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]][unode["node_id"]] = list()
                   for pnode in unode["peering_nodes"]:
                       out[constants.KEY_CDN_ASSIGNMENT_LAYER][cdn["name"]][unode["node_id"]].append((pnode[0], pnode[1]))
        return out

    def config_name_prefix(self):
        out = ""
        if self.fix_ip_links:
            out += "_ip_links"
        elif self.fix_ip_connectivity:
            out += "_ip_links"
        if self.fix_cdn_assignment:
            out += "_cdn_assignment"
        return out
