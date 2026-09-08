import collections
import numpy as np


class MetricsCalculator(object):
    @classmethod
    def calculate_all(cls, sol):
        if not isinstance(sol, dict):
            sol_dict = sol.to_dict()
        else:
            sol_dict = sol
        updated_metrics = dict()
        updated_metrics.update(MetricsCalculator.calculate_num_deployed_ip_trunks(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_mean_fiber_utilization(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_max_fiber_utilization(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_nodal_degrees(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_ip_utilization(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_num_ip_links(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_total_lightpath_hops(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_weighted_total_lightpath_hops(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_path_length_ip_hops(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_path_length_opt_hops(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_distribution_path_length_ip_hops(sol_dict))
        updated_metrics.update(MetricsCalculator.calculate_distribution_capacities(sol_dict))

        if not isinstance(sol, dict):
            for k, v in updated_metrics.items():
                sol.add_metric_value(
                    k, v
                )
        else:
            return updated_metrics

    @staticmethod
    def calculate_num_ip_links(sol_dict):
        return {"num_ip_links": len(sol_dict["ip_links"])}

    @classmethod
    def calculate_num_deployed_ip_trunks(cls, sol_dict):
        num_trunks = 0
        for ip_link in sol_dict["ip_links"]:
            num_trunks += ip_link["num_trunks"]

        return {"deployed_ip_trunks": num_trunks}

    @classmethod
    def calculate_distribution_capacities(cls, sol_dict):
        trunks = list()
        for ip_link in sol_dict["ip_links"]:
            trunks.append(int(ip_link["num_trunks"]))

        return {"distribution_ip_trunks": trunks}

    @classmethod
    def calculate_total_lightpath_hops(cls, sol_dict):
        num_total_lp_hops = 0
        for ip_link in sol_dict["ip_links"]:
            num_total_lp_hops += len(ip_link["opt_links"])
        return {
            "total_num_lightpath_hops": num_total_lp_hops
        }

    @classmethod
    def calculate_weighted_total_lightpath_hops(cls, sol_dict):
        num_total_lp_hops = 0
        for ip_link in sol_dict["ip_links"]:
            num_total_lp_hops += len(ip_link["opt_links"]) * ip_link["num_trunks"]
        return {
            "total_weighted_lightpath_hops": num_total_lp_hops
        }

    @classmethod
    def calculate_max_fiber_utilization(cls, sol_dict):
        num_waves_per_fiber = collections.defaultdict(int)
        for ip_link in sol_dict["ip_links"]:
            for olink in ip_link["opt_links"]:
                o1 = olink[0]
                o2 = olink[1]
                waves = olink[2]
                num_waves_per_fiber[(o1, o2)] += waves

        return {"max_fiber_utilization": np.max(list(num_waves_per_fiber.values()))}

    @classmethod
    def calculate_mean_fiber_utilization(cls, sol_dict):
        num_waves_per_fiber = collections.defaultdict(int)
        for ip_link in sol_dict["ip_links"]:
            for olink in ip_link["opt_links"]:
                o1 = olink[0]
                o2 = olink[1]
                waves = olink[2]
                num_waves_per_fiber[(o1, o2)] += waves

        return {"mean_fiber_utilization": np.mean(list(num_waves_per_fiber.values()))}

    @classmethod
    def calculate_distribution_fiber_utilization(cls, sol_dict):
        num_waves_per_fiber = collections.defaultdict(int)
        for ip_link in sol_dict["ip_links"]:
            for olink in ip_link["opt_links"]:
                o1 = olink[0]
                o2 = olink[1]
                waves = olink[2]
                num_waves_per_fiber[(o1, o2)] += waves

        return {"distribution_fiber_utilization": list(num_waves_per_fiber.values())}

    @classmethod
    def calculate_nodal_degrees(cls, sol_dict):
        degree = collections.defaultdict(int)
        for ip_link in sol_dict["ip_links"]:
            degree[ip_link['node1']] += 1
            degree[ip_link['node2']] += 1

        return {
            "max_ip_node_degree": int(np.max(list(degree.values()))),
            "min_ip_node_degree": int(np.min(list(degree.values()))),
            "mean_ip_node_degree": np.mean(list(degree.values()))
        }

    @classmethod
    def calculate_ip_utilization(cls, sol_dict):
        if not ("ip_links" in sol_dict and "e2e_routing" in sol_dict):
            return {}
        tp_per_link = collections.defaultdict(float)
        for demand in sol_dict["e2e_routing"]:
            for used_links in demand["paths"]:
                tp_per_link[tuple(used_links[0])] += used_links[1]

        for ip_link in sol_dict["ip_links"]:
            tp_per_link[(ip_link['node1'], ip_link['node2'])] /= 100.0 * ip_link["num_trunks"]

        return {
            "max_ip_utilization": np.max(list(tp_per_link.values())),
            "min_ip_utilization": np.min(list(tp_per_link.values())),
            "mean_ip_utilization": np.mean(list(tp_per_link.values()))
        }

    @classmethod
    def calculate_path_length_ip_hops(cls, sol_dict):
        path_lengths_cdn = list()
        for cdn in sol_dict['cdn_assignment']:
            for unode in cdn['user_nodes']:
                path_lengths_cdn.append(len(unode["routes"]))

        path_lengths_e2e = list()
        for demand in sol_dict["e2e_routing"]:
            path_lengths_e2e.append(len(demand["paths"]))

        path_lengths = path_lengths_e2e + path_lengths_cdn
        if len(path_lengths_e2e) == 0:
            path_lengths_e2e.append(-1)
        if len(path_lengths_cdn) == 0:
            path_lengths_cdn.append(-1)
        
        return {
            "max_path_length_ip_hops": int(np.max(list(path_lengths))),
            "min_path_length_ip_hops": int(np.min(list(path_lengths))),
            "mean_path_length_ip_hops": np.mean(list(path_lengths)),
            "median_path_length_ip_hops": np.median(list(path_lengths)),
            "std_path_length_ip_hops": np.std(list(path_lengths)),

            "max_path_length_cdn_ip_hops": int(np.max(list(path_lengths_cdn))),
            "min_path_length_cdn_ip_hops": int(np.min(list(path_lengths_cdn))),
            "mean_path_length_cdn_ip_hops": np.mean(list(path_lengths_cdn)),
            "median_path_length_cdn_ip_hops": np.median(list(path_lengths_cdn)),
            "std_path_length_cdn_ip_hops": np.std(list(path_lengths_cdn)),

            "max_path_length_e2e_ip_hops": int(np.max(list(path_lengths_e2e))),
            "min_path_length_e2e_ip_hops": int(np.min(list(path_lengths_e2e))),
            "mean_path_length_e2e_ip_hops": np.mean(list(path_lengths_e2e)),
            "median_path_length_e2e_ip_hops": np.median(list(path_lengths_e2e)),
            "std_path_length_e2e_ip_hops": np.std(list(path_lengths_e2e))
        }

    @classmethod
    def calculate_distribution_path_length_ip_hops(cls, sol_dict):
        path_lengths = list()
        for cdn in sol_dict['cdn_assignment']:
            for unode in cdn['user_nodes']:
                path_lengths.append(len(unode["routes"]))

        for demand in sol_dict["e2e_routing"]:
            path_lengths.append(len(demand["paths"]))

        return {'distribution_path_length_ip_hops': list(path_lengths)}

    @classmethod
    def calculate_path_length_opt_hops(cls, sol_dict):
        ip_links = dict()
        for ip_link in sol_dict["ip_links"]:
            ip_links[(ip_link["node1"], ip_link["node2"])] = len(ip_link["opt_links"])

        path_lengths = list()
        for cdn in sol_dict['cdn_assignment']:
            for unode in cdn['user_nodes']:
                this_length = 0
                for n1, n2, _ in unode["routes"]:
                    this_length += ip_links[(n1, n2)]
                if this_length > 0:
                    path_lengths.append(this_length)

        for demand in sol_dict["e2e_routing"]:
            this_length = 0
            for (n1, n2), _ in demand["paths"]:
                this_length += ip_links[(n1, n2)]
            if this_length > 0:
                path_lengths.append(this_length)

        return {
            "max_path_length_opt_hops": int(np.max(list(path_lengths))),
            "min_path_length_opt_hops": int(np.min(list(path_lengths))),
            "mean_path_length_opt_hops": np.mean(list(path_lengths)),
            "median_path_length_opt_hops": np.median(list(path_lengths)),
            "std_path_length_opt_hops": np.std(list(path_lengths))
        }

    @classmethod
    def calculate_path_length_km(cls, sol_dict, inputinstance=None):
        graph = inputinstance.topology.graph
        path_lengths = list()
        for cdn in sol_dict['cdn_assignment']:
            for unode in cdn['user_nodes']:
                this_length = 0
                for n1, n2, _ in unode["routes"]:
                    this_length += graph.edges[(n1, n2)]["weight"]
                if this_length > 0:
                    path_lengths.append(this_length)

        for demand in sol_dict["e2e_routing"]:
            path_lengths.append(len(demand["paths"]))

        return {
            "max_path_length_km": np.max(list(path_lengths)),
            "min_path_length_km": np.min(list(path_lengths)),
            "mean_path_length_km": np.mean(list(path_lengths)),
            "median_path_length_km": np.median(list(path_lengths)),
            "std_path_length_ip_km": np.std(list(path_lengths))
        }


AVAILABLE_METRICS = {
    "total_num_lightpath_hops": MetricsCalculator.calculate_total_lightpath_hops,
    "num_ip_links": MetricsCalculator.calculate_num_ip_links,
    "deployed_ip_trunks": MetricsCalculator.calculate_num_deployed_ip_trunks,
    "max_fiber_utilization": MetricsCalculator.calculate_max_fiber_utilization,
    "mean_fiber_utilization": MetricsCalculator.calculate_mean_fiber_utilization,
    "distribution_fiber_utilization": MetricsCalculator.calculate_distribution_fiber_utilization,
    "max_ip_node_degree": MetricsCalculator.calculate_nodal_degrees,
    "max_ip_utilization": MetricsCalculator.calculate_ip_utilization,
    "mean_path_length_ip_hops": MetricsCalculator.calculate_path_length_ip_hops,
    "mean_path_length_opt_hops": MetricsCalculator.calculate_path_length_opt_hops,
    "total_weighted_lightpath_hops": MetricsCalculator.calculate_weighted_total_lightpath_hops,
    "distribution_path_length_ip_hops": MetricsCalculator.calculate_distribution_path_length_ip_hops,
    "distribution_trunk_capacities": MetricsCalculator.calculate_distribution_capacities
}
