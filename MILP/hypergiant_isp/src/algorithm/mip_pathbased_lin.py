import collections
import itertools

import gurobipy as grb
from ortools.linear_solver import pywraplp

import constants
import model.demand
import model.topology
from algorithm.abstract import AbstractAlgorithmConfiguration
from algorithm.mip import AbstractMixedIntegerProgram, add_variables_from_iterator


class PathBasedMixedIntegerProgramConfiguration(AbstractAlgorithmConfiguration):
    def __init__(self, model_implementor, num_threads=1, relaxed=False, time_limit=None):
        self.model_implementor = model_implementor
        self.num_threads = num_threads
        self.relaxed = relaxed
        self.time_limit = time_limit

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'model_implementor': self.model_implementor,
            'num_threads': self.num_threads,
            'relaxed': self.relaxed,
            'time_limit': self.time_limit
        }

    def produce(self, inputinstance):
        return PathMixedIntegerProgram(
            inputinstance=inputinstance,
            model_implementor=self.model_implementor,
            num_threads=self.num_threads,
            relaxed=self.relaxed,
            time_limit=self.time_limit
        )


class PathMixedIntegerProgram(AbstractMixedIntegerProgram):
    """
    Builds the linearized model for the static scenario with unsplittable flows.
    """
    VARIABLE_SUPER_FLOW_CDN_INTEGER = False
    VARIABLE_FLOW_CDN_INTEGER = True
    VARIABLE_FLOW_E2E_INTEGER = True
    VARIABLE_IP_LINK_CAPACITY_INTEGER = True

    class IteratorVariablesFlowsOfHypergiant(object):
        def __init__(self, hypergiant, topology):
            self._internal_iter = itertools.filterfalse(
                lambda x: x[1] == x[2],
                itertools.product(
                    hypergiant.user_nodes,
                    topology.ip_nodes,
                    topology.ip_nodes
                )
            )

        def __iter__(self):
            return self

        def __next__(self):
            res = next(self._internal_iter)
            return res[0], res[1], res[2]

    class IteratorVariablesFlowsEndToEnd(object):
        def __init__(self, matrix, topology):
            self._internal_iter = itertools.filterfalse(
                lambda x: x[1] == x[2],
                itertools.product(
                    matrix.keys(),
                    topology.ip_nodes,
                    topology.ip_nodes
                )
            )

        def __iter__(self):
            return self

        def __next__(self):
            res = next(self._internal_iter)
            return res[0][0], res[0][1], res[1], res[2]

    class IteratorVariablesIpCapacity(object):
        def __init__(self, topology):
            tuples = list()
            for e, f in itertools.filterfalse(
                    lambda x: x[0] == x[1],
                    itertools.product(topology.ip_nodes, topology.ip_nodes)
            ):
                num_paths = len(topology.get_all_optical_candidate_paths_between_ip_nodes(e, f))
                tuples.append(
                    zip([e] * num_paths, [f] * num_paths, range(num_paths))
                )
            self._internal_iter = itertools.chain(*tuples)

        def __iter__(self):
            return self

        def __next__(self):
            res = next(self._internal_iter)
            return res[0], res[1], res[2]

    def __init__(self, inputinstance, model_implementor=AbstractMixedIntegerProgram.MODEL_IMPLEMENTOR_CBC,
                 num_threads=None, relaxed=False, time_limit=None):
        super(PathMixedIntegerProgram, self).__init__(inputinstance, model_implementor, num_threads, time_limit)

        self.variables = dict()
        self.constraints = dict()
        self.objective = None
        self.result_status = None

        if relaxed:
            self.flow_variable_types = {
                "flow_cdn": False,
                "flow_e2e": False,
                "ip_capacity": False
            }
        else:
            self.flow_variable_types = {
                "flow_cdn": PathMixedIntegerProgram.VARIABLE_FLOW_CDN_INTEGER,
                "flow_e2e": PathMixedIntegerProgram.VARIABLE_FLOW_E2E_INTEGER,
                "ip_capacity": PathMixedIntegerProgram.VARIABLE_IP_LINK_CAPACITY_INTEGER
            }

    def build(self):
        super(PathMixedIntegerProgram, self).build()
        self.fix_layers()

    def build_variables(self):
        if self.inputinstance.demandset:
            self.build_variable_flow_cdn()
        if self.inputinstance.background_demand:
            self.build_variable_flow_e2e()
        self.build_variable_ip_capacity()

        self.logger.debug("Model has {} variables".format(self.model_impl.NumVariables()))

    def build_constraints(self):
        self.build_constraint_ip_link_capacity()
        self.build_constraint_degree_limit()
        if self.inputinstance.demandset:
            self.build_constraint_peering_capacity_super()
            self.build_constraint_flow_conservation_cdn()

        if self.inputinstance.background_demand:
            self.build_constraint_flow_conservation_e2e()

        self.build_constraint_fiber_capacity()
        self.build_constraint_max_ip_utilization()

        self.logger.debug("Model has {} constraints".format(self.model_impl.NumConstraints()))

    def build_variable_flow_cdn(self):
        """
        Adds flow variables to model and stores references in variables dict.
        If CDNs have fixed peering, the bounds of the variables are fixed accordingly.
        :return:
        """
        self.variables["flow_cdn"] = dict()
        self.variables["flow_super"] = dict()

        for h in self.inputinstance.demandset:
            new_vars = add_variables_from_iterator(
                model_impl=self.model_impl,
                is_integer=self.flow_variable_types["flow_cdn"],
                iterator=PathMixedIntegerProgram.IteratorVariablesFlowsOfHypergiant(h, self.inputinstance.topology),
                lb=0,
                ub=1,
                name="flow_{}".format(h.name)
            )

            self.variables["flow_cdn"][h.name] = new_vars
            self.logger.debug("Added {} flow variables".format(len(new_vars)))

            new_vars = add_variables_from_iterator(
                model_impl=self.model_impl,
                is_integer=self.flow_variable_types["flow_cdn"],
                iterator=itertools.product(h.user_nodes, h.peering_nodes),
                lb=0,
                ub=1,
                name="flow_super_{}".format(h.name)
            )
            self.variables["flow_super"][h.name] = new_vars
            self.logger.debug("Added {} super-flow variables".format(len(new_vars)))

            for unode in h.user_nodes:
                if unode.pre_peering_nodes is None:
                    continue
                self.logger.debug(f"{unode} has fixed CDN demands.")
                for pnode, fraction in unode.pre_peering_nodes:
                    # Works only if fraction = 1
                    try:
                        pnode = h.get_peering_node(pnode)
                        self.variables["flow_super"][h.name][unode, pnode].SetBounds(fraction, fraction)
                    except ValueError as e:
                        print(f"Peering node {pnode} not found. Flow volume {unode.demand_volume}")
                        raise e

    def build_variable_flow_e2e(self):
        self.variables["flow_e2e"] = add_variables_from_iterator(
            model_impl=self.model_impl,
            is_integer=self.flow_variable_types["flow_e2e"],
            iterator=PathMixedIntegerProgram.IteratorVariablesFlowsEndToEnd(self.inputinstance.background_demand,
                                                                            self.inputinstance.topology),
            lb=0,
            ub=1,
            name="flow_e2e"
        )
        self.logger.debug("Added {} e2e-flow variables".format(len(self.variables["flow_e2e"])))

    def build_variable_ip_capacity(self):
        self.variables['ip_capacity'] = add_variables_from_iterator(
            model_impl=self.model_impl,
            is_integer=self.flow_variable_types["ip_capacity"],
            iterator=PathMixedIntegerProgram.IteratorVariablesIpCapacity(self.inputinstance.topology),
            lb=0,
            ub=self.model_impl.infinity(),
            name="ip_capacity"
        )
        self.logger.debug("Added {} IP trunk capacity variables".format(len(self.variables["ip_capacity"])))

    def build_constraint_peering_capacity_super(self):
        for hg in self.inputinstance.demandset:
            for peeringnode in hg.peering_nodes:
                vars_list = [unode.demand_volume * self.variables["flow_super"][hg.name][unode, peeringnode] for unode
                             in
                             hg.user_nodes]
                lhs = self.model_impl.Sum(vars_list)
                self.model_impl.Add(
                    lhs <= peeringnode.capacity,
                    name="peering_capacity{}_{}".format(
                        hg.name,
                        peeringnode
                    )
                )

    def build_constraint_flow_conservation_cdn(self):
        for hg in self.inputinstance.demandset:
            # End user nodes: Ingressing flow = total flow from CDN
            for unode in hg.user_nodes:
                lhs = self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                    unode, unode.lower_layer, '*'
                ))
                lhs -= self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                    unode, '*', unode.lower_layer
                ))
                self.model_impl.Add(
                    lhs == -1,
                    name="ip_flow_conservation_unodes_{}_{}".format(hg.name, unode)
                )

                # IP nodes that are neither the current end user node nor peering nodes of the current CDN
                for e in self.inputinstance.topology.ip_nodes:

                    if len(e.upper_layer) > 0:
                        if unode in e.upper_layer or set(e.upper_layer) & set(hg.peering_nodes):
                            continue

                    lhs = self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                        unode, e, '*'
                    )) - self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                        unode, '*', e
                    ))

                    self.model_impl.Add(
                        lhs == 0,
                        name="ip_flow_conservation_{}_{}_{}".format(hg.name, unode, e)
                    )

                # Peering nodes. Use additional edge to super source
                for pnode in hg.peering_nodes:
                    lhs = self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                        unode, pnode.lower_layer, '*'
                    )) - self.variables["flow_super"][hg.name].select(unode, pnode)[0]
                    self.model_impl.Add(
                        lhs == 0,
                        name="ip_flow_conservation_pnode_{}_{}_{}".format(hg.name, unode, pnode)
                    )

                # Super source
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables['flow_super'][hg.name].select(unode)) == 1,
                    name="ip_flow_conservation_super_{}_{}".format(hg.name, unode)
                )

    def build_constraint_flow_conservation_e2e(self):
        for k, dem in self.inputinstance.background_demand.items():
            for e in self.inputinstance.topology.ip_nodes:
                # If e is a peering router only and not the destination, only allow outgoing flows.
                if "-E" in e.id and e != dem.node2:
                    lhs = self.model_impl.Sum(
                        self.variables["flow_e2e"].select(*dem.key, e, '*')
                    )
                else:
                    lhs = self.model_impl.Sum(
                        self.variables["flow_e2e"].select(*dem.key, e, '*')
                    ) - self.model_impl.Sum(
                        self.variables["flow_e2e"].select(*dem.key, '*', e)
                    )

                if dem.node1 == e:
                    # Source node:
                    self.model_impl.Add(
                        lhs == 1,
                        name="ip_flow_conservation_e2e_{}_{}".format(dem.key, e)
                    )
                elif dem.node2 == e:
                    # Target node:
                    self.model_impl.Add(
                        lhs == - 1,
                        name="ip_flow_conservation_e2e_{}_{}".format(dem.key, e)
                    )
                else:
                    self.model_impl.Add(
                        lhs == 0,
                        name="ip_flow_conservation_e2e_{}_{}".format(dem.key, e)
                    )

                # The following constraints remove routing loops
                self.model_impl.Add(
                    self.model_impl.Sum(
                        self.variables["flow_e2e"].select(*dem.key, e, '*')
                    ) <= 1,
                    name="ip_routing_restriction_e2e_out_{}_{}".format(dem.key, e)
                )
                self.model_impl.Add(
                    self.model_impl.Sum(
                        self.variables["flow_e2e"].select(*dem.key, '*', e)
                    ) <= 1,
                    name="ip_routing_restriction_e2e_in_{}_{}".format(dem.key, e)
                )

    def build_constraint_ip_link_capacity(self):
        for e, f in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes,
                                  self.inputinstance.topology.ip_nodes)
        ):
            lhs = 0
            if self.inputinstance.demandset:
                for hg in self.inputinstance.demandset:
                    lhs += self.model_impl.Sum(
                        [v * usernode.demand_volume for usernode in hg.user_nodes for v in
                         self.variables["flow_cdn"][hg.name].select(
                             usernode, e, f)]
                    )

            if self.inputinstance.background_demand:
                lhs += self.model_impl.Sum(
                    [v * dem.volume for dem in self.inputinstance.background_demand.values() for v in
                     self.variables["flow_e2e"].select(*dem.key, e, f)]
                )

            rhs = self.model_impl.Sum(
                self.variables['ip_capacity'].select(e, f, '*')
            )
            self.model_impl.Add(
                lhs <= self.inputinstance.topology.parameter[constants.KEY_IP_LIGHTPATH_CAPACITY] * rhs,
                name='ip_capacity_{}_{}'.format(e, f)
            )

        for e, f in itertools.filterfalse(
                lambda x: x[0].id >= x[1].id,
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            for i, var in enumerate(self.variables['ip_capacity'].select(e, f, '*')):
                self.model_impl.Add(
                    var == self.variables['ip_capacity'][f, e, i],
                    name=f"ip_link_bidirect_{e}_{f}_{i}"
                )

    def build_constraint_degree_limit(self):
        for e in self.inputinstance.topology.ip_nodes:
            lhs = self.model_impl.Sum(self.variables['ip_capacity'].select(e, '*', '*')) + \
                  self.model_impl.Sum(self.variables['ip_capacity'].select('*', e, '*'))
            self.model_impl.Add(
                lhs <= e.num_transceiver * 2,  # to account for bidirectionality of links
                name='limit_degree_{}'.format(e)
            )

    def build_constraint_fiber_capacity(self):
        for oedge in self.inputinstance.topology.opt_edges.values():
            on1 = oedge.node1
            on2 = oedge.node2

            lhs = self.model_impl.Sum([
                self.variables['ip_capacity'][e, f, i] for e, f, i in
                self.inputinstance.topology.candidate_paths_per_opt_edge[(on1.id, on2.id)]
            ]
            )
            self.model_impl.Add(
                lhs <= oedge.capacity,
                name="fiber_capacity_{}_{}".format(on1, on2)
            )

    def build_constraint_max_ip_utilization(self):
        if constants.KEY_IP_LINK_UTILIZATION not in self.inputinstance.topology.parameter:
            self.logger.info("No IP link utilization limit provided. Skipping this constraint.")
            return
        for e, f in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            lhs = 0
            if self.inputinstance.demandset:
                for hg in self.inputinstance.demandset:
                    for unode in hg.user_nodes:
                        lhs += self.model_impl.Sum(self.variables["flow_cdn"][hg.name].select(
                            unode, e, f
                        )) * unode.demand_volume
            if self.inputinstance.background_demand:
                lhs += self.model_impl.Sum(
                    [v * dem.volume for dem in self.inputinstance.background_demand.values() for v in
                     self.variables["flow_e2e"].select(*dem.key, e, f)])
            self.model_impl.Add(
                lhs <= self.inputinstance.topology.parameter[constants.KEY_IP_LINK_UTILIZATION] *
                self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) *
                self.inputinstance.topology.parameter[constants.KEY_IP_LIGHTPATH_CAPACITY],
                name="max_ip_link_util_{}_{}".format(e, f)
            )

    def build_objective(self):
        self.model_impl.Minimize(
            self.model_impl.Sum(self.variables["ip_capacity"].select())
        )

        # Try also to set a lower bound
        if self.inputinstance.demandset:
            unique_usernodes = set()
            for hg in self.inputinstance.demandset:
                for unode in hg.user_nodes:
                    unique_usernodes.add(unode.lower_layer)

            lb_capacity_unodes = collections.defaultdict(float)
            for hg in self.inputinstance.demandset:
                for unode in hg.user_nodes:
                    lb_capacity_unodes[unode.lower_layer] += unode.demand_volume
            lb_capacity = 0
            for unode in lb_capacity_unodes:
                lb_capacity += self.inputinstance.topology.get_required_num_trunks(lb_capacity_unodes[unode])

            self.model_impl.Add(
                self.model_impl.Sum(self.variables["ip_capacity"].select()) >= lb_capacity * 2  # Bi-directional paths
            )
            self.logger.info("Lower bound for objective is {}".format(lb_capacity))

    def fix_cdn_layer(self):
        """
        Fixes the variables for the End-user to peering point assignment to the provided values
        :return:
        """
        if constants.KEY_CDN_ASSIGNMENT_LAYER not in self.inputinstance.fixed_layers:
            return

        self.logger.info("Fixing cdn layer...")
        for hg in self.inputinstance.demandset:
            if hg.name not in self.inputinstance.fixed_layers[constants.KEY_CDN_ASSIGNMENT_LAYER]:
                continue
            self.logger.info("Fixing variables for CDN {}".format(hg.name))
            for unode in hg.user_nodes:
                if unode.id not in self.inputinstance.fixed_layers[constants.KEY_CDN_ASSIGNMENT_LAYER][hg.name]:
                    continue
                for assigned_pnode_id, fraction in \
                        self.inputinstance.fixed_layers[constants.KEY_CDN_ASSIGNMENT_LAYER][hg.name][unode.id]:
                    assert fraction <= 1.0
                    for pnode in hg.peering_nodes:
                        if pnode.id == assigned_pnode_id:
                            # Fix value to provided fraction
                            self.variables["flow_super"][hg.name][unode, pnode].SetBounds(fraction, fraction)
                            break

    def fix_ip_links(self):
        """
        Fixes existing IP links. Capacity can be increased but not decreased
        """
        if constants.KEY_IP_LINK_LAYER not in self.inputinstance.fixed_layers or \
                constants.KEY_RECONF_FRACTION_IP in self.inputinstance.fixed_layers or \
                constants.KEY_RECONF_FRACTION_IP_W_OPT in self.inputinstance.fixed_layers:
            return
        self.logger.info("Fixing ip links...")
        old_nodes = set()
        for n in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER]:
            old_nodes.update([n[0], n[1]])

        for (e, f) in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            if (e.id, f.id) in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER]:
                cap = self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER][(e.id, f.id)]
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) >= cap
                )
            elif e.id in old_nodes and f.id in old_nodes:
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) == 0
                )

    def fix_full_ip_links(self):
        """
        Fully fixes the IP links. This means that all links have the given capacity or are actively set to 0
        No reconfigurations are possible
        """
        if constants.KEY_IP_LINK_LAYER_FULL not in self.inputinstance.fixed_layers:
            return

        self.logger.info("Fixing full ip links...")
        old_nodes = set()
        for n in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER_FULL]:
            old_nodes.update([n[0], n[1]])

        for (e, f) in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            if (e.id, f.id) in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER_FULL]:
                cap = self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER_FULL][(e.id, f.id)]["num_trunks"]
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) == cap
                )
            else:  # if e.id in old_nodes and f.id in old_nodes:
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) == 0
                )

    def limit_reconf_ip_links_w_opt(self):
        """
        Limits reconfiguration of IP links. This covers num. of capacity increases and cap. decreases, additions and
        removals and path changes in the optical topology
        """
        if constants.KEY_IP_LINK_LAYER not in self.inputinstance.fixed_layers or \
                constants.KEY_RECONF_FRACTION_IP_W_OPT not in self.inputinstance.fixed_layers or \
                constants.KEY_RECONF_FRACTION_IP in self.inputinstance.fixed_layers:
            return

        self.logger.info("Limiting reconfigurations of  ip links...")
        self.variables['ip_rc_increase_opt'] = grb.tupledict()
        self.variables['ip_rc_decrease_opt'] = grb.tupledict()

        for (e, f, p) in PathMixedIntegerProgram.IteratorVariablesIpCapacity(self.inputinstance.topology):
            self.variables['ip_rc_increase_opt'][(e, f, p)] = self.model_impl.IntVar(0, 1,
                                                                                     f"ip_rc_increase_{(e, f, p)}")
            self.variables['ip_rc_decrease_opt'][(e, f, p)] = self.model_impl.IntVar(0, 1,
                                                                                     f"ip_rc_decrease_{(e, f, p)}")

            cap = 0
            if (e.id, f.id) in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER]:
                try:
                    cap = self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER][(e.id, f.id)][p]
                except IndexError:
                    pass
            self.model_impl.Add(
                self.variables["ip_capacity"][(e, f, p)] - cap <=
                self.variables["ip_rc_increase_opt"][(e, f, p)] * constants.BIG_M
            )
            self.model_impl.Add(
                cap - self.variables["ip_capacity"][(e, f, p)] <=
                self.variables["ip_rc_decrease_opt"][(e, f, p)] * constants.BIG_M
            )
        self.logger.debug("Added {} IP capacity w opt path reconf variables".format(
            len(self.variables["ip_rc_increase_opt"]) + len(self.variables["ip_rc_decrease_opt"]))
        )

        self.variables['ip_rc_increase'] = grb.tupledict()
        self.variables['ip_rc_decrease'] = grb.tupledict()

        for (e, f) in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            self.variables['ip_rc_increase'][(e, f)] = self.model_impl.IntVar(0, 1, f"ip_rc_increase_{(e, f)}")
            self.variables['ip_rc_decrease'][(e, f)] = self.model_impl.IntVar(0, 1, f"ip_rc_decrease_{(e, f)}")

            self.model_impl.Add(
                self.model_impl.Sum(self.variables["ip_rc_increase_opt"].select(e, f, '*')) <=
                self.variables["ip_rc_increase"][e, f] * constants.BIG_M
            )
            self.model_impl.Add(
                self.model_impl.Sum(self.variables["ip_rc_decrease_opt"].select(e, f, '*')) <=
                self.variables["ip_rc_decrease"][e, f] * constants.BIG_M
            )

        self.logger.debug("Added {} IP trunk capacity reconf variables".format(
            len(self.variables["ip_rc_increase"]) + len(self.variables["ip_rc_decrease"]))
        )

        self.model_impl.Add(
            self.model_impl.Sum(self.variables["ip_rc_increase"].select()) +
            self.model_impl.Sum(self.variables["ip_rc_decrease"].select()) <=
            self.inputinstance.fixed_layers[constants.KEY_RECONF_FRACTION_IP_W_OPT] * len(
                self.inputinstance.topology.ip_nodes) ** 2
        )

    def limit_reconf_ip_links(self):
        """
        Limits reconfiguration of IP links. This covers num. of capacity increases and cap. decreases, additions and
        removals
        """
        if constants.KEY_IP_LINK_LAYER not in self.inputinstance.fixed_layers or \
                constants.KEY_RECONF_FRACTION_IP not in self.inputinstance.fixed_layers:
            return

        self.logger.info("Limiting reconfigurations of  ip links...")
        self.variables['ip_rc_increase'] = grb.tupledict()
        self.variables['ip_rc_decrease'] = grb.tupledict()

        for (e, f) in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            self.variables['ip_rc_increase'][(e, f)] = self.model_impl.IntVar(0, 1, f"ip_rc_increase_{(e, f)}")
            self.variables['ip_rc_decrease'][(e, f)] = self.model_impl.IntVar(0, 1, f"ip_rc_decrease_{(e, f)}")

            cap = 0
            if (e.id, f.id) in self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER]:
                values = self.inputinstance.fixed_layers[constants.KEY_IP_LINK_LAYER][(e.id, f.id)]
                cap = values
            self.model_impl.Add(
                self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) - cap <=
                self.variables["ip_rc_increase"][e, f] * constants.BIG_M
            )
            self.model_impl.Add(
                cap - self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) <=
                self.variables["ip_rc_decrease"][e, f] * constants.BIG_M
            )

        self.logger.debug("Added {} IP trunk capacity reconf variables".format(
            len(self.variables["ip_rc_increase"]) + len(self.variables["ip_rc_decrease"]))
        )

        self.model_impl.Add(
            self.model_impl.Sum(self.variables["ip_rc_increase"].select()) +
            self.model_impl.Sum(self.variables["ip_rc_decrease"].select()) <=
            self.inputinstance.fixed_layers[constants.KEY_RECONF_FRACTION_IP] * len(
                self.inputinstance.topology.ip_nodes) ** 2
        )

    def fix_ip_connectivity(self):
        """
        Fixes IP connectivity. This means links' capacities can be increased or decreased but additions or removals
        are not possible
        """
        if constants.KEY_IP_CONNECTIVITY not in self.inputinstance.fixed_layers:
            return

        self.logger.info("Fixing ip connectivity...")
        old_nodes = set()
        for n in self.inputinstance.fixed_layers[constants.KEY_IP_CONNECTIVITY]:
            old_nodes.update([n[0], n[1]])
        for (e, f) in itertools.filterfalse(
                lambda x: x[0] == x[1],
                itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
        ):
            if (e.id, f.id) in self.inputinstance.fixed_layers[constants.KEY_IP_CONNECTIVITY]:
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) >= 1
                )
            elif e.id in old_nodes and f.id in old_nodes:
                self.model_impl.Add(
                    self.model_impl.Sum(self.variables["ip_capacity"].select(e, f, '*')) == 0
                )

    def fix_layers(self):
        self.fix_cdn_layer()
        self.fix_ip_links()
        self.fix_full_ip_links()
        self.fix_ip_connectivity()
        self.limit_reconf_ip_links()
        self.limit_reconf_ip_links_w_opt()

    def print_solution(self):
        print('Solution:')
        if self.result_status == pywraplp.Solver.INFEASIBLE:
            print("Problem instance is infeasible")
            self.write("debug_inf_model.lp")
        else:
            assert self.model_impl.VerifySolution(1e-7, True)
            print('Objective value =', self.model_impl.Objective().Value())
            for var3 in self.variables.values():
                for var2 in var3.values():
                    if isinstance(var2, dict):
                        for var in var2.values():
                            if var.solution_value() > 0:
                                print(var, var.solution_value())
                    else:
                        if var2.solution_value() > 0:
                            print(var2, var2.solution_value())
            print('\nAdvanced usage:')
            print('Problem solved in %f milliseconds' % self.model_impl.wall_time())
            print('Problem solved in %d iterations' % self.model_impl.iterations())
            print('Problem solved in %d branch-and-bound nodes' % self.model_impl.nodes())

    def _extract_ip_links(self):
        ip_links = list()
        opt_links = collections.defaultdict(int)
        sum_trunks = 0
        old_ip_link = (None, None)
        for e, f, path_num in PathMixedIntegerProgram.IteratorVariablesIpCapacity(self.inputinstance.topology):
            if old_ip_link != (e, f):
                if len(opt_links) > 0:
                    # We have filled an IP link previously
                    opt_links_list = [(k[0], k[1], v, k[2]) for k, v in opt_links.items()]
                    ip_links.append(
                        model.topology.IPLink(
                            old_ip_link[0], old_ip_link[1], sum_trunks, opt_links_list
                        )
                    )

                opt_links = collections.defaultdict(int)
                sum_trunks = 0
                old_ip_link = (e, f)
            var = self.variables["ip_capacity"][e, f, path_num]
            if var.solution_value() > 0:
                sum_trunks += var.solution_value()
                opt_path = self.inputinstance.topology.get_all_optical_candidate_paths_between_ip_nodes(e, f)[path_num]
                if len(opt_path) > 1:
                    for m, n in zip(opt_path[:-1], opt_path[1:]):
                        node_m = self.inputinstance.topology.get_node_by_id(m)
                        node_n = self.inputinstance.topology.get_node_by_id(n)
                        opt_links[(node_m, node_n, path_num)] += var.solution_value()
                else:
                    node = self.inputinstance.topology.get_node_by_id(opt_path[0])
                    opt_links[(node, node, path_num)] += var.solution_value()
        if len(opt_links) > 0:
            # We have filled an IP link previously
            opt_links_list = [(k[0], k[1], v, k[2]) for k, v in opt_links.items()]
            ip_links.append(
                model.topology.IPLink(
                    old_ip_link[0], old_ip_link[1], sum_trunks, opt_links_list
                )
            )
        return ip_links

    def _extract_cdn_assignment(self):
        assignments = list()
        if self.inputinstance.demandset is None:
            return assignments
        for hg in self.inputinstance.demandset:
            unodes_assign = list()
            for unode in hg.user_nodes:
                peering_nodes = dict()
                for pnode in hg.peering_nodes:
                    var = self.variables["flow_super"][hg.name][unode, pnode]
                    if var.solution_value() > 0:
                        peering_nodes[pnode] = var.solution_value()
                allocations = list()
                for e, f in itertools.filterfalse(lambda x: x[0] == x[1],
                                                  itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)):
                    var = self.variables["flow_cdn"][hg.name][unode, e, f]
                    if var.solution_value() > 0:
                        allocations.append(
                            model.demand.Allocation(e, f, var.solution_value())
                        )

                unodes_assign.append(
                    model.demand.UserNodeAssignment(unode, peering_nodes, allocations)
                )
            assignments.append(
                model.demand.HypergiantAssignment(
                    hg.name, unodes_assign
                )
            )
        return assignments

    def _extract_e2e_routing(self):
        routes = list()
        if self.inputinstance.background_demand is None:
            return routes

        for k, dem in self.inputinstance.background_demand.items():
            routed_dem = model.demand.RoutedEndToEndDemand(dem.node1, dem.node2)
            for e, f in itertools.filterfalse(
                    lambda x: x[0] == x[1],
                    itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)
            ):
                var = self.variables["flow_e2e"].select(*dem.key, e, f)[0]
                if var.solution_value() > 0:
                    routed_dem.add_path((e.id, f.id), var.solution_value() * dem.volume)
            routes.append(routed_dem)
        return routes

    def set_solution_hint(self, solution):
        hint_vars = list()
        hint_values = list()
        for iplink in solution.ip_links:
            cand_paths = self.inputinstance.topology.get_all_optical_candidate_paths_between_ip_nodes(
                iplink.node1, iplink.node2
            )
            if len(iplink.opt_links) > 1:
                opt_path = [o[0].id for o in iplink.opt_links] + [iplink.opt_links[-1][1].id]
            else:
                opt_path = iplink.opt_links
            for i, cand_path in enumerate(cand_paths):
                hint_vars.append(self.variables["ip_capacity"][iplink.node1, iplink.node2, i])
                if cand_path == opt_path:
                    # Use num of trunks on first hop of optical path
                    hint_values.append(iplink.opt_links[0][2])
                else:
                    hint_values.append(0)

        for hg in solution.cdn_assignment:
            for unode in hg.user_nodes:
                super_flow_vars = list(self.variables["flow_super"][hg.name].select(unode, '*'))
                for pnode, frac in unode.peering_nodes:
                    this_var = self.variables["flow_super"][hg.name][unode, pnode]
                    hint_vars.append(this_var)
                    hint_values.append(frac)
                    super_flow_vars.remove(this_var)
                for sfv in super_flow_vars:
                    hint_vars.append(sfv)
                    hint_values.append(0)
                for e, f in itertools.filterfalse(lambda x: x[0] == x[1],
                                                  itertools.product(self.inputinstance.topology.ip_nodes, repeat=2)):
                    var = self.variables["flow_cdn"][hg.name][unode, e, f]
                    relevant_routers = list(filter(lambda x: x.node1 == e and x.node2 == f, unode.routes))
                    hint_vars.append(var)
                    try:
                        hint_values.append(relevant_routers[0].volume)
                    except IndexError:
                        hint_values.append(0)

        self.model_impl.SetHint(hint_vars, hint_values)
