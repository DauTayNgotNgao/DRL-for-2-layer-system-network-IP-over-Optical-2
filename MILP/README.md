# MILP teacher

This folder vendors the original Hypergiant ISP MILP under `hypergiant_isp/`.
That vendored source is preserved for reference. The teacher runner does not
import the original OR-Tools wrapper; it builds the same path-based MILP through
the native IBM CPLEX Python API in `cplex_native_milp.py`.
The vendored solver source is copied unchanged; project-specific code lives in:

- `hypergiant_adapter.py`: converts generated `src_hung` topology/demands into the Hypergiant `InputInstance`.
- `cplex_native_milp.py`: mirrors the Hypergiant path-based MILP variables/constraints/objective, but builds them directly with IBM CPLEX Python API.
- `run_milp_teacher.py`: runs the exact CPLEX MILP and writes JSON teacher/baseline cases for LNS-Repair experiments.

Default behavior keeps the original slow exact MILP setup:

- integer model, not relaxed;
- no default time limit;
- native IBM CPLEX selected by default;
- no warm start and no SA/heuristic fallback.
- SA-compatible hard constraints: directed generated IP graph, per-demand
  unsplittable routing, IP capacity, optical mapping by candidate paths,
  explicit per-slot spectrum conflict, and `rho_limit` reconfiguration budget.
- After solving, the runner rebuilds a `MultiLayerState` and checks it with the
  same `CostCalculator` used by SA and LNS-Repair.

Example:

```powershell
python -m MILP.run_milp_teacher --num-demands 10 --solver cplex
```

Generate several teacher cases:

```powershell
python -m MILP.run_milp_teacher --demand-points 5 10 15 20 --repetitions 3 --solver cplex
```

Show CPLEX progress logs:

```powershell
python -m MILP.run_milp_teacher --num-demands 30 --solver cplex --cplex-log
```

Compare SA with the fast LNS-Repair optimizer:

```powershell
python -m src_hung.experiments.demand_sweep --demand-points 5,10,15 --repetitions 3 --k-shortest 10 --lns-iterations 80 --lns-destroy-candidates 10
```

The runner defaults to `--ip-candidate-mode generated` so MILP cases match the generated IP topology used by SA/LNS.
Use `--ip-candidate-mode complete` when you want to compare against the original full virtual-topology MILP over all ordered IP-node pairs.
