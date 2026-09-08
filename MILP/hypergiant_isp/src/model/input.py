class InputInstance(object):
    def __init__(self, topology, demandset, fixed_layers=None, background_demand=None):
        self.topology = topology
        self.demandset = demandset
        self.background_demand = background_demand
        self.fixed_layers = fixed_layers
        if self.fixed_layers is None:
            self.fixed_layers = dict()
