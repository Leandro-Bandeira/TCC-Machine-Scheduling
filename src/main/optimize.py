import argparse
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

import pyomo.environ as pyo
from entities import Job, Machine
from pyomo.contrib.solver.solvers.highs import Highs as HiGHS

BASE_DIR = Path(__file__).parent.parent.parent

RAW_DIR = BASE_DIR / "data" / "raw"
TRUSTED_DIR = BASE_DIR / "data" / "trusted"

INPUT_NAME = "input.json"


class TimeIndex:
    def __init__(
        self,
        machine: Machine,
        jobs: list[Job],
        setup_data: dict,
        resources_data: dict,
        big_setup: int,
    ):
        self.machine_data = machine
        self.jobs_data = jobs
        self.setup_data = setup_data
        self.resources_data = resources_data
        self.big_setup = big_setup

        # Simula pior caso nos start_slots reais: n jobs em sequência com max_setup e max_processing
        # snappando sempre para o próximo start_slot disponível
        #
        # Desativado: a simulação assume as n jobs rodando sequencialmente numa lane só
        # (ignora count_machines/job_capacity), então um único job outlier de processing_slots
        # alto já estoura o horizonte na 1ª iteração e trava h_effective bem cedo, cortando
        # time_slots_job de jobs que na verdade caberiam (usando as lanes em paralelo).
        # Usa o horizonte real (H = start_slots[-1]) até essa simulação ser corrigida.
        start_slots = self.machine_data.start_slots
        h_effective = start_slots[-1] if start_slots else 0
        self.time_slots_job = {
            job.id: [
                t
                for t in self.machine_data.start_slots
                if job.release_date_slot <= t <= h_effective
            ]
            for job in self.jobs_data
        }
        
        # print(
        #     f"  H_efetivo={h_effective} (original H={self.machine_data.start_slots[-1] if self.machine_data.start_slots else 0}, slots reduzidos)"
        # )
        self.count_machines = self.machine_data.job_capacity
        print(
            f"Resolvendo para a máquina: {self.machine_data.machine_name}, Jobs: {len(self.jobs_data)}, Machines: {self.count_machines}"
        )

        self.model = pyo.ConcreteModel("Time Index Model")
        self.objective_value = None
        self.warm_start_value = None
        self.mip_gap = None
        self.solve_time = 0.0
        self.termination_condition = "unknown"

    def _single_start_rule(self, model, job: Job):
        return (
            sum(
                model.x[job.id, t, m]
                for t in self.time_slots_job[job.id]
                for m in range(self.count_machines)
            )
            + model.y[job.id]
            == 1
        )

    def _completion_time_rule(self, model, job: Job):
        return (
            sum(
                (t + job.processing_slots) * model.x[job.id, t, m]
                for t in self.time_slots_job[job.id]
                for m in range(self.count_machines)
            )
            <= model.C[job.id]
        )

    def _max_completion_time_rule(self, model, job: Job):
        return model.C_max >= model.C[job.id]

    def _machine_capacity_rule(self, model, t: int, m: int):
        active_vars = []
        for job in self.jobs_data:
            slots_j = self.time_slots_job[job.id]
            lo = bisect_left(slots_j, t - job.processing_slots + 1)
            hi = bisect_right(slots_j, t)
            for s in slots_j[lo:hi]:
                active_vars.append(model.x[job.id, s, m])

        if not active_vars:
            return pyo.Constraint.Skip

        return sum(active_vars) <= 1

    def _setup_machine_rule(self, model, job_i: Job, job_j: Job, t: int, m: int):
        # Tempos de setup: i→j e j→i (0 se não houver)
        s_ij = self.setup_data.get(str(job_i.id), {}).get(str(job_j.id), 0)
        s_ji = self.setup_data.get(str(job_j.id), {}).get(str(job_i.id), 0)

        # Janela proibida para j dado que i começa em t
        window_start = t - job_j.processing_slots - s_ji + 1
        window_end = t + job_i.processing_slots + s_ij - 1

        # Slots de j que caem na janela E existem como variável no modelo
        slots_j = self.time_slots_job[job_j.id]
        lo = bisect_left(slots_j, window_start)
        hi = bisect_right(slots_j, window_end)
        forbidden = slots_j[lo:hi]
        # Se nenhum slot de j cai na janela, a restrição é trivialmente satisfeita
        if not forbidden:
            return pyo.Constraint.Skip

        # sum x_jsm <= 1 - x_itm
        return (
            sum(model.x[job_j.id, s, m] for s in forbidden)
            <= 1 - model.x[job_i.id, t, m]
        )

    def _resource_constraint_rule(
        self, model, resource_id: int, job_i: Job, job_j: Job, t: int, m: int
    ):

        S = self.big_setup

        window_start = t - job_j.processing_slots - S + 1
        window_end = t + job_i.processing_slots + S - 1

        # busca binária nos slots válidos de j
        slots_j = self.time_slots_job[job_j.id]
        lo = bisect_left(slots_j, window_start)
        hi = bisect_right(slots_j, window_end)
        forbidden_slots = slots_j[lo:hi]

        if not forbidden_slots:
            return pyo.Constraint.Skip

        # somatório: job j em qualquer m' ≠ m, dentro da janela
        cross_sum = sum(
            model.x[job_j.id, s, mp]
            for mp in range(self.count_machines)
            if mp != m
            for s in forbidden_slots
        )

        return model.x[job_i.id, t, m] + cross_sum <= 1

    def minimize_max_completion_time(
        self, model, time_slots: list[int], jobs_data: list[Job]
    ):
        self.objective_type = "c_max"
        # Máximo completion time
        model.C_max = pyo.Var(domain=pyo.NonNegativeReals)
        model.max_complation_time = pyo.Constraint(
            jobs_data, rule=self._max_completion_time_rule
        )

        W = time_slots[-1] + 1
        # print(f"Valor de big W: {W}")
        model.penalty = sum(W * model.y[job.id] for job in jobs_data)
        model.objective = pyo.Objective(
            expr=model.C_max + model.penalty, sense=pyo.minimize
        )

    def minmize_sum_completion_time(
        self, model, time_slots: list[int], jobs_data: list[Job]
    ):
        self.objective_type = "sum_completion_time"
        model.objective_expr = sum(model.C[job.id] for job in jobs_data)

        # O valor máximo do somatorio do completion time, é quando todos os jobs terminam no último slot
        # Logo, quando um único job termine no último slot, isso é pior do que alocar todos os jobs no último slot
        W = len(jobs_data) * time_slots[-1] + 1
        model.penalty = sum(W * model.y[job.id] for job in jobs_data)
        model.objective = pyo.Objective(
            expr=model.objective_expr + model.penalty, sense=pyo.minimize
        )

    def _tardiness_rule(self, model, job: Job):
        return model.Tardiness[job.id] >= model.C[job.id] - job.due_date_slot

    def minimize_sum_tardiness(
        self, model, time_slots: list[int], jobs_data: list[Job]
    ):
        self.objective_type = "sum_tardiness"
        model.Tardiness = pyo.Var(
            model.jobs_id, domain=pyo.NonNegativeReals, name="completion"
        )
        model.tardiness_constraint = pyo.Constraint(
            jobs_data, rule=self._tardiness_rule
        )
        model.sum_tardiness = sum(model.Tardiness[job.id] for job in jobs_data)
        # O W é o valor da pior situação possivel, nesse caso, todos os jobs atrasassem até o ultimo slot
        W = len(jobs_data) * time_slots[-1] + 1
        model.penalty = sum(W * model.y[job.id] for job in jobs_data)
        epsilon = 1 / W
        model.sum_completion_time = sum(model.C[job.id] for job in jobs_data)
        model.objective = pyo.Objective(
            expr=model.sum_tardiness
            + model.penalty
            + epsilon * model.sum_completion_time,
            sense=pyo.minimize,
        )

    def generate_output(self) -> dict:
        model = self.model
        machine_id = self.machine_data.id

        if self.objective_value is None:
            return {
                "machines_scheduling": [
                    {
                        "machine_id": machine_id,
                        "objective_function": None,
                        "warm_start_value": self.warm_start_value,
                        "mip_gap": None,
                        "count_jobs_not_allocated": len(self.jobs_data),
                        "solve_time_seconds": round(self.solve_time, 3),
                        "termination_condition": self.termination_condition,
                        "jobs": [],
                    }
                ]
            }

        count_jobs_not_allocated = sum(
            pyo.value(model.y[job.id]) for job in self.jobs_data
        )

        scheduled_jobs = []
        allocated_ids = set()
        for job in self.jobs_data:
            for t in self.time_slots_job[job.id]:
                for m in range(self.count_machines):
                    if pyo.value(model.x[job.id, t, m]) > 0.5:
                        scheduled_jobs.append(
                            {
                                "job_id": job.id,
                                "start": t,
                                "end": t + job.processing_slots - 1,
                                "sub_machine": m,
                            }
                        )
                        allocated_ids.add(job.id)
                        break
                else:
                    continue
                break

        # Jobs não alocados (model.y == 1) entram com -1, igual ao padrão da heurística
        for job in self.jobs_data:
            if job.id not in allocated_ids:
                scheduled_jobs.append(
                    {
                        "job_id": job.id,
                        "start": -1,
                        "end": -1,
                        "sub_machine": -1,
                    }
                )

        return {
            "machines_scheduling": [
                {
                    "machine_id": machine_id,
                    "objective_function": self.objective_value,
                    "warm_start_value": self.warm_start_value,
                    "mip_gap": self.mip_gap,
                    "count_jobs_not_allocated": count_jobs_not_allocated,
                    "solve_time_seconds": round(self.solve_time, 3),
                    "termination_condition": self.termination_condition,
                    "jobs": scheduled_jobs,
                }
            ]
        }

    def _apply_warm_start(self, heuristic_jobs: list[dict]):
        model = self.model
        jobs_data = self.jobs_data
        # print(
        #     f"  [Warm Start] Inicializando modelo Pyomo com {len(heuristic_jobs)} jobs da heurística..."
        # )

        # Inicializa todos os y como 1 (não alocado) e C como 0 por padrão
        for job in jobs_data:
            model.y[job.id].value = 1.0
            model.C[job.id].value = 0.0

        # Zerar todas as variáveis x
        for idx in model.indexes:
            model.x[idx].value = 0.0

        warm_count = 0
        proc_by_id = {job.id: job.processing_slots for job in jobs_data}

        for hj in heuristic_jobs:
            job_id = hj.get("job_id")
            start = hj.get("start")
            m = hj.get("sub_machine")

            if start is not None and start != -1 and m is not None and m != -1:
                if (job_id, start, m) in model.indexes:
                    model.x[job_id, start, m].value = 1.0
                    model.y[job_id].value = 0.0
                    proc = proc_by_id.get(job_id, 0)
                    model.C[job_id].value = start + proc
                    warm_count += 1

        # print(
        #     f"  [Warm Start] Sucesso: {warm_count} variáveis x_jtm inicializadas com 1.0"
        # )

    def optimize(
        self,
        use_gurobi: bool = False,
        use_warm_start: bool = False,
        heuristic_jobs: list[dict] | None = None,
        warm_start_value: float | None = None,
    ):
        self._use_gurobi = use_gurobi
        model = self.model
        jobs_data = self.jobs_data

        jobs_id = [job.id for job in jobs_data]
        time_slots = self.machine_data.start_slots
        time_slots_job = self.time_slots_job
        count_machines = self.count_machines

        # Indecis válidos para cada job
        indexes = [
            (job_id, t, m)
            for job_id, slots in time_slots_job.items()
            for t in slots
            for m in range(count_machines)
        ]

        # Indexes para a restrição de capacidade por slot na máquina
        capacity_indexes = [
            (t, m)
            for t in time_slots
            for m in range(count_machines)
        ]

        # Indexes para a restrição de setup dentro da máquina
        setup_indexes = [
            (job_i, job_j, t, m)
            for job_i in jobs_data
            for job_j in jobs_data
            if job_i.id != job_j.id
            for t in time_slots_job[job_i.id]
            for m in range(count_machines)
        ]

        resource_groups = defaultdict(list)
        for job in jobs_data:
            resource_groups[job.resource_id].append(job)

        # Indexes para a restrição de recursos
        resource_indexes = [
            (resource_id, job_i, job_j, t, m)
            for resource_id, resource_jobs in resource_groups.items()
            for job_i in resource_jobs
            for job_j in resource_jobs
            if job_i.id != job_j.id
            for t in time_slots_job[job_i.id]
            for m in range(count_machines)
        ]
        model.indexes = pyo.Set(initialize=indexes, dimen=3)
        model.jobs_id = pyo.Set(initialize=jobs_id)

        # Cria variável x_jtm, indica se o job foi alocado ao slot t na maquina m
        model.x = pyo.Var(model.indexes, domain=pyo.Binary, name="x")
        model.y = pyo.Var(model.jobs_id, domain=pyo.Binary, name="y")

        # Completion time de cada job
        model.C = pyo.Var(model.jobs_id, domain=pyo.NonNegativeReals, name="completion")

        t0 = perf_counter()
        model.single_start = pyo.Constraint(jobs_data, rule=self._single_start_rule)
        # print(f"[single_start] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        model.completion_time = pyo.Constraint(
            jobs_data, rule=self._completion_time_rule
        )
        # print(f"[completion_time] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        model.machine_capacity = pyo.Constraint(
            capacity_indexes, rule=self._machine_capacity_rule
        )
        # print(f"[machine_capacity] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        model.setup_machine = pyo.Constraint(
            setup_indexes, rule=self._setup_machine_rule
        )
        # print(f"[setup_machine] {perf_counter() - t0:.3f}s")

        if count_machines > 1:
            t0 = perf_counter()
            model.resource_constraint = pyo.Constraint(
                resource_indexes, rule=self._resource_constraint_rule
            )
            # print(f"[resource_constraint] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        self.minimize_sum_tardiness(model, time_slots, jobs_data)
        # print(f"[sum_tardiness] {perf_counter() - t0:.3f}s")

        if use_warm_start and heuristic_jobs:
            self._apply_warm_start(heuristic_jobs)
            self.warm_start_value = warm_start_value

        model.write("model.lp", io_options={"symbolic_solver_labels": True})

        if self._use_gurobi:
            self._solve_with_gurobi(model, warmstart=use_warm_start)
        else:
            self._solve_with_highs(model, warmstart=use_warm_start)

        print(self.termination_condition)
        print(f"{self.objective_type}: {self.objective_value} (gap={self.mip_gap})")

    def _solve_with_highs(self, model, warmstart: bool = False):
        solver = HiGHS()
        solver.config.load_solutions = False
        solver.config.raise_exception_on_nonoptimal_result = False
        solver.config.time_limit = 3600
        #solver.config.solver_options = {"simplex_scale_strategy": 4}
        _t0 = perf_counter()
        try:
            result = solver.solve(model, tee=True, warmstart=warmstart)
        except Exception:
            result = solver.solve(model, tee=True)
        self.solve_time = perf_counter() - _t0
        self.termination_condition = str(result.termination_condition)

        has_solution = result.incumbent_objective is not None
        if has_solution:
            result.solution_loader.load_vars()
            self.objective_value = self._read_objective(model)
            incumbent = result.incumbent_objective
            bound = result.objective_bound
            if incumbent != 0 and bound is not None:
                self.mip_gap = round(abs(incumbent - bound) / abs(incumbent), 6)
            else:
                self.mip_gap = None
        else:
            self.objective_value = None
            self.mip_gap = None

    def _solve_with_gurobi(self, model, warmstart: bool = False):
        solver = pyo.SolverFactory("gurobi")
        solver.options["TimeLimit"] = 3600
        solver.options["MemLimit"] = 40.0
        _t0 = perf_counter()
        try:
            result = solver.solve(
                model, tee=True, warmstart=warmstart, load_solutions=False
            )
            self.solve_time = perf_counter() - _t0
            solver_msg = str(getattr(result.solver, "message", ""))
            if "Unhandled Gurobi solve status (17)" in solver_msg:
                self.termination_condition = "mem_limit"
            else:
                self.termination_condition = str(result.solver.termination_condition)

            upper = result.problem[0].upper_bound
            lower = result.problem[0].lower_bound
            has_solution = (
                upper is not None
                and abs(upper) < 1e99
                and len(result.solution) > 0
            )

            if has_solution:
                result.solver.status = pyo.SolverStatus.ok
                model.solutions.load_from(result)
                self.objective_value = self._read_objective(model)
                if upper != 0 and lower is not None and abs(lower) < 1e99:
                    self.mip_gap = round(abs(upper - lower) / abs(upper), 6)
                else:
                    self.mip_gap = None
            else:
                self.objective_value = None
                self.mip_gap = None
        except Exception as exc:
            self.solve_time = perf_counter() - _t0
            print(f"[AVISO] Gurobi interrompido com exceção: {exc}")
            self.termination_condition = "mem_limit"
            self.objective_value = None
            self.mip_gap = None

    def _read_objective(self, model):
        if self.objective_type == "c_max":
            return pyo.value(model.C_max)
        elif self.objective_type == "sum_tardiness":
            return pyo.value(model.objective)
        else:
            return pyo.value(model.objective_expr)


