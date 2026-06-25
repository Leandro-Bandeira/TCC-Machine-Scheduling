"""
Lê todos os output.json em data/trusted/ e gera data/results.csv com
uma linha por máquina otimizada, cruzando com input.json para obter
o nome da máquina e a quantidade de sub-máquinas.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRUSTED_DIR = BASE_DIR / "data" / "trusted"
RESULTS_CSV = BASE_DIR / "data" / "results.csv"

FIELDNAMES = [
    "dt",
    "status",
    "machine_name",
    "count_jobs",
    "objective_function",
    "count_jobs_not_allocated",
    "solve_time_seconds",
    "termination_condition",
    "count_machines",
]


def ddmmyyyy_to_iso(date_slug: str) -> str:
    """'13102025' → '2025-10-13'"""
    return datetime.strptime(date_slug, "%d%m%Y").strftime("%Y-%m-%d")


def collect_results(trusted_dir: Path) -> list[dict]:
    rows = []

    for output_file in sorted(trusted_dir.rglob("output.json")):
        # Estrutura esperada: trusted/<DDMMYYYY>/<status>/output.json
        try:
            date_slug = output_file.parent.parent.name
            status = output_file.parent.name
            dt = ddmmyyyy_to_iso(date_slug)
        except ValueError:
            continue

        input_file = output_file.parent / "input.json"
        if not input_file.exists():
            print(f"[AVISO] input.json não encontrado para {output_file}")
            continue

        with open(input_file, encoding="utf-8") as f:
            input_data = json.load(f)
        with open(output_file, encoding="utf-8") as f:
            output_data = json.load(f)

        # machine_id → {machine_name, job_capacity}
        machine_info = {m["machine_id"]: m for m in input_data.get("machines", [])}

        jobs_per_machine: dict[int, int] = {}
        for job in input_data.get("jobs", []):
            if job["Status_Processed"] != "":
                continue
            m_id = job["assigned_machine_id"]
            jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1

        for mach in output_data.get("machines_scheduling", []):
            m_id = mach["machine_id"]
            info = machine_info.get(m_id, {})

            rows.append(
                {
                    "dt": dt,
                    "status": status,
                    "machine_name": info.get("machine_name", f"machine_{m_id}"),
                    "count_jobs": jobs_per_machine.get(m_id, 0),
                    "objective_function": mach.get("objective_function"),
                    "count_jobs_not_allocated": mach.get("count_jobs_not_allocated"),
                    "solve_time_seconds": mach.get("solve_time_seconds"),
                    "termination_condition": mach.get("termination_condition"),
                    "count_machines": info.get("job_capacity"),
                }
            )

    return rows


def write_results_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV gerado: {path} ({len(rows)} linhas)")


def main() -> None:
    rows = collect_results(TRUSTED_DIR)
    if not rows:
        print("Nenhum output.json encontrado.")
        return

    rows.sort(key=lambda r: r["count_jobs"], reverse=True)
    write_results_csv(rows, RESULTS_CSV)

    print("\nResumo:")
    for row in rows:
        print(
            f"  {row['dt']} / status={row['status']} / {row['machine_name']}"
            f" → objective_function={row['objective_function']}"
            f", not_alloc={row['count_jobs_not_allocated']}"
            f", solve={row['solve_time_seconds']}s"
        )


if __name__ == "__main__":
    main()
