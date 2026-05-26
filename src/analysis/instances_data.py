"""
Executa data_input_process.py para todos os lotes em data/raw e gera
data/instances.csv com o tamanho de cada instância.
"""
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
TRUSTED_DIR = BASE_DIR / "data" / "trusted"
SCRIPTS_DIR = BASE_DIR / "src" / "main"
INSTANCES_CSV = BASE_DIR / "data" / "instances.csv"

PYTHON = sys.executable


# -----------------------------------------------------------------------------
# Utilitários
# -----------------------------------------------------------------------------

def ddmmyyyy_to_iso(date_slug: str) -> str:
    """'13102025' → '2025-10-13'"""
    return datetime.strptime(date_slug, "%d%m%Y").strftime("%Y-%m-%d")


def discover_batches(raw_dir: Path) -> list[tuple[str, str]]:
    """
    Retorna lista de (date_slug, status_name) para todos os lotes
    com pasta demanda/ em data/raw.
    """
    batches = []
    for date_dir in sorted(raw_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        if not date_dir.name.isdigit() or len(date_dir.name) != 8:
            continue
        for status_dir in sorted(date_dir.iterdir()):
            if status_dir.is_dir() and (status_dir / "demanda").is_dir():
                batches.append((date_dir.name, status_dir.name))
    return batches


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------

def run_data_input(date_iso: str) -> bool:
    """Executa data_input_process.py para uma data."""
    cmd = [
        PYTHON,
        str(SCRIPTS_DIR / "data_input_process.py"),
        "--dt", date_iso,
        "--raw-root", str(RAW_DIR),
        "--trusted-root", str(TRUSTED_DIR),
        "--model-config-dir", str(RAW_DIR / "model_config"),
    ]
    print(f"  [input] --dt {date_iso}")
    result = subprocess.run(cmd)
    return result.returncode == 0


# -----------------------------------------------------------------------------
# Geração do CSV de instâncias
# -----------------------------------------------------------------------------

def collect_instances(trusted_dir: Path) -> list[dict]:
    """
    Lê todos os input.json em trusted/ e retorna uma linha por máquina com:
    date, status, machine_id, machine_name, job_capacity, count_jobs.
    """
    rows = []
    for input_file in sorted(trusted_dir.rglob("input.json")):
        # Estrutura esperada: trusted/<DDMMYYYY>/<status>/input.json
        try:
            date_slug = input_file.parent.parent.name
            status = input_file.parent.name
            date_iso = ddmmyyyy_to_iso(date_slug)
        except ValueError:
            continue

        with open(input_file, encoding="utf-8") as f:
            data = json.load(f)

        # Conta jobs por machine_id
        jobs_per_machine: dict[int, int] = {}
        for job in data.get("jobs", []):
            m_id = job["assigned_machine_id"]
            jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1

        for machine in data.get("machines", []):
            m_id = machine["machine_id"]
            rows.append({
                "date": date_iso,
                "status": status,
                "machine_id": m_id,
                "machine_name": machine["machine_name"],
                "job_capacity": machine["job_capacity"],
                "count_jobs": jobs_per_machine.get(m_id, 0),
            })
    return rows


def write_instances_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date", "status", "machine_id", "machine_name",
                "job_capacity", "count_jobs",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path}")


# -----------------------------------------------------------------------------
# Orquestração principal
# -----------------------------------------------------------------------------

def main() -> None:
    batches = discover_batches(RAW_DIR)
    if not batches:
        print(f"Nenhum lote encontrado em {RAW_DIR}")
        return

    print(f"Lotes encontrados: {len(batches)}\n")

    # data_input_process roda uma vez por data
    dates_done: set[str] = set()
    for date_slug, _ in batches:
        date_iso = ddmmyyyy_to_iso(date_slug)
        if date_iso not in dates_done:
            ok = run_data_input(date_iso)
            if not ok:
                print(f"  [ERRO] data_input_process falhou para {date_iso}")
            dates_done.add(date_iso)

    # Coleta e salva instances.csv
    rows = collect_instances(TRUSTED_DIR)
    if rows:
        rows.sort(key=lambda r: r["count_jobs"])
        write_instances_csv(rows, INSTANCES_CSV)
        print("\nInstâncias:")
        for row in rows:
            print(
                f"  {row['date']} / status={row['status']}"
                f" / {row['machine_name']}"
                f" → {row['count_jobs']} jobs, capacity={row['job_capacity']}"
            )
    else:
        print("\nNenhum input.json encontrado.")


if __name__ == "__main__":
    main()
