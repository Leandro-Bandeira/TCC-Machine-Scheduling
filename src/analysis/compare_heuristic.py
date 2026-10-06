"""
Roda/lê o output_heuristic.json para cada instância listada em run_config.json
e compara o resultado com o output.json (solução do MIP), reportando
diferença de função objetivo, não alocados e tempo de execução.

Gera data/heuristic_vs_mip.csv.
"""

import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRUSTED_DIR = BASE_DIR / "data" / "trusted"
RUN_CONFIG_JSON = BASE_DIR / "run_config.json"
HEURISTICS_DIR = BASE_DIR / "src" / "heuristics"
HEURISTIC_BIN = HEURISTICS_DIR / "heuristic"
OUT_CSV = BASE_DIR / "data" / "heuristic_vs_mip.csv"

FIELDNAMES = [
    "dt",
    "status",
    "machine_id",
    "machine_name",
    "count_jobs",
    "count_machines",
    "mip_fo",
    "heuristic_fo",
    "fo_diff",
    "fo_diff_pct",
    "mip_gap",
    "mip_unallocated",
    "heuristic_unallocated",
    "mip_time_seconds",
    "heuristic_time_seconds",
    "time_diff_seconds",
]


def iso_to_ddmmyyyy(dt: str) -> str:
    """'2025-12-10' -> '10122025'"""
    return datetime.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")


def build_heuristic() -> None:
    print("[build] make -C src/heuristics")
    subprocess.run(["make"], cwd=HEURISTICS_DIR, check=True)


def run_heuristic(input_file: Path, machine_id: int) -> None:
    """Executa o binário da heurística C++, gerando output_heuristic.json."""
    subprocess.run(
        [str(HEURISTIC_BIN), str(input_file), str(machine_id)],
        capture_output=True,
        text=True,
        check=True,
    )


def read_heuristic_json(
    heuristic_file: Path, machine_id: int
) -> tuple[float | None, float | None, int | None]:
    """Lê os dados da máquina específica em output_heuristic.json."""
    if not heuristic_file.exists():
        return None, None, None
    try:
        with open(heuristic_file, encoding="utf-8") as f:
            data = json.load(f)
        for m in data.get("machines_scheduling", []):
            if m.get("machine_id") == machine_id:
                return (
                    m.get("objective_function"),
                    m.get("solve_time_seconds"),
                    m.get("count_jobs_not_allocated", 0),
                )
    except Exception as e:
        print(f"  [erro ao ler {heuristic_file}]: {e}")
    return None, None, None


