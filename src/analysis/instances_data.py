"""
Orquestrador de Descoberta e Preparação de Instâncias de Otimização.

Este módulo realiza o fluxo completo de pré-processamento das instâncias do projeto:
1. Varre `data/raw/` para descobrir todos os lotes de demanda disponíveis (`<DDMMYYYY>/<status>/demanda/`).
2. Executa `src/main/data_input_process.py` para cada data, gerando os arquivos estruturados `input.json` em `data/trusted/`.
3. Coleta os metadados de cada instância (número de jobs, capacidade da máquina, horizonte, recursos necessários) e gera o arquivo `data/instances.csv`.
4. Gera o arquivo central de execução `run_config.json`, que define quais datas, lotes (status) e máquinas serão de fato executados pelo otimizador MIP (`src/main/optimize.py`) ou pela Heurística C++ (`src/heuristics/`).
   - Aplica filtros configuráveis (`INSTANCE_FILTERS`) por capacidade e número de jobs.
   - Permite pular ou reexecutar instâncias já processadas (`SKIP_EXISTING_OUTPUT`).
   - Ordena a fila de execução pelo número acumulado de jobs (instâncias menores primeiro).

Uso:
    python3 -m src.analysis.instances_data
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
LATEST_DIR = BASE_DIR / "data" / "latest"
SCRIPTS_DIR = BASE_DIR / "src" / "main"
INSTANCES_CSV = BASE_DIR / "data" / "instances.csv"
RUN_CONFIG_JSON = BASE_DIR / "run_config.json"

# Flag para ativar ou desativar os filtros de instâncias ao gerar o run_config.json
# True: aplica INSTANCE_FILTERS; False: inclui todas as instâncias encontradas
USE_INSTANCE_FILTERS = True

# Critérios de filtro para elegibilidade das instâncias no run_config.json.
# Cada tupla representa: (job_capacity, min_jobs, max_jobs).
# Instâncias cuja capacidade da máquina e número de jobs não casarem com nenhuma tupla
# serão descartadas do run_config.json quando USE_INSTANCE_FILTERS = True.
INSTANCE_FILTERS: list[tuple[int, int, int]] = [
    (2, 2, 300),
    (1, 4, 300),
    (10, 10, 300),
]

# Controla se ignora instâncias já resolvidas ou se limpa outputs anteriores:
# True: ignora pares (dt, status) que já possuem output.json em data/trusted/
# False: limpa previamente os output.json existentes para reexecução completa
SKIP_EXISTING_OUTPUT = False

PYTHON = sys.executable


# -----------------------------------------------------------------------------
# Utilitários de Data e Descoberta
# -----------------------------------------------------------------------------


def ddmmyyyy_to_iso(date_slug: str) -> str:
    """
    Converte uma string de data no formato slug 'DDMMYYYY' para o formato ISO 'YYYY-MM-DD'.

    Args:
        date_slug: Data no formato 'DDMMYYYY' (ex: '13102025').

    Returns:
        Data formatada em ISO 'YYYY-MM-DD' (ex: '2025-10-13').
    """
    return datetime.strptime(date_slug, "%d%m%Y").strftime("%Y-%m-%d")


def discover_batches(raw_dir: Path) -> list[tuple[str, str]]:
    """
    Varre o diretório de dados brutos (`data/raw`) e localiza todos os lotes válidos.

    Um lote é considerado válido se estiver estruturado como:
    `data/raw/<DDMMYYYY>/<status>/demanda/` contendo arquivos Parquet.

    Args:
        raw_dir: Caminho para o diretório `data/raw`.

    Returns:
        Lista de tuplas `(date_slug, status_name)`, ordenadas alfabeticamente.
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
# Pipeline de Ingestão e Processamento
# -----------------------------------------------------------------------------


def run_data_input(date_iso: str) -> bool:
    """
    Invoca o script `src/main/data_input_process.py` como subprocesso para uma data específica.

    Esse processamento lê os arquivos Parquet de demanda de todos os status daquela data,
    carrega os parâmetros de máquinas/recursos/turnos de `data/raw/model_config`,
    e gera a representação serializada `input.json` em `data/trusted/<DDMMYYYY>/<status>/`.

    Args:
        date_iso: Data no formato ISO 'YYYY-MM-DD'.

    Returns:
        True se o subprocesso encerrou com sucesso (código 0), False caso contrário.
    """
    cmd = [
        PYTHON,
        str(SCRIPTS_DIR / "data_input_process.py"),
        "--dt",
        date_iso,
        "--raw-root",
        str(RAW_DIR),
        "--trusted-root",
        str(TRUSTED_DIR),
        "--model-config-dir",
        str(RAW_DIR / "model_config"),
    ]
    print(f"  [input] --dt {date_iso}")
    result = subprocess.run(cmd)
    return result.returncode == 0


# -----------------------------------------------------------------------------
# Extração de Métricas e Geração do instances.csv
# -----------------------------------------------------------------------------


