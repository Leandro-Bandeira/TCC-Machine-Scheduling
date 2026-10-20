"""
Comparador de Desempenho: Otimização Exata (MIP) vs Heurística ILS/VNS.

Este módulo realiza a comparação sistemática entre:
1. A solução exata gerada pelo solver MIP (`output.json`) via `src/main/optimize.py`.
2. A solução heurística gerada pelo executável C++ (`output_heuristic.json`) via `src/heuristics/`.

Para cada instância ativa listada em `run_config.json`:
- Compila o binário da heurística C++ (`make -C src/heuristics`), se necessário.
- Executa a heurística (ou reaproveita execuções prévias se `--skip-existing` for informado).
- Compara métricas-chave por máquina:
  - Função Objetivo (FO MIP vs FO Heurística, com diferença absoluta e percentual).
  - Quantidade de jobs não alocados / penalizados (`unallocated`).
  - Tempo de execução em segundos (`mip_time_seconds` vs `heuristic_time_seconds`).
  - Gap do MIP e dimensões do problema (`count_jobs`, `count_machines`).

Gera o relatório consolidado em `data/heuristic_vs_mip.csv`.

Uso:
    python3 -m src.analysis.compare_heuristic
    python3 -m src.analysis.compare_heuristic --skip-existing
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
    """
    Converte uma string de data no formato ISO 'YYYY-MM-DD' para o formato 'DDMMYYYY'.

    Args:
        dt: Data no formato ISO 'YYYY-MM-DD' (ex: '2025-12-10').

    Returns:
        Data no formato 'DDMMYYYY' (ex: '10122025').
    """
    return datetime.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")


def build_heuristic() -> None:
    """
    Compila o executável C++ da heurística invocando `make` no diretório `src/heuristics/`.

    Garante que as últimas alterações no código C++ sejam refletidas no binário `./heuristic`.

    Raises:
        subprocess.CalledProcessError: Se a compilação via `make` falhar.
    """
    print("[build] make -C src/heuristics")
    subprocess.run(["make"], cwd=HEURISTICS_DIR, check=True)


def run_heuristic(input_file: Path, machine_id: int) -> None:
    """
    Executa o binário da heurística C++ para uma máquina específica de uma instância.

    Invoca `./heuristic <caminho_input.json> <machine_id>`. O binário salva o resultado
    em `output_heuristic.json` no mesmo diretório do `input.json`.

    Args:
        input_file: Caminho para o `input.json` da instância.
        machine_id: ID numérico da máquina a ser escalonada.

    Raises:
        subprocess.CalledProcessError: Se a execução do binário C++ retornar erro.
    """
    subprocess.run(
        [str(HEURISTIC_BIN), str(input_file), str(machine_id)],
        capture_output=True,
        text=True,
        check=True,
    )


def read_heuristic_json(
    heuristic_file: Path, machine_id: int
) -> tuple[float | None, float | None, int | None]:
    """
    Extrai as métricas de desempenho de uma máquina específica a partir de `output_heuristic.json`.

    Args:
        heuristic_file: Caminho para o arquivo `output_heuristic.json`.
        machine_id: ID numérico da máquina desejada.

    Returns:
        Tupla contendo `(objective_function, solve_time_seconds, count_jobs_not_allocated)`.
        Retorna `(None, None, None)` se o arquivo não existir ou se a máquina não for encontrada.
    """
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
    """
    Itera sobre a matriz de instâncias ativas em `run_config.json` e consolida a comparação MIP vs Heurística.

    Para cada par (data, status) e cada máquina configurada:
    1. Lê a solução MIP de `output.json`.
    2. Lê (ou executa via C++) a solução da Heurística em `output_heuristic.json`.
    3. Calcula diferenças absolutas e percentuais da função objetivo e do tempo de execução.

    Args:
        run_config: Dicionário carregado de `run_config.json`.
        skip_existing: Se True, tenta ler `output_heuristic.json` existente sem reexecutar.

    Returns:
        Lista de dicionários formatados prontos para exportação em CSV.
    """
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
    """
    Grava os registros comparativos entre MIP e Heurística no arquivo CSV de saída.

    Args:
        rows: Lista de dicionários com as métricas calculadas.
        path: Caminho de destino (normalmente `data/heuristic_vs_mip.csv`).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path} ({len(rows)} linhas)")


def main() -> None:
    """
    Ponto de entrada do script de comparação:
    1. Lê os argumentos da linha de comando (`--skip-existing`).
    2. Valida a existência de `run_config.json`.
    3. Compila a heurística C++ com `make`.
    4. Coleta as comparações para cada instância ativa em `run_config.json`.
    5. Grava o relatório consolidado em `data/heuristic_vs_mip.csv`.
    """
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