class ArcTimeIndex(TimeIndex):
    """
    Formulação arco-indexada no tempo, por lane (rede espaço-tempo, estilo Pessoa et al.).

    Cada lane m é um caminho unitário numa rede com:
      - SRC: cadeia de ociosidade da origem (a lane ainda não iniciou nenhum job);
      - (i, p): nó "último job processado = i, lane livre a partir do instante p";
      - arco (i -> j, t, m): j inicia em t na lane m logo após i (setup s_ij embutido:
        sai do nó (i, t - s_ij) e chega ao nó (j, t + p_j));
      - arcos de ociosidade (i, k) -> (i, k+1) e arcos de saída para o sink.
    As variáveis de início x_{j,t,m} são ligadas ao fluxo de entrada em j. Restrições de
    capacidade e de setup entre jobs consecutivos ficam implícitas na rede; a restrição de
    recurso entre lanes (4.6) é mantida sobre x. Arcos são contínuos em [0, 1] (apenas x e y
    são binárias). FO única, idêntica à da formulação TimeIndex. Sem quebra de simetria.
    """

    SRC = -1

    def _setup_time(self, i_id: int, j_id: int) -> int:
        return self.setup_data.get(str(i_id), {}).get(str(j_id), 0)

    def _build_network(self) -> None:
        S = self.time_slots_job
        self._job_by_id = {j.id: j for j in self.jobs_data}
        active = [j for j in self.jobs_data if S[j.id]]
        self._active = active

        min_arrival = {j.id: S[j.id][0] + j.processing_slots for j in active}
        points = {j.id: {t + j.processing_slots for t in S[j.id]} for j in active}
        arcs: list[tuple[int, int, int, int]] = []
        in_arcs: dict[tuple[int, int], list[int]] = defaultdict(list)
        out_arcs: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)

        for i in active:
            for j in active:
                if i.id == j.id:
                    continue
                s_ij = self._setup_time(i.id, j.id)
                for t in S[j.id]:
                    d = t - s_ij  # instante em que a lane sai do nó de i
                    if d >= min_arrival[i.id]:
                        arcs.append((i.id, j.id, t, d))
                        points[i.id].add(d)
                        in_arcs[(j.id, t)].append(i.id)
                        out_arcs[(i.id, d)].append((j.id, t))

        self._arcs = arcs
        self._in_arcs = in_arcs
        self._out_arcs = out_arcs
        self._pts = {jid: sorted(pts) for jid, pts in points.items()}
        self._pidx = {
            jid: {p: k for k, p in enumerate(pts)} for jid, pts in self._pts.items()
        }
        self._src_pts = sorted({t for j in active for t in S[j.id]})
        self._src_pidx = {p: k for k, p in enumerate(self._src_pts)}
        src_out: dict[int, list[int]] = defaultdict(list)
        for j in active:
            for t in S[j.id]:
                src_out[t].append(j.id)
        self._src_out = src_out

    def _add_flow_constraints(self, model) -> None:
        S = self.time_slots_job
        M = self.count_machines
        SRC = self.SRC
        arc, srcarc, idle, ex = model.arc, model.srcarc, model.idle, model.exit_arc
        model.flow = pyo.ConstraintList()
        model.link = pyo.ConstraintList()

        for m in range(M):
            # Cadeia da origem: 1 unidade de fluxo por lane
            last = len(self._src_pts) - 1
            for k, p in enumerate(self._src_pts):
                inflow = 1 if k == 0 else idle[SRC, k - 1, m]
                out = [srcarc[j, p, m] for j in self._src_out[p]]
                out.append(idle[SRC, k, m] if k < last else ex[SRC, m])
                model.flow.add(inflow == pyo.quicksum(out))

            for jid, pts in self._pts.items():
                job = self._job_by_id[jid]
                last = len(pts) - 1
                arrivals: dict[int, list] = defaultdict(list)
                for t in S[jid]:
                    k = self._pidx[jid][t + job.processing_slots]
                    arrivals[k].append(srcarc[jid, t, m])
                    arrivals[k].extend(
                        arc[i, jid, t, m] for i in self._in_arcs.get((jid, t), [])
                    )
                for k, p in enumerate(pts):
                    inflow = list(arrivals.get(k, []))
                    if k > 0:
                        inflow.append(idle[jid, k - 1, m])
                    out = [
                        arc[jid, j2, t2, m]
                        for (j2, t2) in self._out_arcs.get((jid, p), [])
                    ]
                    out.append(idle[jid, k, m] if k < last else ex[jid, m])
                    model.flow.add(pyo.quicksum(inflow) == pyo.quicksum(out))

            # Ligação x_{j,t,m} = fluxo que entra em j iniciando em t na lane m
            for j in self._active:
                for t in S[j.id]:
                    model.link.add(
                        model.x[j.id, t, m]
                        == srcarc[j.id, t, m]
                        + pyo.quicksum(
                            arc[i, j.id, t, m]
                            for i in self._in_arcs.get((j.id, t), [])
                        )
                    )

    def _set_lane_path(self, m: int, seq: list[tuple[int, int]]) -> bool:
        """Grava no modelo o caminho da lane m para a sequência [(job_id, start)] ordenada."""
        model = self.model
        SRC = self.SRC
        ok = True

        def setv(var, key) -> None:
            nonlocal ok
            if key in var:
                var[key].value = 1.0
            else:
                ok = False

        if not seq:
            for k in range(len(self._src_pts) - 1):
                setv(model.idle, (SRC, k, m))
            setv(model.exit_arc, (SRC, m))
            return ok

        j1, t1 = seq[0]
        k1 = self._src_pidx.get(t1)
        if k1 is None:
            return False
        for k in range(k1):
            setv(model.idle, (SRC, k, m))
        setv(model.srcarc, (j1, t1, m))

        for idx, (jid, t) in enumerate(seq):
            ka = self._pidx[jid].get(t + self._job_by_id[jid].processing_slots)
            if ka is None:
                return False
            if idx + 1 < len(seq):
                j2, t2 = seq[idx + 1]
                kd = self._pidx[jid].get(t2 - self._setup_time(jid, j2))
                if kd is None or kd < ka:
                    return False
                for k in range(ka, kd):
                    setv(model.idle, (jid, k, m))
                setv(model.arc, (jid, j2, t2, m))
            else:
                for k in range(ka, len(self._pts[jid]) - 1):
                    setv(model.idle, (jid, k, m))
                setv(model.exit_arc, (jid, m))
        return ok

    def _apply_warm_start(self, heuristic_jobs: list[dict]):
        super()._apply_warm_start(heuristic_jobs)
        model = self.model

        placed: dict[int, tuple[int, int]] = {}
        for hj in heuristic_jobs:
            jid, start, m = hj.get("job_id"), hj.get("start"), hj.get("sub_machine")
            if start is None or start == -1 or m is None or m == -1:
                continue
            if (jid, start, m) in model.indexes:
                placed[jid] = (start, m)

        lanes: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for jid, (start, m) in placed.items():
            lanes[m].append((start, jid))

        for var in (model.arc, model.srcarc, model.idle, model.exit_arc):
            for v in var.values():
                v.value = 0.0

        for m in range(self.count_machines):
            seq = [(jid, t) for t, jid in sorted(lanes.get(m, []))]
            if not self._set_lane_path(m, seq):
                print(
                    f"  [Warm Start] Aviso: caminho da lane {m} não representável na rede de arcos."
                )

    def optimize(
        self,
        use_gurobi: bool = False,
        use_warm_start: bool = False,
        heuristic_jobs: list[dict] | None = None,
        warm_start_value: float | None = None,
    ):
        self._use_gurobi = use_gurobi
        model = self.model
        jobs_data = self.jobs_data
        M = self.count_machines
        S = self.time_slots_job
        time_slots = self.machine_data.start_slots
        SRC = self.SRC

        t0 = perf_counter()
        self._build_network()
        print(
            f"  [arc] rede: {len(self._arcs)} arcos de job por lane, "
            f"{sum(len(p) for p in self._pts.values())} nós de job (build {perf_counter() - t0:.2f}s)"
        )

        indexes = [(j, t, m) for j, slots in S.items() for t in slots for m in range(M)]
        model.indexes = pyo.Set(initialize=indexes, dimen=3)
        model.jobs_id = pyo.Set(initialize=[job.id for job in jobs_data])
        model.x = pyo.Var(model.indexes, domain=pyo.Binary, name="x")
        model.y = pyo.Var(model.jobs_id, domain=pyo.Binary, name="y")
        model.C = pyo.Var(model.jobs_id, domain=pyo.NonNegativeReals, name="completion")

        # Variáveis de fluxo (contínuas em [0, 1])
        model.arc_index = pyo.Set(
            initialize=[(i, j, t, m) for (i, j, t, _d) in self._arcs for m in range(M)],
            dimen=4,
        )
        model.arc = pyo.Var(model.arc_index, bounds=(0, 1))
        model.src_index = pyo.Set(
            initialize=[(j.id, t, m) for j in self._active for t in S[j.id] for m in range(M)],
            dimen=3,
        )
        model.srcarc = pyo.Var(model.src_index, bounds=(0, 1))
        idle_keys = [
            (jid, k, m)
            for jid, pts in self._pts.items()
            for k in range(len(pts) - 1)
            for m in range(M)
        ] + [(SRC, k, m) for k in range(len(self._src_pts) - 1) for m in range(M)]
        model.idle_index = pyo.Set(initialize=idle_keys, dimen=3)
        model.idle = pyo.Var(model.idle_index, bounds=(0, 1))
        exit_keys = [(jid, m) for jid in self._pts for m in range(M)] + [
            (SRC, m) for m in range(M)
        ]
        model.exit_index = pyo.Set(initialize=exit_keys, dimen=2)
        model.exit_arc = pyo.Var(model.exit_index, bounds=(0, 1))

        model.single_start = pyo.Constraint(jobs_data, rule=self._single_start_rule)
        model.completion_time = pyo.Constraint(
            jobs_data, rule=self._completion_time_rule
        )
        self._add_flow_constraints(model)

        if M > 1:
            resource_groups = defaultdict(list)
            for job in jobs_data:
                resource_groups[job.resource_id].append(job)
            resource_indexes = [
                (resource_id, job_i, job_j, t, m)
                for resource_id, resource_jobs in resource_groups.items()
                for job_i in resource_jobs
                for job_j in resource_jobs
                if job_i.id != job_j.id
                for t in S[job_i.id]
                for m in range(M)
            ]
            model.resource_constraint = pyo.Constraint(
                resource_indexes, rule=self._resource_constraint_rule
            )

        self.minimize_sum_tardiness(model, time_slots, jobs_data)

        if use_warm_start and heuristic_jobs:
            self._apply_warm_start(heuristic_jobs)
            self.warm_start_value = warm_start_value

        if self._use_gurobi:
            self._solve_with_gurobi(model, warmstart=use_warm_start)
        else:
            self._solve_with_highs(model, warmstart=use_warm_start)

        print(self.termination_condition)
        print(f"{self.objective_type}: {self.objective_value} (gap={self.mip_gap})")


