"""
Comparador de Desempenho entre Dois Modelos de Otimização Exata (MIP).

Este módulo compara os resultados do Modelo 1 (original, em `data/trusted/`) com os
resultados do Modelo 2 (novo, em `data/trusted_model2/`) para todas as instâncias
definidas no arquivo de configuração (padrão: `run_config3.json`).

Métricas comparadas por instância (data, status, máquina):
- Função Objetivo (`model1_fo` vs `model2_fo`, diferença absoluta e percentual)
- Valor de Warm Start (`model1_warm_start` vs `model2_warm_start`)
- Gap de otimalidade MIP (`model1_mip_gap` vs `model2_mip_gap`)
- Condição de término (`model1_termination` vs `model2_termination`)
- Quantidade de jobs não alocados (`model1_unallocated` vs `model2_unallocated`)
- Tempo de resolução em segundos (`model1_time_seconds` vs `model2_time_seconds`,
  diferença absoluta, variação percentual e speedup)

Gera o relatório consolidado em `data/compare_models.csv`.

Uso:
    python3 -m src.analysis.compare_models
    python3 -m src.analysis.compare_models --config run_config3.json --trusted-model1 data/trusted --trusted-model2 data/trusted_model2
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TRUSTED_MODEL1 = BASE_DIR / "data" / "trusted"
DEFAULT_TRUSTED_MODEL2 = BASE_DIR / "data" / "trusted_model2"
DEFAULT_RUN_CONFIG = BASE_DIR / "run_config3.json"
DEFAULT_OUT_CSV = BASE_DIR / "data" / "compare_models.csv"

FIELDNAMES = [
    "dt",
    "status",
    "machine_id",
    "machine_name",
    "count_jobs",
    "count_machines",
    "H",
    "model1_fo",
    "model2_fo",
    "fo_diff",
    "fo_diff_pct",
    "model1_warm_start",
    "model2_warm_start",
    "model1_mip_gap",
    "model2_mip_gap",
    "model1_termination",
    "model2_termination",
    "model1_unallocated",
    "model2_unallocated",
    "unallocated_diff",
    "model1_time_seconds",
    "model2_time_seconds",
    "time_diff_seconds",
    "time_diff_pct",
    "speedup",
]


def iso_to_ddmmyyyy(dt: str) -> str:
    """Converte data ISO 'YYYY-MM-DD' para slug 'DDMMYYYY'."""
    return datetime.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")


def _load_machine_results(output_file: Path) -> dict[int, dict]:
    """Carrega o dicionário `machine_id -> entry` de um arquivo `output.json`."""
    if not output_file.exists():
        return {}
    try:
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        return {
            m["machine_id"]: m
            for m in data.get("machines_scheduling", [])
            if "machine_id" in m
        }
    except Exception as exc:
        print(f"  [ERRO] Falha ao ler {output_file}: {exc}")
        return {}


def collect_model_comparisons(
    run_config: dict,
    trusted_model1: Path,
    trusted_model2: Path,
) -> list[dict]:
    """
    Itera sobre as instâncias de `run_config` e compara os resultados entre
    `trusted_model1` (Modelo 1) e `trusted_model2` (Modelo 2).
    """
    rows: list[dict] = []

    for dt, cfg in run_config.items():
        date_slug = iso_to_ddmmyyyy(dt)
        machines_by_status: dict[str, list[str]] | None = cfg.get("machines_by_status")
        default_machines = set(cfg.get("machines", []))

        for status in cfg.get("only_status", []):
            if machines_by_status and status in machines_by_status:
                machines_wanted = set(machines_by_status[status])
            else:
                machines_wanted = default_machines

            dir_m1 = trusted_model1 / date_slug / status
            dir_m2 = trusted_model2 / date_slug / status

            input_file = (
                dir_m1 / "input.json"
                if (dir_m1 / "input.json").exists()
                else dir_m2 / "input.json"
            )
            out_m1_file = dir_m1 / "output.json"
            out_m2_file = dir_m2 / "output.json"

            if not input_file.exists():
                print(f"[skip] {dt} / status={status}: input.json ausente")
                continue

            if not out_m1_file.exists() or not out_m2_file.exists():
                missing = []
                if not out_m1_file.exists():
                    missing.append(f"modelo1 ({out_m1_file})")
                if not out_m2_file.exists():
                    missing.append(f"modelo2 ({out_m2_file})")
                print(
                    f"[skip] {dt} / status={status}: output.json ausente em {', '.join(missing)}"
                )
                continue

            with open(input_file, encoding="utf-8") as f:
                input_data = json.load(f)

            m1_by_id = _load_machine_results(out_m1_file)
            m2_by_id = _load_machine_results(out_m2_file)

            jobs_per_machine: dict[int, int] = {}
            for job in input_data.get("jobs", []):
                if job.get("Status_Processed", "") != "":
                    continue
                m_id = job["assigned_machine_id"]
                jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1

            for m_info in input_data.get("machines", []):
                machine_id = m_info["machine_id"]
                machine_name = m_info["machine_name"]

                if machines_wanted and machine_name not in machines_wanted:
                    continue

                m1 = m1_by_id.get(machine_id)
                m2 = m2_by_id.get(machine_id)
                if m1 is None or m2 is None:
                    print(
                        f"[skip] {dt} / status={status} / {machine_name} (id={machine_id}): "
                        f"ausente em {'modelo1' if m1 is None else 'modelo2'}"
                    )
                    continue

                count_jobs = jobs_per_machine.get(machine_id, 0)
                count_machines = m_info.get("job_capacity")
                start_slots = m_info.get("start_slots", [])
                h_horizon = start_slots[-1] if start_slots else 0

                m1_fo = m1.get("objective_function")
                m2_fo = m2.get("objective_function")
                m1_ws = m1.get("warm_start_value")
                m2_ws = m2.get("warm_start_value")
                m1_gap = m1.get("mip_gap")
                m2_gap = m2.get("mip_gap")
                m1_term = m1.get("termination_condition")
                m2_term = m2.get("termination_condition")
                m1_unalloc = m1.get("count_jobs_not_allocated", 0)
                m2_unalloc = m2.get("count_jobs_not_allocated", 0)
                m1_time = m1.get("solve_time_seconds")
                m2_time = m2.get("solve_time_seconds")

                if m1_fo is not None and m2_fo is not None:
                    fo_diff = m2_fo - m1_fo
                    fo_diff_pct = (fo_diff / m1_fo * 100.0) if m1_fo != 0 else 0.0
                else:
                    fo_diff = None
                    fo_diff_pct = None

                if m1_unalloc is not None and m2_unalloc is not None:
                    unalloc_diff = m2_unalloc - m1_unalloc
                else:
                    unalloc_diff = None

                if m1_time is not None and m2_time is not None:
                    time_diff = m2_time - m1_time
                    time_diff_pct = (
                        (time_diff / m1_time * 100.0) if m1_time > 0 else 0.0
                    )
                    speedup = (m1_time / m2_time) if m2_time > 0 else None
                else:
                    time_diff = None
                    time_diff_pct = None
                    speedup = None

                rows.append(
                    {
                        "dt": dt,
                        "status": status,
                        "machine_id": machine_id,
                        "machine_name": machine_name,
                        "count_jobs": count_jobs,
                        "count_machines": count_machines,
                        "H": h_horizon,
                        "model1_fo": m1_fo,
                        "model2_fo": m2_fo,
                        "fo_diff": fo_diff,
                        "fo_diff_pct": fo_diff_pct,
                        "model1_warm_start": m1_ws,
                        "model2_warm_start": m2_ws,
                        "model1_mip_gap": m1_gap,
                        "model2_mip_gap": m2_gap,
                        "model1_termination": m1_term,
                        "model2_termination": m2_term,
                        "model1_unallocated": m1_unalloc,
                        "model2_unallocated": m2_unalloc,
                        "unallocated_diff": unalloc_diff,
                        "model1_time_seconds": m1_time,
                        "model2_time_seconds": m2_time,
                        "time_diff_seconds": time_diff,
                        "time_diff_pct": time_diff_pct,
                        "speedup": speedup,
                    }
                )

                fo_str = (
                    f"m1={m1_fo:.4f} m2={m2_fo:.4f} diff={fo_diff:+.4f}"
                    if (m1_fo is not None and m2_fo is not None and fo_diff is not None)
                    else f"m1={m1_fo} m2={m2_fo}"
                )
                time_str = (
                    f"m1={m1_time:.3f}s m2={m2_time:.3f}s diff={time_diff:+.3f}s ({time_diff_pct:+.1f}%)"
                    if (
                        m1_time is not None
                        and m2_time is not None
                        and time_diff is not None
                        and time_diff_pct is not None
                    )
                    else f"m1={m1_time}s m2={m2_time}s"
                )
                print(
                    f"[{dt}/{status}] {machine_name} (id={machine_id})"
                    f" | jobs={count_jobs} mach={count_machines} H={h_horizon}"
                    f" | fo: {fo_str}"
                    f" | term: {m1_term} vs {m2_term}"
                    f" | tempo: {time_str}"
                )

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    """Grava os registros comparativos entre Modelo 1 e Modelo 2 em CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path} ({len(rows)} linhas)")