def collect_instances(trusted_dir: Path) -> list[dict]:
    """
    Lê todos os arquivos `input.json` em `data/trusted/` e compila os metadados de cada instância.

    Extrai por máquina:
    - Data e status da partição
    - ID e nome da máquina
    - Capacidade em sub-máquinas paralelas (job_capacity)
    - Quantidade de jobs pendentes atribuídos
    - Quantidade de recursos distintos requeridos
    - Palavras de 64 bits necessárias para o modelo Time-Index (W(Necessario))

    Args:
        trusted_dir: Caminho para a pasta `data/trusted`.

    Returns:
        Lista de dicionários, onde cada item representa uma máquina em uma instância.
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

        jobs_per_machine: dict[int, int] = {}
        resources_per_machine: dict[int, set] = {}
        for job in data.get("jobs", []):
            if job.get("Status_Processed", "") != "":
                continue
            m_id = job["assigned_machine_id"]
            jobs_per_machine[m_id] = jobs_per_machine.get(m_id, 0) + 1
            if m_id not in resources_per_machine:
                resources_per_machine[m_id] = set()
            if "resource_id" in job:
                resources_per_machine[m_id].add(job["resource_id"])

        for machine in data.get("machines", []):
            m_id = machine["machine_id"]
            job_capacity = machine["job_capacity"]
            start_slots = machine.get("start_slots", [])
            h_effective = start_slots[-1] if start_slots else 0
            w_needed = (h_effective // 64) + 1
            num_resources = len(resources_per_machine.get(m_id, set()))

            rows.append(
                {
                    "date": date_iso,
                    "status": status,
                    "machine_id": m_id,
                    "machine_name": machine["machine_name"],
                    "job_capacity": job_capacity,
                    "count_jobs": jobs_per_machine.get(m_id, 0),
                    "Quantia de recursos": num_resources,
                    "maquinas": job_capacity,
                    "W(Necessario)": w_needed,
                }
            )
    return rows


def write_instances_csv(rows: list[dict], path: Path) -> None:
    """
    Persiste os registros coletados das instâncias no arquivo CSV de destino.

    Args:
        rows: Lista de dicionários gerada por `collect_instances`.
        path: Caminho de saída (normalmente `data/instances.csv`).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "status",
                "machine_id",
                "machine_name",
                "job_capacity",
                "count_jobs",
                "Quantia de recursos",
                "maquinas",
                "W(Necessario)",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV gerado: {path}")


# -----------------------------------------------------------------------------
# Geração do Arquivo de Configuração de Execução (run_config.json)
# -----------------------------------------------------------------------------


_OPTIMAL_CONDITION = "TerminationCondition.convergenceCriteriaSatisfied"


def _has_output(dt: str, status: str, trusted_dir: Path = TRUSTED_DIR) -> bool:
    """
    Verifica se uma instância específica já foi resolvida com sucesso no passado.

    Considera resolvida se o arquivo `output.json` existir e todas as máquinas
    escalonadas tiverem atingido a condição de parada ótima (`_OPTIMAL_CONDITION`).

    Args:
        dt: Data da partição em formato ISO 'YYYY-MM-DD'.
        status: Identificador do status / lote.
        trusted_dir: Diretório raiz de `data/trusted`.

    Returns:
        True se a instância já estiver resolvida e ótima, False caso contrário.
    """
    from datetime import datetime as _dt

    date_slug = _dt.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")
    output_path = trusted_dir / date_slug / status / "output.json"
    if not output_path.exists():
        return False
    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)
    machines = data.get("machines_scheduling", [])
    return bool(machines) and all(
        m.get("termination_condition") == _OPTIMAL_CONDITION for m in machines
    )


def _matches_filters(
    job_capacity: int, count_jobs: int, filters: list[tuple[int, int, int]]
) -> bool:
    """
    Valida se uma instância atende a pelo menos uma das faixas de filtragem configuradas.

    Args:
        job_capacity: Quantidade de sub-máquinas paralelas da máquina.
        count_jobs: Quantidade de jobs pendentes atribuídos a ela.
        filters: Lista de regras `(job_capacity, min_jobs, max_jobs)`.

    Returns:
        True se a instância for elegível segundo as regras, False caso contrário.
    """
    return any(
        job_capacity == cap and min_j <= count_jobs <= max_j
        for cap, min_j, max_j in filters
    )


