class AbstractOutputConfiguration(object):
    def produce(self, scenario_config):
        raise NotImplementedError


class AbstractOutput(object):
    def __init__(self, scenario_config):
        self._scenario_config = scenario_config

    def write(self, solution):
        """
        Takes a configuration an solution instances and writes it out
        :param solution: instance of solution
        :return:
        """
        raise NotImplementedError

    def solution_exists(self):
        """
        Checks if this configuration has already been solved and the solution exists in the storage
        :return:
        """
        raise NotImplementedError
