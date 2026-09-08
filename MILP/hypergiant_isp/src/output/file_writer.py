import json
import os
import logging
import hashlib
import output.abstract_output


class JsonWriterConfiguration(output.abstract_output.AbstractOutputConfiguration):
    def __init__(self, base_path):
        self.base_path = base_path

    def produce(self, scenario_config):
        return JsonWriter(
            self.base_path,
            scenario_config,
        )


class JsonWriter(output.abstract_output.AbstractOutput):
    def __init__(self, base_path, scenario_config):
        super(JsonWriter, self).__init__(scenario_config)
        self.base_path = base_path
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.fname = None

        self._construct_fname()

    def _construct_fname(self):
        """
        Hashes the string of the configuration dict and uses this as unique identifier for the configuration
        :return:
        """
        my_uuid = hashlib.sha256(bytes(str(self._scenario_config.to_dict()), encoding="utf-8")).hexdigest()
        self.fname = self._scenario_config.topology_configuration.config_name_prefix() + \
                     self._scenario_config.demand_configuration.config_name_prefix() + "_" + str(my_uuid)

    def solution_exists(self):
        return os.path.exists(os.path.join(self.base_path, "solution" + self.fname + ".json"))

    def write(self, solution):
        config_fname = os.path.join(self.base_path, "configuration" + self.fname + ".json")
        with open(config_fname, "w") as fd:
            json.dump(self._scenario_config.to_dict(), fp=fd, indent=2)
        self.logger.info("Wrote configuration to {}".format(config_fname))
        sol_fname = os.path.join(self.base_path, "solution" + self.fname + ".json")
        with open(sol_fname, "w") as fd:
            json.dump(solution.to_dict(), fp=fd, indent=2)
        self.logger.info("Wrote configuration to {}".format(sol_fname))
