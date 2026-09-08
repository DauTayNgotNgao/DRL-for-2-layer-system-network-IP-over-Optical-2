import logging
import gurobipy as grb
from ortools.linear_solver import pywraplp

from algorithm.abstract import AbstractAlgorithm
import model.solution
import model.metrics


def build_var_key(args):
    return str(args).replace(" ", "")


def add_variables_from_iterator(model_impl, is_integer, iterator, lb, ub, name):
    """
    Adds a variable for every element returned by iterator. name is extended by __repr__(element). Similar to gurobi.addVars()
    :param is_integer:
    :param iterator:
    :param lb:
    :param ub:
    :param name:
    :return: (tupledict) containing references to the new variables
    """
    new_vars = grb.tupledict()

    for varkey in iterator:
        new_vars[varkey] = model_impl.Var(
            lb=lb,
            ub=ub,
            integer=is_integer,
            name="{}_{}".format(name, build_var_key(varkey))
        )
    return new_vars


class AbstractMixedIntegerProgram(AbstractAlgorithm):
    MODEL_IMPLEMENTOR_CBC = pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING
#    MODEL_IMPLEMENTOR_SCIP = pywraplp.Solver.SCIP_MIXED_INTEGER_PROGRAMMING
#    MODEL_IMPLEMENTOR_GLPK = pywraplp.Solver.GLPK_MIXED_INTEGER_PROGRAMMING
    MODEL_IMPLEMENTOR_CPLEX = pywraplp.Solver.CPLEX_MIXED_INTEGER_PROGRAMMING

    def __init__(self, inputinstance, model_impl, num_threads=1, time_limit=None):
        self.inputinstance = inputinstance
        self.logger = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.model_impl = pywraplp.Solver("linearized_model", model_impl)
        self.model_impl_type = model_impl
        self.num_threads = num_threads
        self.time_limit = time_limit

    def build(self):
        self.build_variables()
        self.build_constraints()
        self.build_objective()

    def build_variables(self):
        raise NotImplementedError

    def build_constraints(self):
        raise NotImplementedError

    def build_objective(self):
        raise NotImplementedError

    def solve(self):
        if self.logger.getEffectiveLevel() == logging.DEBUG:
            self.model_impl.EnableOutput()
        if self.num_threads is not None:
            if self.model_impl_type == AbstractMixedIntegerProgram.MODEL_IMPLEMENTOR_CPLEX:
                self.model_impl.SetSolverSpecificParametersAsString(
                    f"CPLEX Parameter File Version 12.9.0.0 \n CPX_PARAM_THREADS {self.num_threads}"
                )
            else:
                self.model_impl.SetNumThreads(self.num_threads)
        if self.time_limit is not None:
            self.model_impl.SetTimeLimit(self.time_limit * 1000)

        self.result_status = self.model_impl.Solve()
        self.logger.info("Solver finished. Solution status is {}".format(self.result_status))

    def write(self, fname="debug.lp"):
        with open(fname, "w") as fd:
            if ".lp" in fname:
                fd.write(self.model_impl.ExportModelAsLpFormat(False))
            elif ".mps" in fname:
                fd.write(self.model_impl.ExportModelAsMpsFormat(False, False))
        self.logger.info("Wrote model to {}".format(fname))

    def run(self):
        self.build()
        self.solve()

    def _extract_ip_links(self):
        raise NotImplementedError

    def _extract_cdn_assignment(self):
        raise NotImplementedError

    def _extract_e2e_routing(self):
        raise NotImplementedError

    def get_solution(self):
        if self.result_status in [pywraplp.Solver.INFEASIBLE, pywraplp.Solver.ABNORMAL]:
            print("Problem instance is infeasible")
            self.write("debug_inf_model.lp")
            sol = model.solution.SolutionInstance(list(), list(), list())
            sol.add_metric_value(
                "solver_time", self.model_impl.WallTime()
            )
            return sol
        assert self.model_impl.VerifySolution(1e-6, True)

        ip_links = self._extract_ip_links()
        cdn_assignment = self._extract_cdn_assignment()
        e2e_routing = self._extract_e2e_routing()
        sol = model.solution.SolutionInstance(ip_links, cdn_assignment, e2e_routing)

        sol.add_metric_value(
            "objective", self.model_impl.Objective().Value()
        )
        sol.add_metric_value(
            "solver_time", self.model_impl.WallTime()
        )
        sol.add_metric_value(
            "best_bound", self.model_impl.Objective().BestBound()
        )
        model.metrics.MetricsCalculator.calculate_all(sol)

        return sol
