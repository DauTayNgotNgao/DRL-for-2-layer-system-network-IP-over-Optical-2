class SolutionInstance(object):
    def __init__(self, ip_links, node_assignment, e2e_routing):
        self.ip_links = ip_links
        self.cdn_assignment = node_assignment
        self.e2e_routing = e2e_routing
        self._metrics = dict()

    def add_metric_value(self, name, value):
        if name in self._metrics:
            raise RuntimeError("Metric already exists.")
        self._metrics[name] = value

    def to_dict(self):
        return {
            'ip_links': [ip_link.to_dict() for ip_link in self.ip_links],
            'cdn_assignment': [hg.to_dict() for hg in self.cdn_assignment],
            'e2e_routing': [route.to_dict() for route in self.e2e_routing],
            'metrics': self._metrics
        }
