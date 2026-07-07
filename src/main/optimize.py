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
        start_slots = self.machine_data.start_slots
        if self.jobs_data and start_slots:
            all_setups = [
                v for targets in setup_data.values() for v in targets.values()
            ]
            max_setup = max(all_setups) if all_setups else 0
            max_processing = max(job.processing_slots for job in self.jobs_data)
            max_release = max(job.release_date_slot for job in self.jobs_data)
            n = len(self.jobs_data)

            current = max_release
            h_effective = start_slots[0]
            for _ in range(n):
                idx = bisect_left(start_slots, current)
                if idx >= len(start_slots):
                    break
                h_effective = start_slots[idx]
                current = h_effective + max_processing + max_setup
        else:
            h_effective = start_slots[-1] if start_slots else 0
        self.time_slots_job = {
            job.id: [
                t
                for t in self.machine_data.start_slots
                if job.release_date_slot <= t <= h_effective
            ]
            for job in self.jobs_data
        }
        print(
            f"  H_efetivo={h_effective} (original H={self.machine_data.start_slots[-1] if self.machine_data.start_slots else 0}, slots reduzidos)"
        )
        self.count_machines = self.machine_data.job_capacity
        print(
            f"Resolvendo para a máquina: {self.machine_data.machine_name}, Jobs: {len(self.jobs_data)}, Machines: {self.count_machines}"
        )

        self.model = pyo.ConcreteModel("Time Index Model")
        self.objective_value = None
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
        print(f"Valor de big W: {W}")
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
                        break
                else:
                    continue
                break

        return {
            "machines_scheduling": [
                {
                    "machine_id": machine_id,
                    "objective_function": self.objective_value,
                    "mip_gap": self.mip_gap,
                    "count_jobs_not_allocated": count_jobs_not_allocated,
                    "solve_time_seconds": round(self.solve_time, 3),
                    "termination_condition": self.termination_condition,
                    "jobs": scheduled_jobs,
                }
            ]
        }

    def optimize(self, use_gurobi: bool = False):
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
        print(f"[single_start] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        model.completion_time = pyo.Constraint(
            jobs_data, rule=self._completion_time_rule
        )
        print(f"[completion_time] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        model.setup_machine = pyo.Constraint(
            setup_indexes, rule=self._setup_machine_rule
        )
        print(f"[setup_machine] {perf_counter() - t0:.3f}s")

        if count_machines > 1:
            t0 = perf_counter()
            model.resource_constraint = pyo.Constraint(
                resource_indexes, rule=self._resource_constraint_rule
            )
            print(f"[resource_constraint] {perf_counter() - t0:.3f}s")

        t0 = perf_counter()
        self.minimize_sum_tardiness(model, time_slots, jobs_data)
        print(f"[sum_tardiness] {perf_counter() - t0:.3f}s")

        model.write("model.lp", io_options={"symbolic_solver_labels": True})

        if self._use_gurobi:
            self._solve_with_gurobi(model)
        else:
            self._solve_with_highs(model)

        print(self.termination_condition)
        print(f"{self.objective_type}: {self.objective_value} (gap={self.mip_gap})")

    def _solve_with_highs(self, model):
        solver = HiGHS()
        solver.config.load_solutions = False
        solver.config.raise_exception_on_nonoptimal_result = False
        # solver.config.time_limit = 14400
        solver.config.solver_options = {"simplex_scale_strategy": 4}
        _t0 = perf_counter()
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

    def _solve_with_gurobi(self, model):
        solver = pyo.SolverFactory("gurobi")
        solver.options["TimeLimit"] = 5
        _t0 = perf_counter()
        result = solver.solve(model, tee=True)
        self.solve_time = perf_counter() - _t0
        self.termination_condition = str(result.solver.termination_condition)

        upper = result.problem[0].upper_bound
        lower = result.problem[0].lower_bound
        has_solution = upper is not None and upper < float("inf")

        if has_solution:
            self.objective_value = self._read_objective(model)
            if upper != 0 and lower is not None:
                self.mip_gap = round(abs(upper - lower) / abs(upper), 6)
            else:
                self.mip_gap = None
        else:
            self.objective_value = None
            self.mip_gap = None

    def _read_objective(self, model):
        if self.objective_type == "c_max":
            return pyo.value(model.C_max)
        elif self.objective_type == "sum_tardiness":
            return pyo.value(model.objective)
        else:
            return pyo.value(model.objective_expr)


def main(
    data_input_path: Path,
    data_output_path: Path,
    only_machines: list[str] | None = None,
    use_gurobi: bool = False,
):
    with open(data_input_path, "r") as f:
        data = json.load(f)

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
        time_index_model = TimeIndex(
            machine=machine,
            jobs=jobs_machine,
            setup_data=machine_setups,
            resources_data=machine_resources,
            big_setup=big_setup,
        )
        time_index_model.optimize(use_gurobi=use_gurobi)

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
        )
