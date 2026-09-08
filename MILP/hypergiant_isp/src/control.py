import multiprocessing
import logging

import scenario


class AbstractRunner(object):
    def __init__(self, list_of_scenario_configs):
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self._scenario_configs = list_of_scenario_configs

    def run_all(self):
        raise NotImplementedError


class SequentialRunner(AbstractRunner):
    def __init__(self, list_of_scenario_configs):
        super(SequentialRunner, self).__init__(list_of_scenario_configs)

    def run_all(self):
        for sconfig in self._scenario_configs:
            sconfig.produce().run()


class ParallelRunner(AbstractRunner):
    def __init__(self, list_of_scenario_configs, num_jobs=2):
        super(ParallelRunner, self).__init__(list_of_scenario_configs)
        self.worker_pool = multiprocessing.Pool(num_jobs)

    def run_all(self):
        self.worker_pool.map(
            scenario.run_scenario,
            self._scenario_configs
        )