def collect_comparisons(run_config: dict, skip_existing: bool = False) -> list[dict]:
    rows = []

    for dt, cfg in run_config.items():
        date_slug = iso_to_ddmmyyyy(dt)
        machines_wanted = set(cfg.get("machines", []))

        for status in cfg.get("only_status", []):
            instance_dir = TRUSTED_DIR / date_slug / status
            input_file = instance_dir / "input.json"
            output_file = instance_dir / "output.json"
            output_heuristic_file = instance_dir / "output_heuristic.json"

            if not input_file.exists() or not output_file.exists():
                print(f"[skip] {dt} / status={status}: input.json ou output.json ausente")
                continue

            with open(input_file, encoding="utf-8") as f:
                input_data = json.load(f)
            with open(output_file, encoding="utf-8") as f:
                output_data = json.load(f)

            machine_name_by_id = {
                m["machine_id"]: m["machine_name"] for m in input_data.get("machines", [])
            }
            job_capacity_by_id = {
                m["machine_id"]: m["job_capacity"] for m in input_data.get("machines", [])
            }

            # jobs_per_machine só conta jobs ainda não processados (Status_Processed vazio)
            jobs_per_machine: dict[int, int] = {}
            for job in input_data.get("jobs", []):
                if job.get("Status_Processed", "") != "":
                    continue
                m_id = job["assigned_machine_id"]
                jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1

            for mach in output_data.get("machines_scheduling", []):
                machine_id = mach["machine_id"]
                machine_name = machine_name_by_id.get(machine_id)

                if machine_name not in machines_wanted:
                    continue

                count_jobs = jobs_per_machine.get(machine_id, 0)
                count_machines = job_capacity_by_id.get(machine_id)

                mip_fo = mach.get("objective_function")
                mip_gap = mach.get("mip_gap")
                mip_time = mach.get("solve_time_seconds")
                mip_unallocated = mach.get("count_jobs_not_allocated", 0)

                # Se skip_existing for False ou output_heuristic.json não existir, roda a heurística
                heuristic_fo, heuristic_time, heuristic_unallocated = (None, None, None)
                if skip_existing:
                    heuristic_fo, heuristic_time, heuristic_unallocated = read_heuristic_json(
                        output_heuristic_file, machine_id
                    )

                if heuristic_fo is None:
                    print(
                        f"[run] Executando heurística: {dt} / status={status} / {machine_name} (id={machine_id})"
                    )
                    try:
                        run_heuristic(input_file, machine_id)
                        (
                            heuristic_fo,
                            heuristic_time,
                            heuristic_unallocated,
                        ) = read_heuristic_json(output_heuristic_file, machine_id)
                    except (RuntimeError, subprocess.CalledProcessError) as e:
                        print(f"  [ERRO] {e}")
                        continue

                if heuristic_fo is None:
                    print(
                        f"  [AVISO] {machine_name} (id={machine_id}) não encontrada em {output_heuristic_file}"
                    )
                    continue

                fo_diff = heuristic_fo - (mip_fo if mip_fo is not None else 0.0)
                fo_diff_pct = (
                    (fo_diff / mip_fo * 100) if (mip_fo and mip_fo != 0) else float("nan")
                )
                time_diff = (heuristic_time or 0.0) - (mip_time or 0.0)

                rows.append(
                    {
                        "dt": dt,
                        "status": status,
                        "machine_id": machine_id,
                        "machine_name": machine_name,
                        "count_jobs": count_jobs,
                        "count_machines": count_machines,
                        "mip_fo": mip_fo,
                        "heuristic_fo": heuristic_fo,
                        "fo_diff": fo_diff,
                        "fo_diff_pct": fo_diff_pct,
                        "mip_gap": mip_gap,
                        "mip_unallocated": mip_unallocated,
                        "heuristic_unallocated": heuristic_unallocated,
                        "mip_time_seconds": mip_time,
                        "heuristic_time_seconds": heuristic_time,
                        "time_diff_seconds": time_diff,
                    }
                )
                print(
                    f"[{dt}/{status}] {machine_name} (id={machine_id})"
                    f" | jobs={count_jobs} mach={count_machines}"
                    f" | fo: mip={mip_fo} (gap={mip_gap}) heur={heuristic_fo:.4f} diff={fo_diff:+.4f}"
                    f" | unallocated: mip={mip_unallocated} heur={heuristic_unallocated}"
                    f" | tempo: mip={mip_time}s heur={heuristic_time:.3f}s"
                )

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path} ({len(rows)} linhas)")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Compara a solução MIP (output.json) com a Heurística (output_heuristic.json)."
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=False,
        help="Reaproveita o output_heuristic.json existente sem re-executar a heurística.",
    )
    args = parser.parse_args()

    if not RUN_CONFIG_JSON.exists():
        print(f"run_config.json não encontrado em {RUN_CONFIG_JSON}")
        sys.exit(1)

    build_heuristic()

    with open(RUN_CONFIG_JSON, encoding="utf-8") as f:
        run_config = json.load(f)

    rows = collect_comparisons(run_config, skip_existing=args.skip_existing)
    if not rows:
        print("Nenhuma comparação gerada.")
        return

    write_csv(rows, OUT_CSV)


if __name__ == "__main__":
    main()