def main(
    data_input_path: Path,
    data_output_path: Path,
    only_machines: list[str] | None = None,
    use_gurobi: bool = False,
    use_warm_start: bool = False,
    formulation_arc: bool = False,
):
    with open(data_input_path, "r") as f:
        data = json.load(f)

    heuristic_data_by_machine = {}
    if use_warm_start:
        heuristic_file = data_input_path.parent / "output_heuristic.json"
        if heuristic_file.exists():
            # print(f"[Warm Start] Lendo arquivo da heurística: {heuristic_file}")
            try:
                with open(heuristic_file, "r") as hf:
                    h_json = json.load(hf)
                    for m_entry in h_json.get("machines_scheduling", []):
                        m_id = m_entry.get("machine_id")
                        heuristic_data_by_machine[m_id] = m_entry
            except Exception as exc:
                print(f"[Warm Start] Erro ao ler output_heuristic.json: {exc}")
        else:
            print(
                f"[Warm Start] Aviso: {heuristic_file} não encontrado. Otimizando sem warm start."
            )

    machines = data["machines"]
    jobs = data["jobs"]
    setups_data = data["setups"]
    resources_data = data["machine_resource_jobs"]
    all_machine_schedules = []
    big_setup = data["big_setup"]

    for machine in machines:
        machine_id = machine["machine_id"]
        machine_name = machine["machine_name"]

        if only_machines and machine_name not in only_machines:
            continue

        jobs_machine = [
            job
            for job in jobs
            if job["assigned_machine_id"] == machine_id
            and job["Status_Processed"] == ""
        ]

        jobs_machine = [Job.from_dict(job) for job in jobs_machine]
        machine = Machine.from_dict(machine)
        machine_setups = setups_data.get(str(machine_id), {})
        machine_resources = resources_data.get(str(machine_id), {})
        model_cls = ArcTimeIndex if formulation_arc else TimeIndex
        time_index_model = model_cls(
            machine=machine,
            jobs=jobs_machine,
            setup_data=machine_setups,
            resources_data=machine_resources,
            big_setup=big_setup,
        )
        h_entry = heuristic_data_by_machine.get(machine_id, {})
        h_jobs = h_entry.get("jobs")
        h_fo = h_entry.get("objective_function")
        time_index_model.optimize(
            use_gurobi=use_gurobi,
            use_warm_start=use_warm_start,
            heuristic_jobs=h_jobs,
            warm_start_value=h_fo,
        )

        output = time_index_model.generate_output()
        all_machine_schedules.extend(output["machines_scheduling"])

    with open(data_output_path, "w") as f:
        json.dump(
            {"machines_scheduling": all_machine_schedules},
            f,
            indent=2,
            ensure_ascii=False,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Otimiza o sequenciamento para uma data e lote específicos."
    )
    default_root = Path(__file__).resolve().parent.parent.parent
    parser.add_argument(
        "--dt",
        required=True,
        help="Data no formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--trusted-root",
        type=Path,
        default=default_root / "data" / "trusted",
        help="Diretório raiz das instâncias (default: data/trusted).",
    )
    parser.add_argument(
        "--only-status",
        nargs="+",
        default=None,
        help="Lista de status a processar. Se omitido, processa todos.",
    )
    parser.add_argument(
        "--only-machines",
        nargs="+",
        default=None,
        help="Lista de nomes de máquinas a otimizar. Se omitido, otimiza todas.",
    )
    parser.add_argument(
        "--use-gurobi",
        action="store_true",
        default=False,
        help="Usa Gurobi como solver em vez de HiGHS.",
    )
    parser.add_argument(
        "--use-warm-start",
        action="store_true",
        default=False,
        help="Usa a solução de output_heuristic.json para inicializar o solver (warm start).",
    )
    parser.add_argument(
        "--formulation-arc",
        action="store_true",
        default=False,
        help="Usa a formulação arco-indexada no tempo por lane (ArcTimeIndex) em vez da time-index.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        dt_obj = datetime.strptime(args.dt, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Data inválida para --dt: {args.dt}") from exc

    date_slug = dt_obj.strftime("%d%m%Y")
    trusted_root: Path = args.trusted_root
    date_dir = trusted_root / date_slug

    if not date_dir.is_dir():
        raise SystemExit(f"Diretório não encontrado: {date_dir}")

    available = [
        item.name
        for item in sorted(date_dir.iterdir())
        if item.is_dir() and (item / "input.json").exists()
    ]

    if not available:
        raise SystemExit(f"Nenhum input.json encontrado em {date_dir}")

    status_list = args.only_status if args.only_status else available

    for status in status_list:
        data_input_path = trusted_root / date_slug / status / "input.json"
        data_output_path = trusted_root / date_slug / status / "output.json"
        if not data_input_path.exists():
            print(f"[AVISO] input.json não encontrado: {data_input_path}")
            continue
        print(f"\n=== Otimizando {date_slug}/{status} ===")
        main(
            data_input_path=data_input_path,
            data_output_path=data_output_path,
            only_machines=args.only_machines,
            use_gurobi=args.use_gurobi,
            use_warm_start=args.use_warm_start,
            formulation_arc=args.formulation_arc,
        )
