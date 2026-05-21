import argparse
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def ensure_exists(path: Path, kind: str = "file") -> None:
    if kind == "file" and not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if kind == "dir" and not path.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {path}")


def ensure_model_config_directory(
    model_config_dir: Path, possible_sources: Iterable[Path]
) -> Path:
    model_config_dir.mkdir(parents=True, exist_ok=True)

    existing_files = (
        {item.name for item in model_config_dir.iterdir()}
        if model_config_dir.exists()
        else set()
    )

    for source in possible_sources:
        if not source or not source.exists():
            continue
        for item in source.iterdir():
            destination = model_config_dir / item.name
            if destination.name in existing_files:
                continue
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    return model_config_dir


@dataclass
class IOPaths:
    base_data: Path
    output_dir: Path
    input_model_dir: Path
    output_model_dir: Path
    model_config_dir: Optional[Path] = None

    @classmethod
    def build(
        cls,
        *,
        base_data: Path,
        output_dir: Path,
        model_config_dir: Optional[Path] = None,
        input_model_dir: Optional[Path] = None,
        output_model_dir: Optional[Path] = None,
    ) -> "IOPaths":
        input_dir = input_model_dir or output_dir
        output_dir_model = output_model_dir or output_dir
        if model_config_dir is None:
            candidate = base_data / "parameters"
            model_config_dir = candidate if candidate.exists() else None

        return cls(
            base_data=base_data,
            output_dir=output_dir,
            input_model_dir=input_dir,
            output_model_dir=output_dir_model,
            model_config_dir=model_config_dir,
        )


class JobSchedulingOutput:
    @staticmethod
    def _slot_to_dt(
        init_date: pd.Timestamp, time_step: int, slot: Optional[int]
    ) -> Optional[datetime]:
        if slot is None:
            return None
        return (init_date + timedelta(minutes=int(slot) * time_step)).to_pydatetime()

    def run(self, output_dir: Path) -> pd.DataFrame:
        input_file = output_dir / "input.json"
        output_file = output_dir / "output.json"

        with open(input_file, "r") as f:
            input_data = json.load(f)
        with open(output_file, "r") as f:
            output_data = json.load(f)

        init_date = pd.Timestamp(
            datetime.strptime(input_data["init_date"], "%Y-%m-%d %H:%M")
        )
        time_step = int(input_data["time_step"])

        machine_id_to_name = {
            m["machine_id"]: m["machine_name"] for m in input_data["machines"]
        }
        jobs_dict = {j["id"]: j for j in input_data["jobs"]}

        schedule_rows = []

        for mach in output_data.get("machines_scheduling", []):
            m_id = mach["machine_id"]
            m_name = machine_id_to_name.get(m_id, f"Machine_{m_id}")

            for job in mach.get("jobs", []):
                j_id = job["job_id"]
                job_in = jobs_dict.get(j_id, {})
                start_slot = job.get("start")
                end_slot = job.get("end")

                inicio = self._slot_to_dt(init_date, time_step, start_slot)
                fim = self._slot_to_dt(
                    init_date,
                    time_step,
                    end_slot + 1 if end_slot is not None else None,
                )
                release = self._slot_to_dt(
                    init_date, time_step, job_in.get("release_date_slot")
                )
                deadline = self._slot_to_dt(
                    init_date, time_step, job_in.get("due_date_slot")
                )

                schedule_rows.append(
                    {
                        "job_id": j_id,
                        "order_id": job_in.get("order_id"),
                        "resource_id": job_in.get("resource_id"),
                        "maquina": m_name,
                        "inicio": inicio,
                        "fim": fim,
                        "not_before_date": release,
                        "deadline": deadline,
                        "sub_machine": job.get("sub_machine", 0),
                        "Status_Processed": job_in.get("Status_Processed", ""),
                    }
                )

        for j in input_data.get("jobs", []):
            if j.get("Status_Processed"):
                m_id = j.get("assigned_machine_id")
                schedule_rows.append(
                    {
                        "job_id": j["id"],
                        "order_id": j.get("order_id"),
                        "resource_id": j.get("resource_id"),
                        "maquina": machine_id_to_name.get(m_id, ""),
                        "inicio": pd.NaT,
                        "fim": pd.NaT,
                        "not_before_date": self._slot_to_dt(
                            init_date, time_step, j.get("release_date_slot")
                        ),
                        "deadline": self._slot_to_dt(
                            init_date, time_step, j.get("due_date_slot")
                        ),
                        "sub_machine": 0,
                        "Status_Processed": j.get("Status_Processed", ""),
                    }
                )

        if not schedule_rows:
            logger.warning("Nenhum agendamento encontrado.")
            return pd.DataFrame()

        df = pd.DataFrame(schedule_rows)

        for col in ["inicio", "fim", "not_before_date", "deadline"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")

        df["delay"] = (df["fim"] - df["deadline"]).dt.days.fillna(0).clip(lower=0)
        df["tempo_processamento"] = (
            ((df["fim"] - df["inicio"]).dt.total_seconds() / 60).fillna(0).astype(int)
        )

        demanda_dir = output_dir / "demanda"
        demanda_dir.mkdir(parents=True, exist_ok=True)
        current_date = datetime.now().strftime("%Y-%m-%d")
        parquet_path = demanda_dir / f"result_{current_date}.parquet"
        csv_path = demanda_dir / f"result_{current_date}.csv"

        pq.write_table(
            pa.Table.from_pandas(df),
            parquet_path,
            coerce_timestamps="us",
            allow_truncated_timestamps=True,
        )
        df.to_csv(csv_path, index=False, encoding="utf-8")
        logger.info("Arquivos salvos:\n  - %s\n  - %s", parquet_path, csv_path)
        return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Processa a saída do otimizador e gera os arquivos de resultado."
    )
    default_root = Path(__file__).resolve().parent.parent.parent
    parser.add_argument(
        "--dt",
        required=True,
        help="Partição dt a ser processada (formato YYYY-MM-DD).",
    )
    parser.add_argument(
        "--trusted-root",
        type=Path,
        default=default_root / "data" / "trusted",
        help="Diretório raiz das saídas processadas (default: data/trusted).",
    )
    parser.add_argument(
        "--only-status",
        nargs="+",
        default=None,
        help="Lista de status a processar. Se omitido, processa todos.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        dt_obj = datetime.strptime(args.dt, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Data inválida para --dt: {args.dt}") from exc

    date_slug = dt_obj.strftime("%d%m%Y")
    trusted_root: Path = args.trusted_root
    date_dir = trusted_root / date_slug

    ensure_exists(date_dir, kind="dir")

    available_status_dirs = [
        (item.name, item)
        for item in sorted(date_dir.iterdir())
        if item.is_dir() and (item / "input.json").exists()
    ]

    if not available_status_dirs:
        raise SystemExit(f"Nenhum lote com input.json encontrado em {date_dir}.")

    if args.only_status:
        requested = {s.strip().lower() for s in args.only_status if s.strip()}
        found_map = {name.lower(): path for name, path in available_status_dirs}
        missing = sorted(requested - set(found_map.keys()))
        if missing:
            raise SystemExit("Status não encontrados: " + ", ".join(missing))
        status_to_process = [
            (name, found_map[name.lower()]) for name in args.only_status
        ]
    else:
        status_to_process = available_status_dirs

    for status_label, status_dir in status_to_process:
        output_dir = trusted_root / date_slug / status_label
        logger.info("Processando status=%s | dir=%s", status_label, output_dir)
        JobSchedulingOutput().run(output_dir)
        logger.info("Concluído: status=%s", status_label)


if __name__ == "__main__":
    main()
