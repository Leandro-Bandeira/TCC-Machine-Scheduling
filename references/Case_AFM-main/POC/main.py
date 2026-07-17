from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from unidecode import unidecode


# ============================================================
# LOGGING
# ============================================================

LOG_FMT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("baseline-two-machines")


# ============================================================
# CONFIG
# ============================================================

RESULT_DIR = Path("POC/results_baseline")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

WORK_DAYS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

# Apenas duas máquinas
TARGET_MACHINE_CONTAINS = ("_vibrado", "_sopradora")


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class MachineInfo:
    machine_name: str
    processo: str
    recurso: str
    job_capacity: int
    oee: float
    max_dia_minutes: float
    turnos: List[int]
    daily_capacity: Dict[pd.Timestamp, float]
    daily_windows: Dict[pd.Timestamp, List[Tuple[datetime, datetime]]]


@dataclass
class Job:
    job_id: int
    op: int
    machine_name: str
    recurso: str
    ordenacao: int
    _kf_macho: int
    config: Optional[str]
    release_date: pd.Timestamp
    due_date: pd.Timestamp
    processing_minutes: float


@dataclass
class JobExecution:
    machine_name: str
    recurso: str
    job_id: int
    op: int
    ordenacao: int
    start: datetime
    end: datetime
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


def normalize_demand_df(df: pd.DataFrame) -> pd.DataFrame:
    # garante colunas mínimas esperadas
    required = {"processo", "recurso"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Demanda sem colunas obrigatórias {missing}. Colunas disponíveis: {list(df.columns)}")

    df["processo"] = df["processo"].astype(str).map(normalize_string)
    df["recurso"] = df["recurso"].astype(str).map(normalize_string)
    df["machine_name"] = df["processo"] + "_" + df["recurso"]

    # datas
    if "not_before_date" in df.columns:
        df["not_before_date"] = pd.to_datetime(df["not_before_date"], errors="coerce")
    else:
        df["not_before_date"] = pd.NaT

    if "deadline" in df.columns:
        df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    else:
        df["deadline"] = pd.NaT

    return df


def _demand_parquet_files(lote_dir: Path) -> List[Path]:
    """
    Regra correta: demanda deve estar em lote_dir/demanda.
    Evita incluir parquets de outputs (ex.: job_scheduling_output, dashboards, etc.).
    """
    demanda_dir = lote_dir / "demanda"
    if demanda_dir.exists() and demanda_dir.is_dir():
        files = list(demanda_dir.rglob("*.parquet"))
        return sorted(files)

    # fallback: se não existir /demanda, não varre o lote inteiro (isso causou sua contagem errada)
    return []


def _dedupe_demand(df: pd.DataFrame) -> pd.DataFrame:
    """
    Evita duplicar jobs quando a demanda vem particionada em múltiplos parquets
    ou quando há re-export. Usa a melhor chave disponível.
    """
    # escolha de chave estável: use as colunas que existirem
    preferred_keys = [
        ["_kf_producao", "_kf_macho", "ordenacao", "processo", "recurso", "not_before_date", "deadline"],
        ["_kf_producao", "_kf_macho", "processo", "recurso", "not_before_date", "deadline"],
        ["_kf_producao", "_kf_macho", "processo", "recurso"],
    ]
    for keys in preferred_keys:
        if all(k in df.columns for k in keys):
            before = len(df)
            df = df.drop_duplicates(subset=keys, keep="first").copy()
            after = len(df)
            if after != before:
                logger.info("[DEDUPE] Removidos %d duplicados usando keys=%s", before - after, keys)
            return df

    # sem chave suficiente: não deduplica
    return df


# ============================================================
# LOADERS
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


def load_aux_tables(model_config_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    ensure_exists(lote_dir, kind="dir")

    parquet_files: List[Path] = []

    # subpastas numéricas (lote_gap)
    for sub in lote_dir.iterdir():
        if sub.is_dir() and sub.name.isdigit():
            parquet_files.extend(sub.glob("*.parquet"))

    # parquets direto no lote
    parquet_files.extend(lote_dir.glob("*.parquet"))

    parquet_files = sorted(set(parquet_files))

    if not parquet_files:
        raise FileNotFoundError(
            f"Nenhum parquet de demanda encontrado em {lote_dir}"
        )

    logger.info(
        "Carregando %d arquivo(s) PARQUET de demanda em %s",
        len(parquet_files),
        lote_dir.name,
    )

    dfs = [pd.read_parquet(fp, engine="pyarrow") for fp in parquet_files]
    df = pd.concat(dfs, ignore_index=True)

    # 🔒 normalizações textuais e datas
    df = normalize_demand_df(df)

    # ===============================
    # GARANTIA ABSOLUTA DE job_id
    # ===============================
    df = df.reset_index(drop=True)
    df["job_id"] = np.arange(len(df), dtype=int)

    logger.info(
        "job_id criado: %d jobs carregados para %s",
        len(df),
        lote_dir.name,
    )

    return df



def compute_business_days(day_start: pd.Timestamp, n_days: int = 5) -> pd.DatetimeIndex:
    day_start = pd.to_datetime(day_start).normalize()
    business_days = []
    current = day_start
    while len(business_days) < n_days:
        if current.weekday() < 5:
            business_days.append(current)
        current += pd.Timedelta(days=1)
    return pd.to_datetime(business_days)


# ============================================================
# SHIFT WINDOWS + CAPACITY
# ============================================================

def _parse_hhmm(hhmm: str) -> time:
    return datetime.strptime(hhmm, "%H:%M").time()


def build_daily_windows_for_machine(
    shifts_df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    turnos: List[int],
) -> Dict[pd.Timestamp, List[Tuple[datetime, datetime]]]:
    out: Dict[pd.Timestamp, List[Tuple[datetime, datetime]]] = {}

    for day in business_days:
        day_name = WORK_DAYS[day.weekday()]
        day_shifts = shifts_df[shifts_df["dia"] == day_name]
        machine_shifts = day_shifts[day_shifts["turno"].isin(turnos)]

        windows: List[Tuple[datetime, datetime]] = []
        for _, row in machine_shifts.iterrows():
            s1, e1 = _parse_hhmm(row["inicio"]), _parse_hhmm(row["intervalo_inicio"])
            s2, e2 = _parse_hhmm(row["intervalo_fim"]), _parse_hhmm(row["fim"])

            w1 = (datetime.combine(day.to_pydatetime().date(), s1),
                  datetime.combine(day.to_pydatetime().date(), e1))
            w2 = (datetime.combine(day.to_pydatetime().date(), s2),
                  datetime.combine(day.to_pydatetime().date(), e2))

            if w1[1] > w1[0]:
                windows.append(w1)
            if w2[1] > w2[0]:
                windows.append(w2)

        windows.sort(key=lambda x: x[0])
        out[day.normalize()] = windows  # normalize aqui para chave consistente

    return out


def compute_daily_capacity_minutes(
    daily_windows: Dict[pd.Timestamp, List[Tuple[datetime, datetime]]],
    max_dia_minutes: float,
) -> Dict[pd.Timestamp, float]:
    out = {}
    for day, windows in daily_windows.items():
        total = 0.0
        for a, b in windows:
            total += (b - a).total_seconds() / 60.0
        out[day] = float(total if total < max_dia_minutes else max_dia_minutes)
    return out


# ============================================================
# SETUP (mantido como você definiu; A->A deve existir)
# ============================================================

def build_kp_macho_data(setup_df: pd.DataFrame, machines: List[MachineInfo]) -> Dict[Tuple[int, str], Dict]:
    out: Dict[Tuple[int, str], Dict] = {}

    def find_machine_name(recurso_str: str) -> Optional[str]:
        r = normalize_string(recurso_str)
        for m in machines:
            if m.recurso == r:
                return m.machine_name
        return None

    for _, row in setup_df.iterrows():
        mname = find_machine_name(str(row["recurso"]))
        if mname is None:
            continue

        macho_info = str(row["_kp_macho"]).replace(" ", "")
        macho_info = re.sub(r"[A-Za-z]+", "", macho_info)
        if not macho_info:
            continue

        if "/" in macho_info:
            parts = macho_info.split("/")
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
                out[(kp, mname)] = {"config": row["configuracao"], "not_setup": not_setup}
        else:
            try:
                kp = int(macho_info)
            except ValueError:
                continue
            out[(kp, mname)] = {"config": row["configuracao"], "not_setup": []}

    return out


def build_setup_time_data(setup_times_df: pd.DataFrame, machines: List[MachineInfo]) -> Dict[Tuple[str, str, str], int]:
    out: Dict[Tuple[str, str, str], int] = {}

    def find_machine_name(recurso_str: str) -> Optional[str]:
        r = normalize_string(recurso_str)
        for m in machines:
            if m.recurso == r:
                return m.machine_name
        return None

    for _, row in setup_times_df.iterrows():
        mname = find_machine_name(str(row["recurso"]))
        if mname is None:
            continue
        key = (str(row["de_config"]), str(row["para_config"]), mname)
        out[key] = int(row["setup_time_min"])

    return out


def get_setup_minutes(
    prev_job: Optional[Job],
    curr_job: Job,
    machine: MachineInfo,
    setup_time_data: Dict[Tuple[str, str, str], int],
) -> float:
    """
    Setup sempre sequencial.
    A→A também consome setup.
    """

    if prev_job is None:
        return 0.0

    if prev_job.config is None or curr_job.config is None:
        logger.warning(
            "[SETUP] Config ausente: prev=%s curr=%s job_id=%s",
            prev_job.config,
            curr_job.config,
            curr_job.job_id,
        )
        return 0.0

    key = (prev_job.config, curr_job.config, machine.machine_name)

    if key not in setup_time_data:
        logger.warning(
            "[SETUP] Tempo não mapeado: %s → %s (%s)",
            prev_job.config,
            curr_job.config,
            machine.machine_name,
        )
        return 0.0

    return float(setup_time_data[key])



# ============================================================
# MACHINES + JOBS
# ============================================================

def build_target_machines(
    demand_df: pd.DataFrame,
    machines_df: pd.DataFrame,
    caps_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
) -> List[MachineInfo]:
    machines: List[MachineInfo] = []

    recursos_target = sorted(
        demand_df["recurso"].dropna().astype(str).map(normalize_string).unique().tolist()
    )

    for recurso in recursos_target:
        df_r = demand_df[demand_df["recurso"] == recurso]
        if df_r.empty:
            continue

        processo = str(df_r["processo"].iloc[0])
        machine_name = f"{processo}_{recurso}"

        df_m = machines_df[machines_df["recurso"] == recurso]
        if df_m.empty:
            logger.warning("Recurso %s não encontrado em brut_machine_information. Pulando.", recurso)
            continue

        job_capacity = int(df_m.iloc[0]["maximo_caixas"])

        current_shifts_df = machines_df[machines_df["processo"] == processo]
        if current_shifts_df.shape[0] > 1:
            turnos = machines_df.loc[machines_df["recurso"] == recurso, "turnos"].to_list()[0]
        else:
            turnos = current_shifts_df["turnos"].to_list()[0]

        max_dia = float(caps_df[caps_df["recurso"] == recurso]["max_dia"].iloc[0])
        oee = float(str(caps_df[caps_df["recurso"] == recurso]["oee"].iloc[0]).replace("%", "")) / 100.0

        daily_windows = build_daily_windows_for_machine(shifts_df, business_days, turnos)
        daily_capacity = compute_daily_capacity_minutes(daily_windows, max_dia)

        machines.append(
            MachineInfo(
                machine_name=machine_name,
                processo=processo,
                recurso=recurso,
                job_capacity=job_capacity,
                oee=oee,
                max_dia_minutes=max_dia,
                turnos=turnos,
                daily_capacity=daily_capacity,
                daily_windows=daily_windows,
            )
        )

    return machines


def safe_int_ordenacao(raw, default: int = 100) -> int:
    try:
        v = int(raw) if str(raw).strip() != "" else default
        return v
    except (TypeError, ValueError):
        return default


def build_jobs_for_machine(
    demand_df: pd.DataFrame,
    machine: MachineInfo,
    business_days: pd.DatetimeIndex,
    day_start: pd.Timestamp,
    kp_macho_data: Dict[Tuple[int, str], Dict],
    setup_time_data: Dict[Tuple[str, str, str], int],
) -> List[Job]:
    df = demand_df[demand_df["machine_name"] == machine.machine_name].copy()
    if df.empty:
        return []

    last_day = business_days[-1]
    jobs: List[Job] = []

    for _, row in df.iterrows():
        release_date = pd.Timestamp(row.get("not_before_date"))
        deadline_date = pd.Timestamp(row.get("deadline"))

        if pd.isna(release_date):
            release_date = day_start
        if pd.isna(deadline_date):
            deadline_date = last_day
        if deadline_date.date() > last_day.date():
            deadline_date = last_day

        try:
            processing_minutes = float(row["qtd_moldes"]) * float(row["tempo_ciclo"]) / float(machine.oee)
        except Exception:
            continue

        try:
            kp = int(row["_kf_macho"])
        except Exception:
            kp = -1

        config = None
        if (kp, machine.machine_name) in kp_macho_data:
            config = kp_macho_data[(kp, machine.machine_name)]["config"]

        ordenacao = safe_int_ordenacao(row.get("ordenacao"), default=100)

        jobs.append(
            Job(
                job_id=int(row["job_id"]),
                op=int(row["_kf_producao"]),
                machine_name=machine.machine_name,
                recurso=machine.recurso,
                ordenacao=ordenacao,
                _kf_macho=int(row["_kf_macho"]) if pd.notna(row["_kf_macho"]) else -1,
                config=config,
                release_date=release_date,
                due_date=deadline_date,
                processing_minutes=float(processing_minutes),
            )
        )

    jobs.sort(key=lambda j: j.ordenacao)
    return jobs


# ============================================================
# SCHEDULER
# ============================================================

def snap_to_next_window_start(t: datetime, windows: List[Tuple[datetime, datetime]]) -> Optional[datetime]:
    for a, b in windows:
        if a <= t < b:
            return t
        if t < a:
            return a
    return None


def consume_work_minutes(
    start: datetime,
    minutes: float,
    day: pd.Timestamp,
    machine: MachineInfo,
) -> Tuple[datetime, float]:
    remaining = float(minutes)
    windows = machine.daily_windows.get(day.normalize(), [])

    t = start
    consumed = 0.0

    while remaining > 1e-9:
        t2 = snap_to_next_window_start(t, windows)
        if t2 is None:
            break
        t = t2

        current_window = None
        for a, b in windows:
            if a <= t < b:
                current_window = (a, b)
                break
        if current_window is None:
            break

        a, b = current_window
        available = (b - t).total_seconds() / 60.0
        if available <= 0:
            t = b
            continue

        delta = min(available, remaining)
        t = t + timedelta(minutes=delta)
        remaining -= delta
        consumed += delta

    return t, consumed


def schedule_machine_baseline_fast(
    machine: MachineInfo,
    jobs: List[Job],
    business_days: pd.DatetimeIndex,
    kp_macho_data: Dict[Tuple[int, str], Dict],
    setup_time_data: Dict[Tuple[str, str, str], int],
) -> List[JobExecution]:
    executions: List[JobExecution] = []
    used_by_day = {d.normalize(): 0.0 for d in business_days}
    current_day = business_days[0].normalize()
    prev_job: Optional[Job] = None

    for job in jobs:
        release_day = job.release_date.normalize()
        day = max(current_day, release_day) if release_day in used_by_day else current_day
        setup = get_setup_minutes(prev_job, job, machine, setup_time_data)

        total = setup + job.processing_minutes

        # acha um dia que cabe
        while True:
            cap = machine.daily_capacity.get(day, 0.0)
            used = used_by_day.get(day, 0.0)

            if used + total <= cap + 1e-9:
                break

            idx = list(business_days.normalize()).index(day)
            if idx + 1 >= len(business_days):
                # horizonte acabou -> não atende esse job e encerra
                return executions
            day = business_days[idx + 1].normalize()

        windows = machine.daily_windows.get(day, [])
        if not windows:
            continue

        start_dt = max(job.release_date.to_pydatetime(), windows[0][0] + timedelta(minutes=used_by_day[day]))

        # setup precisa caber inteiro no dia
        setup_end_dt = start_dt
        if setup > 0:
            setup_end_dt, setup_consumed = consume_work_minutes(start_dt, setup, day, machine)
            if setup_consumed + 1e-9 < setup:
                # empurra para próximo dia (sem agendar nada)
                idx = list(business_days.normalize()).index(day)
                if idx + 1 >= len(business_days):
                    return executions
                current_day = business_days[idx + 1].normalize()
                continue
            used_by_day[day] += setup_consumed

        # processamento precisa caber inteiro no dia
        
        proc_start_dt = setup_end_dt
        proc_end_dt, proc_consumed = consume_work_minutes(proc_start_dt, job.processing_minutes, day, machine)
        if proc_consumed + 1e-9 < job.processing_minutes:
            # não atende e encerra (regra consistente com "horizonte fixo")
            return executions
        used_by_day[day] += proc_consumed

        end_dt = proc_end_dt
        current_day = day

        tardiness = max(0.0, (pd.Timestamp(end_dt) - job.due_date).total_seconds() / 60.0)

        executions.append(
            JobExecution(
                machine_name=machine.machine_name,
                recurso=machine.recurso,
                job_id=job.job_id,
                op=job.op,
                ordenacao=job.ordenacao,
                start=start_dt,
                end=end_dt,
                setup_minutes=setup,
                processing_minutes=job.processing_minutes,
                tardiness_minutes=tardiness,
                prev_job_id=(prev_job.job_id if prev_job else None),
                prev_config=(prev_job.config if prev_job else None),
                curr_config=job.config,
            )
        )
        prev_job = job

    return executions


# ============================================================
# METRICS
# ============================================================

def compute_end_of_horizon(machine: MachineInfo, business_days: pd.DatetimeIndex) -> datetime:
    return max(w[1] for day in business_days for w in machine.daily_windows[day.normalize()])



def compute_metrics(executions: List[JobExecution]) -> dict:
    if not executions:
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

    start = min(e.start for e in executions)
    end = max(e.end for e in executions)

    makespan_days = (end.date() - start.date()).days + 1

    total_processing = sum(e.processing_minutes for e in executions)
    total_setup = sum(e.setup_minutes for e in executions)

    return {
        "jobs_total": len(executions),
        "jobs_late": sum(1 for e in executions if e.tardiness_minutes > 1e-9),
        "total_tardiness_minutes": sum(e.tardiness_minutes for e in executions),
        "makespan_days": int(makespan_days),
        "total_processing_minutes": float(total_processing + total_setup),
        "total_setup_minutes": float(total_setup),
        "start_datetime": start,
        "end_datetime": end,
    }
def compute_metrics_from_parquet_machine(
    df_machine: pd.DataFrame,
    machine_name: str,
    setup_time_data: Dict[Tuple[str, str, str], int],
) -> dict:

    df_ok = df_machine[df_machine["inicio"].notna()].copy()

    if df_ok.empty:
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

    df_ok["inicio"] = pd.to_datetime(df_ok["inicio"])
    df_ok["fim"] = pd.to_datetime(df_ok["fim"])
    df_ok["Deadline"] = pd.to_datetime(df_ok["Deadline"], errors="coerce")
    df_ok["tempo_processamento"] = pd.to_numeric(
        df_ok["tempo_processamento"], errors="coerce"
    ).fillna(0.0)

    start = df_ok["inicio"].min()
    end = df_ok["fim"].max()

    makespan_days = (end.date() - start.date()).days + 1

    jobs_late = (df_ok["fim"] > df_ok["Deadline"]).sum()
    tardiness_minutes = (
        (df_ok["fim"] - df_ok["Deadline"])
        .dt.total_seconds()
        .clip(lower=0)
        .sum() / 60.0
    )

    # -------------------------
    # SETUP por sequência
    # -------------------------
    total_setup = 0.0

    if "sub_machine" in df_ok.columns:
        df_seq = df_ok.sort_values(["sub_machine", "inicio"])
        groups = df_seq.groupby("sub_machine", dropna=False)
    else:
        df_seq = df_ok.sort_values("inicio")
        groups = [(None, df_seq)]

    for _, g in groups:
        prev_config = None
        for _, row in g.iterrows():
            curr_config = row.get("config")
            if prev_config is not None and curr_config is not None:
                total_setup += setup_time_data.get(
                    (str(prev_config), str(curr_config), machine_name),
                    0
                )
            prev_config = curr_config

    total_processing = df_ok["tempo_processamento"].sum() + total_setup

    return {
        "jobs_total": int(len(df_ok)),
        "jobs_late": int(jobs_late),
        "total_tardiness_minutes": float(tardiness_minutes),
        "makespan_days": int(makespan_days),
        "total_setup_minutes": float(total_setup),
        "total_processing_minutes": float(total_processing),
        "start_datetime": start,
        "end_datetime": end,
    }




def save_metrics_to_excel(rows: List[dict], excel_path: Path) -> None:
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows)

    for col in ["day_start", "start_datetime", "end_datetime"]:
        if col in df_new.columns:
            df_new[col] = pd.to_datetime(df_new[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

    if excel_path.exists():
        df_old = pd.read_excel(excel_path)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_excel(excel_path, index=False)
    logger.info("Métricas salvas em: %s", excel_path)


# ============================================================
# CLI / MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Baseline (Vibrado + Sopradora) com regras ligadas.")
    p.add_argument("--base-data", type=Path, required=True, help="Pasta do lote OU pasta com vários lotes.")
    p.add_argument("--model-config-dir", type=Path, required=True, help="Pasta com parâmetros CSVs.")
    p.add_argument("--output-excel", type=Path, default=RESULT_DIR / "baseline_metrics.xlsx", help="Excel de métricas.")
    return p.parse_args()


def parse_day_start_from_lote(lote_dir: Path) -> pd.Timestamp:
    base_date = datetime.strptime(lote_dir.name, "%d%m%Y")
    return pd.Timestamp(base_date + timedelta(days=1))


def discover_lotes(base_data: Path) -> List[Path]:
    if (base_data / "demanda").exists() or list(base_data.glob("brut_demand*.csv")):
        return [base_data]

    return sorted([
        p for p in base_data.iterdir()
        if p.is_dir()
        and p.name != "model_config"
        and re.fullmatch(r"\d{8}", p.name)
    ])


def main() -> None:
    args = parse_args()
    lotes = discover_lotes(args.base_data)
    logger.info("Lotes encontrados: %s", [p.name for p in lotes])

    machines_df, caps_df, shifts_df, setup_df, setup_times_df = load_aux_tables(args.model_config_dir)
    metrics_rows: List[dict] = []
  


    for lote_dir in lotes:
        parquet_modelo_dir = lote_dir / "modelo"
        logger.info("Processando lote: %s", lote_dir.name)

        day_start = parse_day_start_from_lote(lote_dir)
        business_days = compute_business_days(day_start)

        demand_df = load_demand(lote_dir)

        demand_df = demand_df[
            demand_df["machine_name"].apply(lambda x: ("_vibrado" in x) or ("_sopradora" in x))
        ].copy()

        if demand_df.empty:
            logger.warning("Lote %s sem Vibrado/Sopradora. Pulando.", lote_dir.name)
            continue

        machines = build_target_machines(
            demand_df=demand_df,
            machines_df=machines_df,
            caps_df=caps_df,
            shifts_df=shifts_df,
            business_days=business_days,
        )

        kp_macho_data = build_kp_macho_data(setup_df, machines)
        setup_time_data = build_setup_time_data(setup_times_df, machines)

        # ============================================================
        # HEURISTIC / GAP METRICS (FROM PARQUET)
        # ============================================================
        # ============================================================
        # HEURISTIC / GAP METRICS (FROM PARQUET) - POR MAQUINA
        # ============================================================
        parquet_files = sorted(parquet_modelo_dir.glob("job_scheduling_output_*.parquet"))

        if not parquet_files:
            logger.warning("Nenhum parquet de solução encontrado em %s", parquet_modelo_dir)
        else:
            for parquet_path in parquet_files:
                logger.info("Lendo Parquet da heurística/GAP: %s", parquet_path.name)

                df_sol = pd.read_parquet(parquet_path)

                # filtra só vibrado / sopradora
                df_sol = df_sol[
                    df_sol["maquina"].astype(str).apply(
                        lambda x: ("_vibrado" in x) or ("_sopradora" in x)
                    )
                ].copy()

                if df_sol.empty:
                    logger.warning("Parquet %s sem Vibrado/Sopradora. Pulando.", parquet_path.name)
                    continue

                # identifica o cenário pela data do arquivo
                scenario_id = parquet_path.stem.replace("job_scheduling_output_", "")

                for machine_name, df_m in df_sol.groupby("maquina"):

                    # ⚠️ demanda SEMPRE vem do parquet de demanda
                    jobs_demand_total = (
                        demand_df[demand_df["machine_name"] == machine_name]
                        .shape[0]
                    )

                    met_h = compute_metrics_from_parquet_machine(
                        df_machine=df_m,
                        machine_name=machine_name,
                        setup_time_data=setup_time_data,
                    )

                    metrics_rows.append({
                        "lote": lote_dir.name,
                        "scenario": scenario_id,   # 👈 novo
                        "day_start": day_start,
                        "jobs_demand_total": jobs_demand_total,
                        "jobs_unattended": jobs_demand_total - met_h["jobs_total"],
                        "machine_name": machine_name,
                        "recurso": machine_name.split("_")[-1],
                        "solution": "heuristic",
                        **met_h,
                    })
            



        for m in machines:
            jobs_demand_total = demand_df[demand_df["machine_name"] == m.machine_name].shape[0]

            jobs = build_jobs_for_machine(
                demand_df=demand_df,
                machine=m,
                business_days=business_days,
                day_start=day_start,
                kp_macho_data=kp_macho_data,
                setup_time_data=setup_time_data,
            )

            execs = schedule_machine_baseline_fast(
                machine=m,
                jobs=jobs,
                business_days=business_days,
                kp_macho_data=kp_macho_data,
                setup_time_data=setup_time_data,
            )

            logger.info("DEBUG [%s | %s] Demand=%d | Scheduled=%d", lote_dir.name, m.machine_name, jobs_demand_total, len(execs))

            met = compute_metrics(execs)

            metrics_rows.append({
                "lote": lote_dir.name,
                "day_start": day_start,
                "jobs_demand_total": jobs_demand_total,
                "jobs_unattended": jobs_demand_total - met["jobs_total"],
                "machine_name": m.machine_name,
                "recurso": m.recurso,
                "solution": "baseline",
                **met,
            })

    # baseline demand
    logger.info("[BASE DEMAND] %s ->\n%s",
        lote_dir.name,
        demand_df.groupby("machine_name").size()
    )

    # heuristic parquet
    logger.info("[HEUR PARQUET] %s ->\n%s",
        lote_dir.name,
        df_sol.groupby("maquina").size()
    )

    logger.info("[HEUR DATE RANGE] inicio=[%s..%s] day_start=%s",
        df_sol["inicio"].min(),
        df_sol["inicio"].max(),
        day_start
    )


    save_metrics_to_excel(metrics_rows, args.output_excel)


if __name__ == "__main__":
    main()