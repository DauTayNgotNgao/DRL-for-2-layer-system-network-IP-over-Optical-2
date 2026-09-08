import traceback
import logging

import model.input


class ScenarioConfiguration(object):
    def __init__(self, topology_configuration, demand_configuration, algorithm_configuration,
                 fixed_layers, outputs=None, comment=""):
        self.topology_configuration = topology_configuration
        self.demand_configuration = demand_configuration
        self.algorithm_configuration = algorithm_configuration
        self.fixed_layers = fixed_layers
        self.outputs = outputs
        if self.outputs is None:
            self.outputs = list()
        self.comment = comment

    def to_dict(self):
        return {
            'name': self.__class__.__name__,
            'topology': self.topology_configuration.to_dict(),
            'demand': self.demand_configuration.to_dict(),
            'algorithm': self.algorithm_configuration.to_dict(),
            'fixed_layers': self.fixed_layers.to_dict(),
            'comment': self.comment
        }

    def produce(self):
        topo = self.topology_configuration.produce().generate()
        demand, demand_matrix = self.demand_configuration.produce(topo).generate()
        inputinstance = model.input.InputInstance(topo, demand, fixed_layers=self.fixed_layers.produce(),
                                                  background_demand=demand_matrix)
        algo = self.algorithm_configuration.produce(inputinstance)

        return Scenario(
            self,
            topo,
            demand,
            algo,
            self.outputs
        )


class Scenario(object):
    def __init__(self, cfg, topology, demandset, algorithm, outputs):
        self.logger = logging.getLogger(self.__module__ + '.' + self.__class__.__name__)
        self.config = cfg
        self.topology = topology
        self.demandset = demandset
        self.algorithm = algorithm
        self.output_configs = outputs
        self.outputs = list()

    def build_outputs(self):
        if len(self.outputs) > 0:
            return
        for out_cfg in self.output_configs:
            self.outputs.append(out_cfg.produce(self.config))

    def check_solution(self):
        """
        Checks if configuration was already solved
        :return:
        """
        for output in self.outputs:
            if output.solution_exists():
                return True
        return False

    def run(self):
        self.build_outputs()
        if self.check_solution():
            self.logger.info(f"Scenario has already been solved. Skipping.")
            return

        # Run algorithm
        self.algorithm.run()

        # Get and save solution
        sol = self.algorithm.get_solution()

        for output in self.outputs:
            output.write(sol)
        self.logger.info(f"Scenario successfully solved.")
        return sol


def run_scenario(config):
    """
    Builds and runs the given scenario configuration
    :param config:
    :return:
    """
    try:
        config.produce().run()
    except Exception as e:
        print(e)
        traceback.print_exc()
