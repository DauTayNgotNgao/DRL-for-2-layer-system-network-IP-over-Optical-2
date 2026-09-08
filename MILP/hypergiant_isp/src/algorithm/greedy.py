import collections
import logging

import numpy as np

import constants
from algorithm.abstract import AbstractAlgorithm, AbstractAlgorithmConfiguration


class GreedyCDNAssignmentAlgorithmConfiguration(AbstractAlgorithmConfiguration):
    def __init__(self, mip_config):
        self.mip_config = mip_config

    def produce(self, inputinstance) -> AbstractAlgorithm:
        return GreedyCDNAssignmentAlgorithm(
            inputinstance,
            self.mip_config
        )

    def to_dict(self) -> dict:
        return {
            'name': self.__class__.__name__,
            'mip_config': self.mip_config.to_dict()
        }


class GreedyCDNAssignmentAlgorithm(AbstractAlgorithm):
    def __init__(self, inputinstance, mip_config):
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.inputinstance = inputinstance
        self.mip_config = mip_config

        self.solution = None

    def run(self):
        assignment = dict()
        for hg in self.inputinstance.demandset:
            assignment[hg.name] = dict()
            allocation_per_peering_node = collections.defaultdict(float)
            for unode in sorted(hg.user_nodes, key=lambda x: x.demand_volume,
                                reverse=True):  # Sort unodes by their demand volume
                min_plength = np.inf
                min_pnode = None
                for pnode in hg.peering_nodes:
                    if (unode.demand_volume + allocation_per_peering_node[pnode] > pnode.capacity) or (
                            self.inputinstance.topology.get_required_num_trunks(
                                unode.demand_volume + allocation_per_peering_node[pnode]
                            ) > pnode.lower_layer.num_transceiver // 2
                    ):
                        # Not enough capacity available at peering node
                        continue

                    # Choose closest pnode according to optical topo
                    path_length = self.inputinstance.topology.get_path_length_between_ip_nodes(
                        unode.lower_layer, pnode.lower_layer
                    )
                    if path_length < min_plength:
                        min_pnode = pnode
                        min_plength = path_length
                allocation_per_peering_node[min_pnode] += unode.demand_volume
                assignment[hg.name][unode.id] = [(min_pnode.id, 1)]
        self.logger.info(assignment)
        if self.inputinstance.fixed_layers is not None:
            if constants.KEY_CDN_ASSIGNMENT_LAYER not in self.inputinstance.fixed_layers:
                self.inputinstance.fixed_layers.update(
                    {
                        constants.KEY_CDN_ASSIGNMENT_LAYER: assignment
                    }
                )
        else:
            self.inputinstance.fixed_layers = {
                constants.KEY_CDN_ASSIGNMENT_LAYER: assignment
            }
        mymip = self.mip_config.produce(self.inputinstance)
        mymip.run()

        self.solution = mymip.get_solution()

    def get_solution(self):
        return self.solution