def generate_run_config(
    instances_csv: Path,
    out_path: Path,
    filters: list[tuple[int, int, int]] = INSTANCE_FILTERS,
    use_filters: bool = USE_INSTANCE_FILTERS,
    skip_existing: bool = SKIP_EXISTING_OUTPUT,
) -> None:
    """
    Lê o `data/instances.csv` e constrói o arquivo central `run_config.json`.

    O `run_config.json` é a especificação que governa a execução do otimizador MIP
    (`src/main/optimize.py`), do comparador de heurísticas (`src/analysis/compare_heuristic.py`)
    e do orquestrador em lote (`./run.sh`).

    Formato gerado:
    ```json
    {
      "YYYY-MM-DD": {
        "only_status": ["status_1", "status_2"],
        "machines": ["processo_recurso_1", "processo_recurso_2"]
      }
    }
    ```

    Etapas do processamento:
    1. Filtra instâncias por capacidade e volume de jobs caso `use_filters=True`.
    2. Descarta instâncias já resolvidas otimamente caso `skip_existing=True`.
    3. Agrupa por data e status quais máquinas devem ser otimizadas.
    4. Ordena as datas pelo total acumulado de jobs (instâncias menores executam primeiro).
    5. Grava o JSON formatado no caminho de destino.

    Args:
        instances_csv: Caminho para o `data/instances.csv` contendo as instâncias catalogadas.
        out_path: Caminho onde o `run_config.json` será salvo.
        filters: Lista de tuplas `(job_capacity, min_jobs, max_jobs)`.
        use_filters: Se True, aplica a lista de filtros `filters`.
        skip_existing: Se True, ignora instâncias com `output.json` já ótimo.
    """
    import csv as _csv

    groups: dict[str, dict[str, set[str]]] = {}
    dt_total_jobs: dict[str, int] = {}
    skipped = 0

    with open(instances_csv, encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            count = int(row["count_jobs"])
            capacity = int(row["job_capacity"])
            if use_filters and not _matches_filters(capacity, count, filters):
                continue
            dt, status, machine = row["date"], row["status"], row["machine_name"]
            if skip_existing and _has_output(dt, status):
                skipped += 1
                continue
            groups.setdefault(dt, {}).setdefault(status, set()).add(machine)
            dt_total_jobs[dt] = dt_total_jobs.get(dt, 0) + count

    # Ordena dt por total de jobs acumulado (menor → maior) para priorizar instâncias rápidas
    sorted_dts = sorted(groups, key=lambda d: dt_total_jobs[d])

    config: dict = {}
    for dt in sorted_dts:
        statuses = sorted(groups[dt].keys())
        machines = sorted({m for ms in groups[dt].values() for m in ms})
        config[dt] = {"only_status": statuses, "machines": machines}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    total = sum(len(v["only_status"]) for v in config.values())
    filter_label = filters if use_filters else "desativados"
    print(f"\nrun_config.json gerado: {out_path}")
    print(f"  {len(config)} datas | {total} lotes | filtros: {filter_label}")
    if skip_existing and skipped:
        print(f"  {skipped} lotes ignorados (output.json já existe)")


# -----------------------------------------------------------------------------
# Limpeza de Outputs Anteriores
# -----------------------------------------------------------------------------


def cleanup_all_outputs(
    trusted_dir: Path = TRUSTED_DIR,
    latest_dir: Path = LATEST_DIR,
) -> None:
    """
    Remove todos os arquivos `output.json` de `data/trusted/` e limpa `data/latest/`.

    Essa limpeza é disparada quando `SKIP_EXISTING_OUTPUT = False`, garantindo
    que nenhuma execução anterior interfira no novo ciclo do pipeline.

    Args:
        trusted_dir: Diretório raiz de `data/trusted/`.
        latest_dir: Diretório raiz de `data/latest/`.
    """
    import shutil

    deleted_outputs = 0
    for output_file in sorted(trusted_dir.rglob("output.json")):
        output_file.unlink()
        deleted_outputs += 1
        print(f"  [cleanup] removido {output_file.relative_to(BASE_DIR)}")

    deleted_latest = 0
    if latest_dir.is_dir():
        for status_dir in sorted(latest_dir.iterdir()):
            if status_dir.is_dir():
                shutil.rmtree(status_dir)
                deleted_latest += 1
                print(f"  [cleanup] removido latest/{status_dir.name}/")

    print(
        f"\n[cleanup] {deleted_outputs} output.json removidos"
        f" | {deleted_latest} latest/ removidos"
    )


# -----------------------------------------------------------------------------
# Orquestração Principal
# -----------------------------------------------------------------------------


def main() -> None:
    """
    Fluxo principal de orquestração do módulo:
    1. Se `SKIP_EXISTING_OUTPUT` for False, executa a limpeza prévia de outputs antigos.
    2. Descobre todos os lotes em `data/raw/` com `discover_batches`.
    3. Executa `data_input_process.py` para cada data única encontrada, gerando os `input.json`.
    4. Compila as métricas das instâncias em `data/instances.csv` via `collect_instances`.
    5. Constrói o `run_config.json` aplicando os filtros configurados via `generate_run_config`.
    """
    if not SKIP_EXISTING_OUTPUT:
        cleanup_all_outputs()

    batches = discover_batches(RAW_DIR)
    if not batches:
        print(f"Nenhum lote encontrado em {RAW_DIR}")
        return

    print(f"Lotes encontrados: {len(batches)}\n")

    # Executa data_input_process uma única vez por data distinta
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
                f" → {row['count_jobs']} jobs, capacity={row['job_capacity']}, "
                f"R={row['Quantia de recursos']}, M={row['maquinas']}, W={row['W(Necessario)']}"
            )
    else:
        print("\nNenhum input.json encontrado.")
        return

    # Gera a matriz de instâncias ativas a serem processadas pelo pipeline
    generate_run_config(INSTANCES_CSV, RUN_CONFIG_JSON)


if __name__ == "__main__":
    main()