def print_summary(rows: list[dict]) -> None:
    """Exibe um resumo estatístico da comparação entre os dois modelos."""
    if not rows:
        return

    both_opt = [
        r
        for r in rows
        if r["model1_termination"] == "optimal"
        and r["model2_termination"] == "optimal"
    ]
    valid_times = [
        r
        for r in rows
        if r["model1_time_seconds"] is not None
        and r["model2_time_seconds"] is not None
    ]
    valid_fo = [r for r in rows if r["fo_diff"] is not None]

    print("\n==========================================")
    print("  Resumo Comparativo: Modelo 1 vs Modelo 2")
    print("==========================================")
    print(f"  Instâncias comparadas : {len(rows)}")
    print(f"  Ótimo em ambos        : {len(both_opt)}")
    if valid_times:
        t1_total = sum(float(r["model1_time_seconds"]) for r in valid_times)
        t2_total = sum(float(r["model2_time_seconds"]) for r in valid_times)
        t1_mean = t1_total / len(valid_times)
        t2_mean = t2_total / len(valid_times)
        print(f"  Tempo total Modelo 1  : {t1_total:.2f}s (média: {t1_mean:.2f}s)")
        print(f"  Tempo total Modelo 2  : {t2_total:.2f}s (média: {t2_mean:.2f}s)")
        if t2_total > 0:
            print(f"  Speedup global        : {t1_total / t2_total:.2f}x")
    if valid_fo:
        max_abs_fo_diff = max(abs(float(r["fo_diff"])) for r in valid_fo)
        print(f"  Maior |fo_diff|       : {max_abs_fo_diff:.6g}")
    print("==========================================")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara os resultados de dois modelos MIP (ex: data/trusted vs data/trusted_model2)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_RUN_CONFIG,
        help=f"Arquivo run_config JSON (default: {DEFAULT_RUN_CONFIG.name}).",
    )
    parser.add_argument(
        "--trusted-model1",
        type=Path,
        default=DEFAULT_TRUSTED_MODEL1,
        help="Diretório raiz dos resultados do Modelo 1 (default: data/trusted).",
    )
    parser.add_argument(
        "--trusted-model2",
        type=Path,
        default=DEFAULT_TRUSTED_MODEL2,
        help="Diretório raiz dos resultados do Modelo 2 (default: data/trusted_model2).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_CSV,
        help="Caminho do arquivo CSV de saída (default: data/compare_models.csv).",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Arquivo de configuração não encontrado: {args.config}")
        sys.exit(1)

    with open(args.config, encoding="utf-8") as f:
        run_config = json.load(f)

    rows = collect_model_comparisons(
        run_config=run_config,
        trusted_model1=args.trusted_model1,
        trusted_model2=args.trusted_model2,
    )
    if not rows:
        print("Nenhuma comparação gerada.")
        return

    write_csv(rows, args.out)
    print_summary(rows)


if __name__ == "__main__":
    main()
