import itertools
import json
import logging
import os
import re
from datetime import datetime

import pandas as pd
import pytest

logger = logging.getLogger(__name__)

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
TRUSTED_ROOT = DATA_ROOT / "trusted"
RUN_CONFIG_PATH = PROJECT_ROOT / "run_config.json"


def _load_run_config() -> dict:
    if not RUN_CONFIG_PATH.exists():
        return {}
    with open(RUN_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


RUN_CONFIG = _load_run_config()


# ---------------------------------------------------------------------------
# Descoberta de pares (partição, status) em data/trusted
# ---------------------------------------------------------------------------


def _partitions() -> list[tuple]:
    max_pairs = int(os.getenv("MAX_PAIRS", "0"))
    combos = []

    if not TRUSTED_ROOT.exists():
        logger.warning("data/trusted não encontrado em %s.", TRUSTED_ROOT)
        return combos

    for partition_dir in sorted(TRUSTED_ROOT.iterdir()):
        if not partition_dir.is_dir() or not re.fullmatch(r"\d{8}", partition_dir.name):
            continue

        # Filtra por run_config se disponível
        if RUN_CONFIG:
            try:
                date_iso = datetime.strptime(partition_dir.name, "%d%m%Y").strftime("%Y-%m-%d")
            except ValueError:
                continue
            if date_iso not in RUN_CONFIG:
                continue
            allowed_statuses = set(RUN_CONFIG[date_iso].get("only_status", []))
        else:
            date_iso = None
            allowed_statuses = set()

        for status_dir in sorted(partition_dir.iterdir()):
            if not status_dir.is_dir():
                continue
            if allowed_statuses and status_dir.name not in allowed_statuses:
                continue
            if not (status_dir / "input.json").exists():
                continue
            if not (status_dir / "output.json").exists():
                continue
            demanda_dir = status_dir / "demanda"
            if not demanda_dir.exists() or not list(demanda_dir.glob("*.parquet")):
                continue
            combos.append((partition_dir, status_dir))
            if max_pairs and len(combos) >= max_pairs:
                return combos

    logger.info("Pares encontrados em trusted: %d", len(combos))
    return combos


pairs = _partitions()
pair_ids = [f"{p.name}-{s.name}" for p, s in pairs]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", params=pairs, ids=pair_ids)
def partition_status(request):
    return request.param  # (partition_dir, status_dir)


@pytest.fixture(scope="module")
def allowed_machines(partition_status) -> set[str]:
    """Máquinas permitidas pelo run_config para este par. Vazio = todas."""
    partition_dir, _ = partition_status
    if not RUN_CONFIG:
        return set()
    try:
        date_iso = datetime.strptime(partition_dir.name, "%d%m%Y").strftime("%Y-%m-%d")
    except ValueError:
        return set()
    return set(RUN_CONFIG.get(date_iso, {}).get("machines", []))


@pytest.fixture(scope="module")
def input_json(partition_status):
    partition_dir, status_dir = partition_status
    path = TRUSTED_ROOT / partition_dir.name / status_dir.name / "input.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


REQUIRED_COLS = {"status_processed", "inicio", "fim", "job_id", "maquina", "sub_machine"}


@pytest.fixture(scope="module")
def output_demand_df(partition_status, allowed_machines):
    partition_dir, status_dir = partition_status
    trusted_dir = TRUSTED_ROOT / partition_dir.name / status_dir.name
    parquet_files = list((trusted_dir / "demanda").glob("*.parquet"))
    assert parquet_files, f"Nenhum parquet em {trusted_dir / 'demanda'}"
    df = pd.read_parquet(parquet_files[-1])
    df.columns = df.columns.str.lower()
    missing_cols = REQUIRED_COLS - set(df.columns)
    assert not missing_cols, (
        f"[{partition_dir.name}/{status_dir.name}] Colunas faltando no parquet: {missing_cols}"
    )
    df["inicio"] = pd.to_datetime(df["inicio"])
    df["fim"] = pd.to_datetime(df["fim"])
    if "not_before_date" in df.columns:
        df["not_before_date"] = pd.to_datetime(df["not_before_date"])
    if allowed_machines:
        df = df[df["maquina"].isin(allowed_machines)]
    return df


# ---------------------------------------------------------------------------
# Testes de integridade do pipeline
# ---------------------------------------------------------------------------
def _log_job_coverage(
    partition_status, input_json, output_demand_df, allowed_machines: set[str] | None = None
) -> None:
    """Loga quantos jobs do input aparecem no output (não-alocados são válidos)."""
    if allowed_machines:
        allowed_ids = {
            m["machine_id"]
            for m in input_json["machines"]
            if m["machine_name"] in allowed_machines
        }
        input_ids = {
            j["id"]
            for j in input_json["jobs"]
            if j.get("Status_Processed", "") == "" and j["assigned_machine_id"] in allowed_ids
        }
    else:
        input_ids = {j["id"] for j in input_json["jobs"] if j.get("Status_Processed", "") == ""}

    output_ids = set(output_demand_df["job_id"].dropna().astype(int))
    missing = input_ids - output_ids
    extra = output_ids - input_ids
    logger.info(
        "[%s/%s] Cobertura jobs: %d/%d no output",
        partition_status[0].name,
        partition_status[1].name,
        len(input_ids) - len(missing),
        len(input_ids),
    )
    if missing:
        logger.warning(
            "[%s/%s] %d jobs do input ausentes no output (não alocados): %s",
            partition_status[0].name,
            partition_status[1].name,
            len(missing),
            sorted(missing),
        )
    if extra:
        logger.warning(
            "[%s/%s] %d job_ids no output sem correspondência no input: %s",
            partition_status[0].name,
            partition_status[1].name,
            len(extra),
            sorted(extra),
        )


def test_all_jobs_present(partition_status, input_json, output_demand_df, allowed_machines):
    """Todos os jobs a agendar do input devem aparecer no output; jobs faltando são logados."""
    _log_job_coverage(partition_status, input_json, output_demand_df, allowed_machines)
    if allowed_machines:
        allowed_ids = {
            m["machine_id"]
            for m in input_json["machines"]
            if m["machine_name"] in allowed_machines
        }
        input_ids = {
            j["id"]
            for j in input_json["jobs"]
            if j.get("Status_Processed", "") == "" and j["assigned_machine_id"] in allowed_ids
        }
    else:
        input_ids = {j["id"] for j in input_json["jobs"] if j.get("Status_Processed", "") == ""}
    output_ids = set(output_demand_df["job_id"].dropna().astype(int))
    extra = output_ids - input_ids
    assert not extra, (
        f"[{partition_status[0].name}/{partition_status[1].name}] "
        f"job_ids no output sem correspondência no input: {sorted(extra)}"
    )


def test_only_start(partition_status, output_demand_df):
    """Jobs agendados (status_processed vazio) devem ter inicio preenchido."""
    scheduled = output_demand_df[output_demand_df["status_processed"] == ""]
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job agendado encontrado; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return
    assert scheduled["inicio"].notna().all(), "Jobs agendados com inicio nulo."


def test_not_before_date(partition_status, output_demand_df):
    """Nenhum job pode iniciar antes do seu not_before_date."""
    scheduled = output_demand_df[output_demand_df["status_processed"] == ""]
    scheduled = scheduled.dropna(subset=["inicio", "not_before_date"])
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job com inicio e not_before_date preenchidos; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return
    invalid = scheduled[
        scheduled["inicio"].dt.date < scheduled["not_before_date"].dt.date
    ]
    assert invalid.empty, "Jobs iniciaram antes do not_before_date:\n" + "\n".join(
        f"  job_id={row['job_id']} inicio={row['inicio'].date()}"
        f" < not_before={row['not_before_date'].date()}"
        for _, row in invalid.iterrows()
    )


# ---------------------------------------------------------------------------
# Testes de restrições do modelo
# ---------------------------------------------------------------------------


def test_no_overlap_same_submachine(partition_status, output_demand_df):
    """Dois jobs na mesma (máquina, sub_machine) não podem se sobrepor."""
    scheduled = output_demand_df[output_demand_df["status_processed"] == ""].copy()
    scheduled = scheduled.dropna(subset=["inicio", "fim"])
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job com inicio e fim preenchidos; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return

    violations = []
    for (machine, sub_machine), group in scheduled.groupby(["maquina", "sub_machine"]):
        group = group.sort_values("inicio").reset_index(drop=True)
        for i in range(len(group) - 1):
            end_a = group.loc[i, "fim"]
            start_b = group.loc[i + 1, "inicio"]
            if start_b < end_a:
                violations.append(
                    f"maq={machine} sub={sub_machine}: "
                    f"job {group.loc[i, 'job_id']} termina {end_a}, "
                    f"job {group.loc[i + 1, 'job_id']} começa {start_b}"
                )

    assert not violations, "Sobreposições detectadas:\n" + "\n".join(violations)


def test_parallel_jobs(partition_status, output_demand_df, input_json, allowed_machines):
    """O índice máximo de sub-máquina não ultrapassa job_capacity - 1."""
    _log_job_coverage(partition_status, input_json, output_demand_df, allowed_machines)
    machine_capacity = {
        m["machine_name"]: m["job_capacity"] for m in input_json["machines"]
    }
    scheduled = output_demand_df[output_demand_df["status_processed"] == ""]
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job agendado encontrado; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return

    violations = []
    for machine_name, group in scheduled.groupby("maquina"):
        max_capacity = machine_capacity.get(machine_name)
        if max_capacity is None:
            logger.warning(
                "[%s/%s] Máquina '%s' não encontrada em input.json; ignorando.",
                partition_status[0].name,
                partition_status[1].name,
                machine_name,
            )
        max_sub = group["sub_machine"].max()
        if not pd.isna(max_sub) and max_sub >= max_capacity:
            violations.append(
                f"maq={machine_name}: sub_machine máxima={int(max_sub)}"
                f" >= job_capacity={max_capacity}"
            )

    assert not violations, "Capacidade de sub-máquinas excedida:\n" + "\n".join(
        violations
    )


def test_setup_times(partition_status, output_demand_df, input_json, allowed_machines):
    """Gap entre jobs consecutivos na mesma sub-máquina respeita o tempo de setup."""
    _log_job_coverage(partition_status, input_json, output_demand_df, allowed_machines)
    time_step = int(input_json.get("time_step", 5))
    setups = input_json.get("setups", {})
    name_to_id = {m["machine_name"]: m["machine_id"] for m in input_json["machines"]}

    scheduled = output_demand_df[output_demand_df["status_processed"] == ""]
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job agendado encontrado; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return

    violations = []
    for machine_name, machine_group in scheduled.groupby("maquina"):
        machine_id = name_to_id.get(machine_name)
        machine_setups = (
            setups.get(str(machine_id), {}) if machine_id is not None else {}
        )
        if not machine_setups:
            logger.info(
                "[%s/%s] Máquina '%s' sem setups definidos; pulando verificação de setup.",
                partition_status[0].name,
                partition_status[1].name,
                machine_name,
            )
        for sub_machine, group in machine_group.groupby("sub_machine"):
            group = group.sort_values("inicio").reset_index(drop=True)
            for i in range(len(group) - 1):
                job_a = group.iloc[i]
                job_b = group.iloc[i + 1]

                setup_slots = machine_setups.get(str(int(job_a["job_id"])), {}).get(
                    str(int(job_b["job_id"])), 0
                )
                setup_min = setup_slots * time_step
                gap_min = (job_b["inicio"] - job_a["fim"]).total_seconds() / 60

                if gap_min < setup_min:
                    violations.append(
                        f"maq={machine_name} sub={sub_machine}: "
                        f"job {int(job_a['job_id'])}→{int(job_b['job_id'])}: "
                        f"gap={gap_min:.1f}min < setup={setup_min}min"
                    )

    assert not violations, "Setup insuficiente:\n" + "\n".join(violations)


def test_resource_constraint(partition_status, output_demand_df, input_json, allowed_machines):
    """
    Jobs com mesmo resource_id em sub-máquinas diferentes devem ter gap >= big_setup.
    Valida a restrição _resource_constraint_rule do modelo.
    """
    _log_job_coverage(partition_status, input_json, output_demand_df, allowed_machines)
    big_setup_slots = input_json.get("big_setup", 0)
    time_step = int(input_json.get("time_step", 5))
    big_setup_min = big_setup_slots * time_step

    if big_setup_min == 0:
        pytest.skip("big_setup é zero, restrição não se aplica")

    scheduled = output_demand_df[output_demand_df["status_processed"] == ""].copy()
    scheduled = scheduled.dropna(subset=["inicio", "fim", "resource_id"])
    if scheduled.empty:
        logger.warning(
            "[%s/%s] Nenhum job com resource_id, inicio e fim preenchidos; nada a validar.",
            partition_status[0].name,
            partition_status[1].name,
        )
        return

    violations = []
    checked_groups = 0
    for (machine, resource_id), group in scheduled.groupby(["maquina", "resource_id"]):
        sub_machines = group["sub_machine"].unique()
        if len(sub_machines) < 2:
            continue

        checked_groups += 1
        for sub_a, sub_b in itertools.combinations(sub_machines, 2):
            jobs_a = group[group["sub_machine"] == sub_a].sort_values("inicio")
            jobs_b = group[group["sub_machine"] == sub_b].sort_values("inicio")
            for _, job_a in jobs_a.iterrows():
                for _, job_b in jobs_b.iterrows():
                    earlier, later = (
                        (job_a, job_b)
                        if job_a["inicio"] <= job_b["inicio"]
                        else (job_b, job_a)
                    )
                    gap_min = (later["inicio"] - earlier["fim"]).total_seconds() / 60
                    if gap_min < big_setup_min:
                        violations.append(
                            f"maq={machine} resource={resource_id} "
                            f"sub={int(earlier['sub_machine'])}→{int(later['sub_machine'])}: "
                            f"gap={gap_min:.1f}min < big_setup={big_setup_min}min"
                        )

    if checked_groups == 0:
        logger.info(
            "[%s/%s] Nenhum resource_id aparece em mais de uma sub-máquina; restrição não exercitada.",
            partition_status[0].name,
            partition_status[1].name,
        )

    assert not violations, "Violações de resource_constraint:\n" + "\n".join(violations)
