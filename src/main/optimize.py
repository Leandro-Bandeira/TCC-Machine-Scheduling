import json
from pathlib import Path

import pyomo.environ as pyo
from entities import Job, Machine

BASE_DIR = Path(__file__).parent.parent.parent

RAW_DIR = BASE_DIR / "data" / "raw"
TRUSTED_DIR = BASE_DIR / "data" / "trusted"

INPUT_NAME = "input.json"


class TimeIndex:
    def __init__(self, machine: Machine, jobs: list[Job]):
        self.machine_data = machine
        self.jobs_data = jobs

        # Informações que serão utilizadas na modelagem
        self.time_slots_job = {
            job.id: [
                t for t in self.machine_data.start_slots if t >= job.release_date_slot
            ]
            for job in self.jobs_data
        }
        self.count_machines = self.machine_data.job_capacity
        self.model = pyo.ConcreteModel("Time Index Model")

    def _single_start_rule(self, model, job: Job):
        return (
            sum(
                model.x[job.id, t, m]
                for t in self.time_slots_job[job.id]
                for m in range(self.count_machines)
            )
            == 1
        )

    def _completion_time_rule(self, model, job: Job):
        return (
            sum(
                t * model.x[job.id, t, m]
                for t in self.time_slots_job[job.id]
                for m in range(self.count_machines)
            )
            + job.processing_slots
            <= model.C[job.id]
        )

    def _max_completion_time_rule(self, model, job: Job):
        return model.C_max >= model.C[job.id]

    def optimize(self):
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
        model.indexes = pyo.Set(initialize=indexes, dimen=3)
        model.jobs_id = pyo.Set(initialize=jobs_id)

        # Cria variável x_jtm, indica se o job foi alocado ao slot t na maquina m
        model.x = pyo.Var(model.indexes, domain=pyo.Binary, name="x")
        # Completion time de cada job
        model.C = pyo.Var(model.jobs_id, domain=pyo.NonNegativeReals, name="completion")
        # Máximo completion time
        model.C_max = pyo.Var(domain=pyo.NonNegativeReals)

        model.single_start = pyo.Constraint(jobs_data, rule=self._single_start_rule)
        model.completion_time = pyo.Constraint(
            jobs_data, rule=self._completion_time_rule
        )
        model.max_complation_time = pyo.Constraint(
            jobs_data, rule=self._max_completion_time_rule
        )

        model.objective = pyo.Objective(expr=model.C_max, sense=pyo.minimize)
        model.write("model.lp", io_options={"symbolic_solver_labels": True})

        solver = pyo.SolverFactory("highs")
        result = solver.solve(model, tee=True)

        print(result.solver.status)
        print(result.solver.termination_condition)
        print(pyo.value(model.C_max))


def main(data_input_path: Path):
    with open(data_input_path, "r") as f:
        data = json.load(f)

    machines = data["machines"]
    jobs = data["jobs"]

    for machine in machines:
        machine_id = machine["machine_id"]
        machine_name = machine["machine_name"]

        if machine_name != "coldboxgasado_coldboxpequena":
            continue
        jobs_machine = [job for job in jobs if job["assigned_machine_id"] == machine_id]

        jobs_machine = [Job.from_dict(job) for job in jobs_machine]
        machine = Machine.from_dict(machine)
        time_index_model = TimeIndex(machine=machine, jobs=jobs_machine)
        time_index_model.optimize()


if __name__ == "__main__":
    data_input_path = TRUSTED_DIR / "13102025" / "34" / "input.json"
    main(data_input_path=data_input_path)
