"""
Comparador de Desempenho: Solução Base dos Operadores (Case AFM) vs Heurística ILS/VNS.

Este módulo lê as instâncias ativas configuradas em `run_config.json` e compara
apenas a Solução Base dos Operadores (`Case_AFM-main/main.py` -> `output_baseline.json`)
com a Heurística C++ (`src/heuristics/` -> `output_heuristic.json`), sem depender do MIP.

Para cada par `(dt, status)` e máquina configurada em `run_config.json`:
1. Compila o binário da heurística C++ (`make -C src/heuristics`), se necessário.
2. Gera sempre um novo resultado da Solução Base dos Operadores (`output_baseline.json`).
3. Preserva e lê o resultado existente da Heurística C++ (`output_heuristic.json`), executando o binário apenas caso a máquina ainda não exista em `output_heuristic.json`.
4. Compara:
   - Função Objetivo (`baseline_fo` vs `heuristic_fo`, diferença absoluta `fo_diff` e percentual `fo_diff_pct`).
   - Jobs não alocados (`baseline_unallocated` vs `heuristic_unallocated`).
   - Dimensões da instância (`count_jobs`, `count_machines`, `H`).
   - Tempo de execução (`baseline_time_seconds` vs `heuristic_time_seconds`).

Gera o relatório consolidado em `Case_AFM-main/baseline_vs_heuristic.csv`.

Uso:
    python3 Case_AFM-main/compare_heuristic.py
    python3 Case_AFM-main/compare_heuristic.py --skip-existing
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
BASE_DIR = CASE_DIR.parent
RAW_DIR = BASE_DIR / "data" / "raw"
TRUSTED_DIR = BASE_DIR / "data" / "trusted"
RUN_CONFIG_JSON = BASE_DIR / "run_config.json"
HEURISTICS_DIR = BASE_DIR / "src" / "heuristics"
HEURISTIC_BIN = HEURISTICS_DIR / "heuristic"
MODEL_CONFIG_DIR = CASE_DIR / "model_config"
OUT_CSV = CASE_DIR / "baseline_vs_heuristic.csv"

if str(CASE_DIR) not in sys.path:
    sys.path.insert(0, str(CASE_DIR))

import main as baseline_main  # noqa: E402

FIELDNAMES = [
    "dt",
    "status",
    "machine_id",
    "machine_name",
    "count_jobs",
    "count_machines",
    "H",
    "baseline_fo",
    "heuristic_fo",
    "fo_diff",
    "fo_diff_pct",
    "baseline_unallocated",
    "heuristic_unallocated",
    "baseline_time_seconds",
    "heuristic_time_seconds",
    "time_diff_seconds",
]


def iso_to_ddmmyyyy(dt: str) -> str:
    """Converte data ISO 'YYYY-MM-DD' para 'DDMMYYYY'."""
    return datetime.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")


def build_heuristic() -> None:
    """Compila o executável C++ da heurística em `src/heuristics/`."""
    print("[build] make -C src/heuristics")
    subprocess.run(["make"], cwd=HEURISTICS_DIR, check=True)


def run_heuristic(input_file: Path, machine_id: int) -> None:
    """Executa o binário `./heuristic <input.json> <machine_id>`."""
    subprocess.run(
        [str(HEURISTIC_BIN), str(input_file), str(machine_id)],
        capture_output=True,
        text=True,
        check=True,
    )


def read_scheduling_json(
    json_file: Path, machine_id: int
) -> tuple[float | None, float | None, int | None]:
    """
    Lê `(objective_function, solve_time_seconds, count_jobs_not_allocated)` de um arquivo
    no formato `{"machines_scheduling": [...]}` (`output_heuristic.json` ou `output_baseline.json`).
    """
    if not json_file.exists():
        return None, None, None
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        for m in data.get("machines_scheduling", []):
            if m.get("machine_id") == machine_id:
                return (
                    m.get("objective_function"),
                    m.get("solve_time_seconds"),
                    m.get("count_jobs_not_allocated", 0),
                )
    except Exception as e:
        print(f"  [erro ao ler {json_file}]: {e}")
    return None, None, None


def run_and_save_baseline_for_lote(
    raw_lote_dir: Path,
    output_baseline_file: Path,
    aux_tables: tuple,
) -> None:
    """
    Executa a solução base dos operadores (`Case_AFM-main/main.py`) para um lote
    e grava `output_baseline.json` no mesmo formato de `output_heuristic.json`.
    """
    import numpy as np
    import pandas as pd

    machines_df, caps_df, shifts_df, setup_df, setup_times_df = aux_tables

    day_start = baseline_main.parse_day_start_from_lote(raw_lote_dir)
    business_days = baseline_main.compute_business_days(day_start)
    init_date = pd.Timestamp(business_days[0])

    demand_df = baseline_main.load_demand(raw_lote_dir)
    demand_df = baseline_main.validate_and_fix_demand(demand_df, day_start)
    demand_df = baseline_main.filter_demand_by_horizon(demand_df, business_days)
    demand_df = demand_df.reset_index(drop=True)
    demand_df["job_id"] = np.arange(len(demand_df), dtype=int)

    machines = baseline_main.build_target_machines(
        demand_df=demand_df,
        machines_df=machines_df,
        caps_df=caps_df,
        shifts_df=shifts_df,
        business_days=business_days,
        only_machines=None,
    )

    kp_macho_data = baseline_main.build_kp_macho_data(setup_df, machines, demand_df)
    setup_time_data = baseline_main.build_setup_time_data(setup_times_df, machines)

    machines_scheduling_json = []
    for m in machines:
        jobs = baseline_main.build_jobs_for_machine(
            demand_df=demand_df,
            machine=m,
            day_start=day_start,
            kp_macho_data=kp_macho_data,
        )
        _, machine_json_entry = baseline_main.schedule_machine_baseline(
            machine=m,
            jobs=jobs,
            init_date=init_date,
            kp_macho_data=kp_macho_data,
            setup_time_data=setup_time_data,
        )
        machines_scheduling_json.append(machine_json_entry)

    output_baseline_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_baseline_file, "w", encoding="utf-8") as f:
        json.dump(
            {"machines_scheduling": machines_scheduling_json},
            f,
            indent=4,
            ensure_ascii=False,
        )


def collect_comparisons(
    run_config: dict,
    skip_existing: bool = False,
    only_existing_heuristic: bool = False,
) -> list[dict]:
    """
    Itera sobre `run_config.json` e compara a Solução Base (`output_baseline.json`)
    com a Heurística (`output_heuristic.json`).
    """
    rows = []
    aux_tables = baseline_main.load_aux_tables(MODEL_CONFIG_DIR)

    for dt, cfg in run_config.items():
        date_slug = iso_to_ddmmyyyy(dt)
        machines_wanted = set(cfg.get("machines", []))

        for status in cfg.get("only_status", []):
            instance_dir = TRUSTED_DIR / date_slug / status
            raw_lote_dir = RAW_DIR / date_slug / status
            input_file = instance_dir / "input.json"
            output_heuristic_file = instance_dir / "output_heuristic.json"
            output_baseline_file = instance_dir / "output_baseline.json"

            if not input_file.exists() or not raw_lote_dir.exists():
                print(f"[skip] {dt} / status={status}: input.json ou lote raw ausente")
                continue

            if only_existing_heuristic and not output_heuristic_file.exists():
                continue

            # Sempre gera um novo baseline para o lote
            run_and_save_baseline_for_lote(
                raw_lote_dir, output_baseline_file, aux_tables
            )

            with open(input_file, encoding="utf-8") as f:
                input_data = json.load(f)

            jobs_per_machine: dict[int, int] = {}
            for job in input_data.get("jobs", []):
                if job.get("Status_Processed", "") != "":
                    continue
                m_id = job["assigned_machine_id"]
                jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1

            for mach in input_data.get("machines", []):
                machine_id = mach["machine_id"]
                machine_name = mach["machine_name"]

                if machine_name not in machines_wanted:
                    continue

                count_jobs = jobs_per_machine.get(machine_id, 0)
                count_machines = mach["job_capacity"]
                start_slots = mach.get("start_slots", [])
                h_horizon = start_slots[-1] if start_slots else 0

                baseline_fo, baseline_time, baseline_unallocated = read_scheduling_json(
                    output_baseline_file, machine_id
                )

                # Preserva sempre o resultado já existente da heurística
                heuristic_fo, heuristic_time, heuristic_unallocated = (
                    read_scheduling_json(output_heuristic_file, machine_id)
                )

                if heuristic_fo is None and not only_existing_heuristic:
                    print(
                        f"[run] Executando heurística: {dt} / status={status} / {machine_name} (id={machine_id})"
                    )
                    try:
                        run_heuristic(input_file, machine_id)
                        (
                            heuristic_fo,
                            heuristic_time,
                            heuristic_unallocated,
                        ) = read_scheduling_json(output_heuristic_file, machine_id)
                    except (RuntimeError, subprocess.CalledProcessError) as e:
                        print(f"  [ERRO] {e}")
                        continue

                if baseline_fo is None or heuristic_fo is None:
                    continue

                fo_diff = heuristic_fo - baseline_fo
                fo_diff_pct = (
                    (fo_diff / baseline_fo * 100)
                    if (baseline_fo and baseline_fo != 0)
                    else float("nan")
                )
                time_diff = (heuristic_time or 0.0) - (baseline_time or 0.0)

                rows.append(
                    {
                        "dt": dt,
                        "status": status,
                        "machine_id": machine_id,
                        "machine_name": machine_name,
                        "count_jobs": count_jobs,
                        "count_machines": count_machines,
                        "H": h_horizon,
                        "baseline_fo": baseline_fo,
                        "heuristic_fo": heuristic_fo,
                        "fo_diff": fo_diff,
                        "fo_diff_pct": fo_diff_pct,
                        "baseline_unallocated": baseline_unallocated,
                        "heuristic_unallocated": heuristic_unallocated,
                        "baseline_time_seconds": baseline_time,
                        "heuristic_time_seconds": heuristic_time,
                        "time_diff_seconds": time_diff,
                    }
                )
                print(
                    f"[{dt}/{status}] {machine_name} (id={machine_id})"
                    f" | jobs={count_jobs} mach={count_machines} H={h_horizon}"
                    f" | fo: base={baseline_fo:.4f} heur={heuristic_fo:.4f} diff={fo_diff:+.4f} ({fo_diff_pct:+.2f}%)"
                    f" | unallocated: base={baseline_unallocated} heur={heuristic_unallocated}"
                    f" | tempo: base={baseline_time:.4f}s heur={heuristic_time:.4f}s"
                )

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    """Grava os registros comparativos no arquivo CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path} ({len(rows)} linhas)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara a Solução Base (Case AFM) com a Heurística a partir do run_config.json."
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=False,
        help="Reaproveita output_baseline.json e output_heuristic.json existentes sem re-executar.",
    )
    parser.add_argument(
        "--only-existing-heuristic",
        action="store_true",
        default=False,
        help="Compara apenas instâncias que já possuem output_heuristic.json gerado.",
    )
    args = parser.parse_args()

    if not RUN_CONFIG_JSON.exists():
        print(f"run_config.json não encontrado em {RUN_CONFIG_JSON}")
        sys.exit(1)

    build_heuristic()

    with open(RUN_CONFIG_JSON, encoding="utf-8") as f:
        run_config = json.load(f)

    rows = collect_comparisons(
        run_config,
        skip_existing=args.skip_existing,
        only_existing_heuristic=args.only_existing_heuristic,
    )
    if not rows:
        print("Nenhuma comparação gerada.")
        return

    write_csv(rows, OUT_CSV)


if __name__ == "__main__":
    main()
