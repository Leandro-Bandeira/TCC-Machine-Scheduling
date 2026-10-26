from __future__ import annotations

import argparse
import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pandas.tseries.offsets import CustomBusinessDay
from unidecode import unidecode


# ============================================================
# LOGGING
# ============================================================

LOG_FMT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("baseline-operators")


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "POC" / "results_baseline"

WORK_DAYS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
DEFAULT_TIME_STEP = 5  # minutos
SLOTS_PER_DAY_DEFAULT = (24 * 60) // DEFAULT_TIME_STEP  # 288 slots/dia
BIG_SETUP_MINUTES = 5 * 60  # 5 horas (60 slots)


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class MachineInfo:
    machine_id: int
    machine_name: str
    processo: str
    recurso: str
    job_capacity: int
    oee: float
    max_dia_minutes: float
    turnos: List[int]
    daily_capacity: Dict[pd.Timestamp, float]
    daily_windows: Dict[pd.Timestamp, List[Tuple[datetime, datetime]]]
    last_slot_day: List[int] = field(default_factory=list)
    start_slots: List[int] = field(default_factory=list)
    next_start_slots: List[int] = field(default_factory=list)
    first_slot: int = 0
    H: int = 0


@dataclass
class Job:
    job_id: int
    op: int
    machine_id: int
    machine_name: str
    recurso: str
    ordenacao: int
    _kf_macho: int
    resource_idx: int
    config: Optional[str]
    release_date: pd.Timestamp
    due_date: pd.Timestamp
    processing_minutes: float
    processing_slots: int
    release_date_slot: int
    due_date_slot: int


@dataclass
class JobExecution:
    machine_id: int
    machine_name: str
    recurso: str
    job_id: int
    op: int
    ordenacao: int
    sub_machine: int
    resource_id: int
    start_slot: int
    end_slot: int
    processing_slots: int
    release_date_slot: int
    due_date_slot: int
    start: Optional[datetime]
    end: Optional[datetime]
    setup_minutes: float
    processing_minutes: float
    tardiness_minutes: float
    prev_job_id: Optional[int]
    prev_config: Optional[str]
    curr_config: Optional[str]


# ============================================================
# HELPERS
# ============================================================

def normalize_string(value) -> str:
    if pd.isna(value):
        return ""
    return unidecode(str(value)).lower().replace(" ", "")


def ensure_exists(path: Path, kind: str = "file") -> None:
    if kind == "file" and not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if kind == "dir" and not path.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {path}")


def safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value) or str(value).strip() == "":
            return default
        return int(float(value))
    except Exception:
        return default


def safe_int_ordenacao(raw, default: int = 100) -> int:
    try:
        v = int(float(raw)) if pd.notna(raw) and str(raw).strip() != "" else default
        return v
    except (TypeError, ValueError):
        return default


def get_hour_slot(hora_str: str, time_step: int = DEFAULT_TIME_STEP) -> int:
    hora = datetime.strptime(hora_str, "%H:%M")
    total_min = hora.hour * 60 + hora.minute
    return total_min // time_step


def get_interval_slots(
    init_time: str,
    end_time: str,
    time_step: int = DEFAULT_TIME_STEP,
    slots_per_day: int = SLOTS_PER_DAY_DEFAULT,
) -> Tuple[int, int]:
    start_slot = get_hour_slot(init_time, time_step)
    end_slot = get_hour_slot(end_time, time_step)
    if start_slot <= end_slot:
        return start_slot, end_slot
    return start_slot, slots_per_day + end_slot


# ============================================================
# LOADERS & DEMAND VALIDATION (alinhado com data_input_process.py)
# ============================================================

def parse_turnos_to_list(value) -> List[int]:
    if pd.isna(value):
        return []
    if value == "geral":
        return [0]
    return [int(x.strip()) for x in str(value).split(",") if x.strip().isdigit()]


def parse_turno_to_int(val) -> int:
    if val == "geral":
        return 0
    return int(val)


