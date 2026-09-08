class AbstractAlgorithm(object):
    def run(self):
        raise NotImplementedError

    def get_solution(self):
        raise NotImplementedError


class AbstractAlgorithmConfiguration(object):
    def to_dict(self) -> dict:
        raise NotImplementedError

    def produce(self, inputinstance) -> AbstractAlgorithm:
        raise NotImplementedError