def load_aux_tables(
    model_config_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_exists(model_config_dir, kind="dir")

    machines_csv = model_config_dir / "brut_machine_information.csv"
    cap_csv = model_config_dir / "brut_recurso_time_capacity.csv"
    shifts_csv = model_config_dir / "brut_shifts.csv"
    setup_csv = model_config_dir / "setup.csv"
    setup_times_csv = model_config_dir / "setup_times.csv"

    for f in (machines_csv, cap_csv, shifts_csv, setup_csv, setup_times_csv):
        ensure_exists(f)

    machines = pd.read_csv(
        machines_csv,
        converters={
            "turnos": parse_turnos_to_list,
            "processo": normalize_string,
            "recurso": normalize_string,
        },
    )
    caps = pd.read_csv(cap_csv, converters={"recurso": normalize_string})
    shifts = pd.read_csv(shifts_csv, converters={"turno": parse_turno_to_int})
    setup = pd.read_csv(setup_csv)
    setup_times = pd.read_csv(setup_times_csv)

    return machines, caps, shifts, setup, setup_times


def load_demand(lote_dir: Path) -> pd.DataFrame:
    """
    Carrega a demanda exatamente como data_input_process.py:
    busca os arquivos Parquet em lote_dir/demanda (ou subpastas).
    """
    ensure_exists(lote_dir, kind="dir")

    demanda_dir = lote_dir / "demanda"
    parquet_files: List[Path] = []
    if demanda_dir.is_dir():
        parquet_files = sorted(demanda_dir.glob("*.parquet"))
    else:
        for sub in sorted(lote_dir.iterdir()):
            if sub.is_dir() and (sub / "demanda").is_dir():
                parquet_files.extend(sorted((sub / "demanda").glob("*.parquet")))
            elif sub.is_dir() and sub.name.isdigit():
                parquet_files.extend(sorted(sub.glob("*.parquet")))
        parquet_files.extend(sorted(lote_dir.glob("*.parquet")))
        parquet_files = sorted(set(parquet_files))

    if not parquet_files:
        raise FileNotFoundError(f"Nenhum parquet de demanda encontrado em {lote_dir}")

    logger.info(
        "Carregando %d arquivo(s) PARQUET de demanda em %s",
        len(parquet_files),
        lote_dir,
    )

    dfs = [pd.read_parquet(fp, engine="pyarrow") for fp in parquet_files]
    df = pd.concat(dfs, ignore_index=True)

    df = df.rename(
        columns={
            "Not_Before_Date": "not_before_date",
            "DeadLine": "deadline",
            "tempo_total": "Tempo Total (minutos)",
        }
    )

    df = df.assign(
        not_before_date=lambda d: pd.to_datetime(d["not_before_date"], errors="coerce"),
        deadline=lambda d: pd.to_datetime(d["deadline"], errors="coerce"),
        processo=lambda d: d["processo"].astype("string").map(normalize_string),
        recurso=lambda d: d["recurso"].astype("string").map(normalize_string),
    )
    df["machine_name"] = df["processo"] + "_" + df["recurso"]
    df["lateness"] = 0
    df["Status_Processed"] = ""

    return df


def validate_and_fix_demand(df: pd.DataFrame, day_start: pd.Timestamp) -> pd.DataFrame:
    """Mesmas regras de validação e ajuste de data_input_process.py."""
    mask_invalida = df["not_before_date"] > df["deadline"]
    if mask_invalida.any():
        df.loc[mask_invalida, "Status_Processed"] = "Erro Not before date > deadline"

    required_cols = [
        "not_before_date",
        "caixa",
        "processo",
        "recurso",
        "Tempo Total (minutos)",
        "deadline",
        "_kf_macho",
        "_kf_producao",
        "qtd_moldes",
    ]
    existing_req = [c for c in required_cols if c in df.columns]
    mask_missing = df[existing_req].isnull().any(axis=1)
    if mask_missing.any():
        df.loc[mask_missing, "Status_Processed"] = "ERRO dado faltando"

    mask_late = df["deadline"] < day_start
    if mask_late.any():
        df.loc[mask_late, "deadline"] = day_start
        df.loc[mask_late, "lateness"] = 1

    return df


def compute_business_days(day_start: pd.Timestamp) -> pd.DatetimeIndex:
    """
    Idêntico a data_input_process.py:
    Gera dias úteis (seg-sex) a partir de day_start até a sexta-feira da mesma semana.
    - Se day_start for sábado/domingo, começa na 2ª feira seguinte.
    - Inclui o próprio day_start se ele for dia útil.
    """
    day_start = pd.to_datetime(day_start)
    wd = day_start.weekday()  # 0=Mon ... 6=Sun

    start = day_start
    if wd == 4:
        end = start
    else:
        end = start + pd.offsets.Week(weekday=4)
    bday = CustomBusinessDay(weekmask="Mon Tue Wed Thu Fri")
    return pd.date_range(start=start, end=end, freq=bday, inclusive="both")


def filter_demand_by_horizon(
    demand_df: pd.DataFrame, business_days: pd.DatetimeIndex
) -> pd.DataFrame:
    """Idêntico a data_input_process.py: descarta jobs com not_before_date após o horizonte."""
    last_day = business_days[-1].normalize()
    mask = demand_df["not_before_date"].dt.normalize() > last_day
    if mask.any():
        demand_df.loc[mask, "Status_Processed"] = (
            "Erro not before posterior ao ultimo dia"
        )
    return demand_df


# ============================================================
# SHIFT WINDOWS, SLOTS & CAPACITY (alinhado com data_input_process.py)
# ============================================================

def _parse_hhmm(hhmm: str) -> time:
    return datetime.strptime(hhmm, "%H:%M").time()


def build_slots_and_windows_for_machine(
    shifts_df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    turnos: List[int],
    max_dia_minutes: float,
    time_step: int = DEFAULT_TIME_STEP,
    slots_per_day: int = SLOTS_PER_DAY_DEFAULT,
) -> Tuple[
    List[int],
    List[int],
    List[int],
    Dict[pd.Timestamp, List[Tuple[datetime, datetime]]],
    Dict[pd.Timestamp, float],
]:
    """
    Constrói exatamente os mesmos `start_slots`, `last_slot_day` e `next_start_slots`
    que `data_input_process.py` + `ReadInstance::parse_next_start_slots` (heurística C++),
    além das janelas diárias truncadas pelo mesmo limite `cap`.
    """
    count_time_slots = len(business_days) * slots_per_day
    slots_valid_machine: set[int] = set()

    for count_day, day in enumerate(business_days):
        day_name = WORK_DAYS[day.weekday()]
        start_slot_day = count_day * slots_per_day
        day_shifts = shifts_df.loc[shifts_df["dia"] == day_name]
        machine_shifts = day_shifts[day_shifts["turno"].isin(turnos)]

        for _, row in machine_shifts.iterrows():
            s1, e1 = get_interval_slots(
                row["inicio"], row["intervalo_inicio"], time_step, slots_per_day
            )
            s2, e2 = get_interval_slots(
                row["intervalo_fim"], row["fim"], time_step, slots_per_day
            )
            for slot in range(start_slot_day + s1, start_slot_day + e1):
                if slot < count_time_slots:
                    slots_valid_machine.add(slot)
            for slot in range(start_slot_day + s2, start_slot_day + e2):
                if slot < count_time_slots:
                    slots_valid_machine.add(slot)

    start_slots_sorted = sorted(slots_valid_machine)
    process_max_slots = int(float(max_dia_minutes) // time_step)

    last_slot_day: List[int] = []
    start_slots_filtered: List[int] = []
    daily_windows: Dict[pd.Timestamp, List[Tuple[datetime, datetime]]] = {}
    daily_capacity: Dict[pd.Timestamp, float] = {}

    for count_day, day in enumerate(business_days):
        start_slot_day = count_day * slots_per_day
        end_slot_day = start_slot_day + slots_per_day
        todays_slots = [
            s for s in start_slots_sorted if start_slot_day <= s < end_slot_day
        ]
        last_valid = todays_slots[-1] if todays_slots else start_slot_day
        cap = min(last_valid, start_slot_day + process_max_slots)
        last_slot_day.append(cap)
        day_filtered = [s for s in todays_slots if s <= cap]
        start_slots_filtered.extend(day_filtered)

        # Converte os blocos contíguos de slots do dia em janelas datetime
        day_norm = day.normalize()
        day_base_dt = day_norm.to_pydatetime()
        windows: List[Tuple[datetime, datetime]] = []
        if day_filtered:
            seg_start = day_filtered[0]
            prev_s = day_filtered[0]
            for s in day_filtered[1:]:
                if s == prev_s + 1:
                    prev_s = s
                else:
                    w_a = day_base_dt + timedelta(minutes=(seg_start - start_slot_day) * time_step)
                    w_b = day_base_dt + timedelta(minutes=(prev_s + 1 - start_slot_day) * time_step)
                    windows.append((w_a, w_b))
                    seg_start = s
                    prev_s = s
            w_a = day_base_dt + timedelta(minutes=(seg_start - start_slot_day) * time_step)
            w_b = day_base_dt + timedelta(minutes=(prev_s + 1 - start_slot_day) * time_step)
            windows.append((w_a, w_b))

        daily_windows[day_norm] = windows
        daily_capacity[day_norm] = float(len(day_filtered) * time_step)

    H = start_slots_filtered[-1] if start_slots_filtered else 0
    next_start_slots = [H + 1] * (H + 2)
    idx = 0
    n_slots = len(start_slots_filtered)
    for t in range(H + 1):
        while idx < n_slots and start_slots_filtered[idx] < t:
            idx += 1
        if idx < n_slots:
            next_start_slots[t] = start_slots_filtered[idx]
        else:
            next_start_slots[t] = H + 1

    return (
        start_slots_filtered,
        last_slot_day,
        next_start_slots,
        daily_windows,
        daily_capacity,
    )


# ============================================================
# MACHINES, SETUPS & JOBS (alinhado com data_input_process.py)
# ============================================================

def build_target_machines(
    demand_df: pd.DataFrame,
    machines_df: pd.DataFrame,
    caps_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    only_machines: Optional[Tuple[str, ...]] = None,
) -> List[MachineInfo]:
    """
    Constrói a lista de máquinas seguindo a mesma ordem e IDs (`machine_id`)
    de `SchedulingInputBuilder.build_machines_information` em `data_input_process.py`.
    """
    machines: List[MachineInfo] = []
    index_machine = 0

    for process in demand_df["processo"].unique():
        recursos = (
            demand_df.loc[demand_df["processo"] == process, "recurso"]
            .unique()
            .tolist()
        )

        for recurso_type in recursos:
            machine_name = f"{process}_{recurso_type}"

            mi_rows = machines_df.query("recurso == @recurso_type")
            if mi_rows.empty:
                continue
            job_capacity = int(mi_rows.iloc[0]["maximo_caixas"])

            current_shifts_df = machines_df.query("processo == @process")
            if current_shifts_df.shape[0] > 1:
                turnos = machines_df.loc[
                    machines_df["recurso"] == recurso_type, "turnos"
                ].to_list()[0]
            else:
                turnos = current_shifts_df["turnos"].to_list()[0]

            caps_rows = caps_df.query("recurso == @recurso_type")
            if caps_rows.empty:
                continue

            max_dia = float(caps_rows["max_dia"].iloc[0])
            oee = float(str(caps_rows["oee"].iloc[0]).rstrip("%")) / 100.0

            (
                start_slots,
                last_slot_day,
                next_start_slots,
                daily_windows,
                daily_capacity,
            ) = build_slots_and_windows_for_machine(
                shifts_df=shifts_df,
                business_days=business_days,
                turnos=turnos,
                max_dia_minutes=max_dia,
            )

            first_slot = start_slots[0] if start_slots else 0
            H = start_slots[-1] if start_slots else 0

            if only_machines is None or any(tok in machine_name for tok in only_machines):
                machines.append(
                    MachineInfo(
                        machine_id=index_machine,
                        machine_name=machine_name,
                        processo=str(process),
                        recurso=str(recurso_type),
                        job_capacity=job_capacity,
                        oee=oee,
                        max_dia_minutes=max_dia,
                        turnos=turnos,
                        daily_capacity=daily_capacity,
                        daily_windows=daily_windows,
                        last_slot_day=last_slot_day,
                        start_slots=start_slots,
                        next_start_slots=next_start_slots,
                        first_slot=first_slot,
                        H=H,
                    )
                )

            index_machine += 1

    return machines


def build_kp_macho_data(
    setup_df: pd.DataFrame,
    machines: List[MachineInfo],
    demand_df: pd.DataFrame,
) -> Dict[Tuple[int, str], Dict]:
    """
    Mapeia (_kf_macho, machine_name) -> {"config": str, "not_setup": List[int]},
    incluindo o fallback `config="A"` para recursos sem entrada explícita em `setup.csv`
    (idêntico a `data_input_process.py`).
    """
    out: Dict[Tuple[int, str], Dict] = {}

    def find_machine_names(recurso_str: str) -> List[str]:
        r = normalize_string(recurso_str)
        return [m.machine_name for m in machines if m.recurso == r]

    for _, row in setup_df.iterrows():
        mnames = find_machine_names(str(row["recurso"]))
        if not mnames:
            continue

        macho_info = str(row["_kp_macho"]).replace(" ", "")
        macho_info = re.sub(r"[A-Za-z]+", "", macho_info)
        if not macho_info:
            continue

        if "/" in macho_info:
            parts = macho_info.split("/")
            for mname in mnames:
                for i, p in enumerate(parts):
                    try:
                        kp = int(p)
                    except ValueError:
                        continue
                    not_setup = []
                    for j, q in enumerate(parts):
                        if j == i:
                            continue
                        try:
                            not_setup.append(int(q))
                        except ValueError:
                            pass
                    out[(kp, mname)] = {
                        "config": str(row["configuracao"]),
                        "not_setup": not_setup,
                    }
        else:
            try:
                kp = int(macho_info)
            except ValueError:
                continue
            for mname in mnames:
                out[(kp, mname)] = {
                    "config": str(row["configuracao"]),
                    "not_setup": [],
                }

    # Fallback: recursos sem entrada em setup.csv -> config="A"
    recursos_com_setup = {
        normalize_string(str(row["recurso"])) for _, row in setup_df.iterrows()
    }
    for m in machines:
        if m.recurso in recursos_com_setup:
            continue
        kps = (
            demand_df.loc[demand_df["machine_name"] == m.machine_name, "_kf_macho"]
            .dropna()
            .unique()
        )
        for kp_raw in kps:
            kp = safe_int(kp_raw, default=-1)
            if kp >= 0 and (kp, m.machine_name) not in out:
                out[(kp, m.machine_name)] = {"config": "A", "not_setup": []}

    return out


def build_setup_time_data(
    setup_times_df: pd.DataFrame, machines: List[MachineInfo]
) -> Dict[Tuple[str, str, str], int]:
    out: Dict[Tuple[str, str, str], int] = {}

    def find_machine_names(recurso_str: str) -> List[str]:
        r = normalize_string(recurso_str)
        return [m.machine_name for m in machines if m.recurso == r]

    for _, row in setup_times_df.iterrows():
        for mname in find_machine_names(str(row["recurso"])):
            key = (str(row["de_config"]), str(row["para_config"]), mname)
            out[key] = int(row["setup_time_min"])

    return out


def get_setup_minutes_and_slots(
    prev_job: Optional[Job],
    curr_job: Job,
    machine: MachineInfo,
    kp_macho_data: Dict[Tuple[int, str], Dict],
    setup_time_data: Dict[Tuple[str, str, str], int],
    time_step: int = DEFAULT_TIME_STEP,
) -> Tuple[float, int]:
    """
    Calcula o tempo de setup entre dois jobs consecutivos seguindo a mesma regra
    de `data_input_process.py`:
    - Primeiro job da rota (`prev_job is None`) -> setup 0
    - Mesmo `_kf_macho` ou `_kf_macho` conjugado em `not_setup` -> setup 0
    - Caso contrário -> busca `(prev_config, curr_config, machine_name)` em `setup_times.csv`
      e converte para slots via `ceil(setup_min / time_step)`.
    """
    if prev_job is None:
        return 0.0, 0

    if prev_job._kf_macho == curr_job._kf_macho:
        return 0.0, 0

    prev_info = kp_macho_data.get((prev_job._kf_macho, machine.machine_name))
    if prev_info and curr_job._kf_macho in prev_info.get("not_setup", []):
        return 0.0, 0

    if prev_job.config is None or curr_job.config is None:
        return 0.0, 0

    key = (prev_job.config, curr_job.config, machine.machine_name)
    setup_min = float(setup_time_data.get(key, 0))
    setup_slots = math.ceil(setup_min / time_step) if setup_min > 0 else 0
    return setup_min, setup_slots


def build_jobs_for_machine(
    demand_df: pd.DataFrame,
    machine: MachineInfo,
    day_start: pd.Timestamp,
    kp_macho_data: Dict[Tuple[int, str], Dict],
    time_step: int = DEFAULT_TIME_STEP,
    slots_per_day: int = SLOTS_PER_DAY_DEFAULT,
) -> List[Job]:
    """
    Cria os jobs pendentes (`Status_Processed == ""`) da máquina com os mesmos
    campos (`processing_slots`, `release_date_slot`, `due_date_slot`, `resource_idx`)
    usados no `input.json` e na heurística C++, e ordena por `ordenacao` (regra dos operadores).
    """
    df = demand_df[
        (demand_df["machine_name"] == machine.machine_name)
        & (demand_df["Status_Processed"] == "")
    ].copy()
    if df.empty:
        return []

    # Mapeamento denso resource_id (_kf_macho) -> resource_idx (0..R-1) na ordem do input.json
    resource_idx_map: Dict[int, int] = {}
    jobs: List[Job] = []

    for _, row in df.iterrows():
        if pd.isna(row.get("not_before_date")) or pd.isna(row.get("deadline")):
            continue

        qm = pd.to_numeric(row.get("qtd_moldes"), errors="coerce")
        tc = pd.to_numeric(row.get("tempo_ciclo"), errors="coerce")
        if pd.isna(qm) or pd.isna(tc):
            continue

        jid = row.get("job_id")
        if pd.isna(jid):
            continue
        jid = int(jid)

        processing_minutes = float(qm) * float(tc) / float(machine.oee)
        processing_slots = math.ceil(processing_minutes / time_step)

        release_date = pd.Timestamp(row["not_before_date"])
        deadline_date = pd.Timestamp(row["deadline"])

        release_slot = int(
            max(0, (release_date - day_start).total_seconds() / 60 // time_step)
        )
        if deadline_date.date() == day_start.date():
            deadline_slot = slots_per_day - 1
        else:
            deadline_slot = int(
                max(0, (deadline_date - day_start).total_seconds() / 60 // time_step)
            )

        kp = safe_int(row.get("_kf_macho"), default=-1)
        if kp not in resource_idx_map:
            resource_idx_map[kp] = len(resource_idx_map)
        res_idx = resource_idx_map[kp]

        config = None
        if (kp, machine.machine_name) in kp_macho_data:
            config = kp_macho_data[(kp, machine.machine_name)]["config"]

        ordenacao = safe_int_ordenacao(row.get("ordenacao"), default=100)

        jobs.append(
            Job(
                job_id=jid,
                op=safe_int(row.get("_kf_producao")),
                machine_id=machine.machine_id,
                machine_name=machine.machine_name,
                recurso=machine.recurso,
                ordenacao=ordenacao,
                _kf_macho=kp,
                resource_idx=res_idx,
                config=config,
                release_date=release_date,
                due_date=deadline_date,
                processing_minutes=float(processing_minutes),
                processing_slots=int(processing_slots),
                release_date_slot=int(release_slot),
                due_date_slot=int(deadline_slot),
            )
        )

    # Regra da solução base (operadores): segue a coluna `ordenacao`
    jobs.sort(key=lambda j: (j.ordenacao, j.job_id))
    return jobs


# ============================================================
# SCHEDULER (Solução Base dos Operadores no mesmo horizonte da Heurística)
# ============================================================

def schedule_machine_baseline(
    machine: MachineInfo,
    jobs: List[Job],
    init_date: pd.Timestamp,
    kp_macho_data: Dict[Tuple[int, str], Dict],
    setup_time_data: Dict[Tuple[str, str, str], int],
    time_step: int = DEFAULT_TIME_STEP,
    big_setup_slots: int = BIG_SETUP_MINUTES // DEFAULT_TIME_STEP,
) -> Tuple[List[JobExecution], dict]:
    """
    Agenda os jobs na sequência definida pelos operadores (`ordenacao`),
    respeitando exatamente os `start_slots`, `first_slot` e horizonte `H` da heurística,
    e calcula a função objetivo (`objective_function`) com a mesma fórmula de `objective.cpp`.
    """
    t0 = perf_counter()
    M = max(1, machine.job_capacity)
    H = machine.H
    first_slot = machine.first_slot
    next_start_slots = machine.next_start_slots

    # Estado por sub-máquina paralela (0..M-1)
    last_completion_slot: List[int] = [0] * M
    prev_job_by_sub: List[Optional[Job]] = [None] * M
    routes_execs: List[List[JobExecution]] = [[] for _ in range(M)]
    unallocated_execs: List[JobExecution] = []

    # Intervalos de ocupação de recursos por sub-máquina para evitar/contar conflitos de big_setup
    # resource_intervals[resource_idx] = lista de (start, min(H+1, end + big_setup), sub_machine)
    resource_intervals: Dict[int, List[Tuple[int, int, int]]] = defaultdict(list)

    sum_tardiness_slots = 0.0
    sum_completion_slots = 0.0
    allocated_count = 0

    for job in jobs:
        # Escolhe a sub-máquina disponível mais cedo para iniciar este job,
        # respeitando que o mesmo recurso (_kf_macho) não pode ser usado simultaneamente
        # em outra sub-máquina (nem dentro da janela de big_setup em sub-máquina distinta).
        best_sub = 0
        best_start = H + 1
        best_setup_min = 0.0

        res_used = resource_intervals.get(job.resource_idx, [])

        for sub in range(M):
            setup_min, setup_slots = get_setup_minutes_and_slots(
                prev_job_by_sub[sub],
                job,
                machine,
                kp_macho_data,
                setup_time_data,
                time_step=time_step,
            )
            earliest = max(
                last_completion_slot[sub] + setup_slots,
                job.release_date_slot,
                first_slot,
            )
            # Se outra sub-máquina (j != sub) utilizou este mesmo recurso,
            # sub só pode iniciar após o término + big_setup daquela sub-máquina.
            if M > 1 and res_used:
                for _s_other, e_other_blocked, sub_other in res_used:
                    if sub_other != sub and earliest < e_other_blocked:
                        earliest = e_other_blocked

            cand_start = next_start_slots[earliest] if earliest <= H else H + 1
            if cand_start < best_start:
                best_start = cand_start
                best_sub = sub
                best_setup_min = setup_min

        if best_start > H:
            # Job não cabe no horizonte H -> fica não alocado (start=-1, end=-1, sub_machine=M)
            unallocated_execs.append(
                JobExecution(
                    machine_id=machine.machine_id,
                    machine_name=machine.machine_name,
                    recurso=machine.recurso,
                    job_id=job.job_id,
                    op=job.op,
                    ordenacao=job.ordenacao,
                    sub_machine=M,
                    resource_id=job.resource_idx,
                    start_slot=-1,
                    end_slot=-1,
                    processing_slots=job.processing_slots,
                    release_date_slot=job.release_date_slot,
                    due_date_slot=job.due_date_slot,
                    start=None,
                    end=None,
                    setup_minutes=0.0,
                    processing_minutes=job.processing_minutes,
                    tardiness_minutes=0.0,
                    prev_job_id=None,
                    prev_config=None,
                    curr_config=job.config,
                )
            )
            continue

        start_slot = best_start
        end_slot = start_slot + job.processing_slots
        prev_job = prev_job_by_sub[best_sub]

        start_dt = (init_date + timedelta(minutes=start_slot * time_step)).to_pydatetime()
        end_dt = (init_date + timedelta(minutes=end_slot * time_step)).to_pydatetime()

        tardiness_slots = max(0, end_slot - job.due_date_slot)
        tardiness_minutes = float(tardiness_slots * time_step)

        exec_item = JobExecution(
            machine_id=machine.machine_id,
            machine_name=machine.machine_name,
            recurso=machine.recurso,
            job_id=job.job_id,
            op=job.op,
            ordenacao=job.ordenacao,
            sub_machine=best_sub,
            resource_id=job.resource_idx,
            start_slot=start_slot,
            end_slot=end_slot,
            processing_slots=job.processing_slots,
            release_date_slot=job.release_date_slot,
            due_date_slot=job.due_date_slot,
            start=start_dt,
            end=end_dt,
            setup_minutes=best_setup_min,
            processing_minutes=job.processing_minutes,
            tardiness_minutes=tardiness_minutes,
            prev_job_id=(prev_job.job_id if prev_job else None),
            prev_config=(prev_job.config if prev_job else None),
            curr_config=job.config,
        )

        routes_execs[best_sub].append(exec_item)
        last_completion_slot[best_sub] = end_slot
        prev_job_by_sub[best_sub] = job

        allocated_count += 1
        sum_tardiness_slots += tardiness_slots
        sum_completion_slots += end_slot

        if M > 1:
            resource_intervals[job.resource_idx].append(
                (start_slot, min(H + 1, end_slot + big_setup_slots), best_sub)
            )

    # Calcula violações de recurso entre sub-máquinas paralelas (idêntico a rebuildResourceIntervals em objective.cpp)
    total_violations = 0
    if M > 1:
        for _, intervals in resource_intervals.items():
            if len(intervals) < 2:
                continue
            intervals_sorted = sorted(intervals, key=lambda x: (x[0], x[2], x[1]))
            last_end = [-1] * M
            violated_pairs: set[Tuple[int, int]] = set()
            for s, e, k in intervals_sorted:
                for j in range(M):
                    if j == k or last_end[j] <= s:
                        continue
                    pair = (min(k, j), max(k, j))
                    if pair not in violated_pairs:
                        violated_pairs.add(pair)
                        total_violations += 1
                if e > last_end[k]:
                    last_end[k] = e

    N = len(jobs)
    unallocated_count = N - allocated_count
    weight_not_allocated = float(N * H + 1)
    epsilon = 1.0 / weight_not_allocated
    resource_violation_penalty = float(N * weight_not_allocated + 1.0)

    objective_function = (
        sum_tardiness_slots
        + epsilon * sum_completion_slots
        + unallocated_count * weight_not_allocated
        + (total_violations * resource_violation_penalty if M > 1 else 0.0)
    )

    solve_time_seconds = perf_counter() - t0

    all_execs: List[JobExecution] = []
    for sub in range(M):
        all_execs.extend(routes_execs[sub])
    all_execs.extend(unallocated_execs)

    machine_json_entry = {
        "count_jobs_not_allocated": unallocated_count,
        "jobs": [
            {
                "due_date_slot": ex.due_date_slot,
                "end": ex.end_slot,
                "job_id": ex.job_id,
                "processing_slots": ex.processing_slots,
                "release_date_slot": ex.release_date_slot,
                "resource_id": ex.resource_id,
                "start": ex.start_slot,
                "sub_machine": ex.sub_machine,
            }
            for ex in all_execs
        ],
        "machine_id": machine.machine_id,
        "objective_function": objective_function,
        "solve_time_seconds": solve_time_seconds,
    }

    return all_execs, machine_json_entry


# ============================================================
# METRICS
# ============================================================

def compute_metrics(executions: List[JobExecution]) -> dict:
    allocated = [e for e in executions if e.start_slot >= 0 and e.start is not None]
    if not allocated:
        return {
            "jobs_total": 0,
            "jobs_late": 0,
            "total_tardiness_minutes": 0.0,
            "makespan_days": 0,
            "total_setup_minutes": 0.0,
            "total_processing_minutes": 0.0,
            "start_datetime": pd.NaT,
            "end_datetime": pd.NaT,
        }

    start = min(e.start for e in allocated)
    end = max(e.end for e in allocated)

    makespan_days = (end.date() - start.date()).days + 1
    total_processing = sum(e.processing_minutes for e in allocated)
    total_setup = sum(e.setup_minutes for e in allocated)

    return {
        "jobs_total": len(allocated),
        "jobs_late": sum(1 for e in allocated if e.tardiness_minutes > 1e-9),
        "total_tardiness_minutes": sum(e.tardiness_minutes for e in allocated),
        "makespan_days": int(makespan_days),
        "total_processing_minutes": float(total_processing + total_setup),
        "total_setup_minutes": float(total_setup),
        "start_datetime": start,
        "end_datetime": end,
    }


def save_metrics_to_excel(rows: List[dict], excel_path: Path) -> None:
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows)

    for col in ["day_start", "start_datetime", "end_datetime"]:
        if col in df_new.columns:
            df_new[col] = pd.to_datetime(df_new[col], errors="coerce").dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

    try:
        if excel_path.exists():
            df_old = pd.read_excel(excel_path)
            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new
        df.to_excel(excel_path, index=False)
        logger.info("Métricas salvas em: %s", excel_path)
    except ModuleNotFoundError:
        csv_fallback = excel_path.with_suffix(".csv")
        df_new.to_csv(csv_fallback, index=False)
        logger.info("Métricas salvas em CSV (openpyxl ausente): %s", csv_fallback)


# ============================================================
# CLI / MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Solução Base dos Operadores (Case AFM) alinhada ao horizonte da Heurística."
    )
    p.add_argument(
        "--base-data",
        type=Path,
        required=True,
        help="Pasta do lote (ex: data/raw/01122025/94) OU pasta com vários lotes.",
    )
    p.add_argument(
        "--model-config-dir",
        type=Path,
        default=BASE_DIR / "model_config",
        help="Pasta com parâmetros CSVs (default: Case_AFM-main/model_config).",
    )
    p.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Caminho opcional para salvar o JSON no mesmo formato de output_heuristic.json.",
    )
    p.add_argument(
        "--output-excel",
        type=Path,
        default=RESULT_DIR / "baseline_metrics.xlsx",
        help="Excel de métricas.",
    )
    p.add_argument(
        "--all-machines",
        action="store_true",
        default=True,
        help="Processa todas as máquinas da instância (padrão: True).",
    )
    return p.parse_args()


def parse_day_start_from_lote(lote_dir: Path) -> pd.Timestamp:
    """
    Extrai a data do lote no formato DDMMYYYY (seja de `<DDMMYYYY>` ou `<DDMMYYYY>/<status>`)
    e retorna `YYYY-MM-DD 00:00`, idêntico ao `day_start` de `data_input_process.py`.
    """
    for candidate in (lote_dir.name, lote_dir.parent.name):
        if re.fullmatch(r"\d{8}", candidate):
            base_date = datetime.strptime(candidate, "%d%m%Y")
            return pd.Timestamp(base_date)
    raise ValueError(
        f"Não foi possível identificar data DDMMYYYY a partir do caminho: {lote_dir}"
    )


def discover_lotes(base_data: Path) -> List[Path]:
    """
    Descobre lotes válidos tanto em `data/raw/<DDMMYYYY>/<status>` quanto em `<DDMMYYYY>`.
    """
    if (base_data / "demanda").is_dir():
        return [base_data]

    # Se base_data for uma pasta de data <DDMMYYYY> contendo subpastas <status>/demanda
    status_dirs = [
        p for p in sorted(base_data.iterdir())
        if p.is_dir() and (p / "demanda").is_dir()
    ]
    if status_dirs:
        return status_dirs

    # Se base_data for data/raw contendo várias datas <DDMMYYYY>
    lotes: List[Path] = []
    for p in sorted(base_data.iterdir()):
        if not p.is_dir() or p.name == "model_config" or not re.fullmatch(r"\d{8}", p.name):
            continue
        sub_status = [
            s for s in sorted(p.iterdir())
            if s.is_dir() and (s / "demanda").is_dir()
        ]
        if sub_status:
            lotes.extend(sub_status)
        else:
            lotes.append(p)
    return lotes


def main() -> None:
    args = parse_args()
    lotes = discover_lotes(args.base_data)
    logger.info("Lotes encontrados: %d", len(lotes))

    machines_df, caps_df, shifts_df, setup_df, setup_times_df = load_aux_tables(
        args.model_config_dir
    )
    metrics_rows: List[dict] = []

    for lote_dir in lotes:
        lote_label = (
            f"{lote_dir.parent.name}/{lote_dir.name}"
            if re.fullmatch(r"\d{8}", lote_dir.parent.name)
            else lote_dir.name
        )
        logger.info("Processando lote: %s", lote_label)

        day_start = parse_day_start_from_lote(lote_dir)
        business_days = compute_business_days(day_start)
        init_date = pd.Timestamp(business_days[0])

        demand_df = load_demand(lote_dir)
        demand_df = validate_and_fix_demand(demand_df, day_start)
        demand_df = filter_demand_by_horizon(demand_df, business_days)
        demand_df = demand_df.reset_index(drop=True)
        demand_df["job_id"] = np.arange(len(demand_df), dtype=int)

        machines = build_target_machines(
            demand_df=demand_df,
            machines_df=machines_df,
            caps_df=caps_df,
            shifts_df=shifts_df,
            business_days=business_days,
            only_machines=None,
        )

        kp_macho_data = build_kp_macho_data(setup_df, machines, demand_df)
        setup_time_data = build_setup_time_data(setup_times_df, machines)

        machines_scheduling_json: List[dict] = []

        for m in machines:
            jobs = build_jobs_for_machine(
                demand_df=demand_df,
                machine=m,
                day_start=day_start,
                kp_macho_data=kp_macho_data,
            )
            jobs_demand_total = len(jobs)

            execs, machine_json_entry = schedule_machine_baseline(
                machine=m,
                jobs=jobs,
                init_date=init_date,
                kp_macho_data=kp_macho_data,
                setup_time_data=setup_time_data,
            )
            machines_scheduling_json.append(machine_json_entry)

            met = compute_metrics(execs)
            logger.info(
                "[%s | id=%d %s] H=%d | Jobs=%d | Alocados=%d | NãoAlocados=%d | FO_base=%.6f",
                lote_label,
                m.machine_id,
                m.machine_name,
                m.H,
                jobs_demand_total,
                met["jobs_total"],
                machine_json_entry["count_jobs_not_allocated"],
                machine_json_entry["objective_function"],
            )

            metrics_rows.append(
                {
                    "lote": lote_label,
                    "day_start": day_start,
                    "H": m.H,
                    "machine_id": m.machine_id,
                    "machine_name": m.machine_name,
                    "recurso": m.recurso,
                    "jobs_demand_total": jobs_demand_total,
                    "jobs_unattended": machine_json_entry["count_jobs_not_allocated"],
                    "objective_function": machine_json_entry["objective_function"],
                    "solution": "baseline",
                    **met,
                }
            )

        output_payload = {"machines_scheduling": machines_scheduling_json}

        if args.output_json is not None and len(lotes) == 1:
            json_path = args.output_json
        else:
            json_path = RESULT_DIR / lote_label.replace("/", "_") / "output_baseline.json"

        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=4, ensure_ascii=False)
        logger.info("JSON da solução base salvo em: %s", json_path)

    if metrics_rows:
        save_metrics_to_excel(metrics_rows, args.output_excel)


if __name__ == "__main__":
    main()
