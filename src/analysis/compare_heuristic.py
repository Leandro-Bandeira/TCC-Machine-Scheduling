"""
Roda o heuristic (ILS) para cada instância listada em run_config.json e
compara o resultado com o output.json (solução do MIP), reportando
diferença de função objetivo e de tempo de execução.

Gera data/heuristic_vs_mip.csv.
"""

import csv
import json
import re
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

FO_RE = re.compile(r"^Fun[cç][aã]o objetivo: ([\-0-9.eE]+)", re.MULTILINE)
TIME_RE = re.compile(r"Tempo total: ([\-0-9.eE]+)s")

FIELDNAMES = [
    "dt",
    "status",
    "machine_id",
    "machine_name",
    "mip_fo",
    "heuristic_fo",
    "fo_diff",
    "fo_diff_pct",
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


def run_heuristic(input_file: Path, machine_id: int) -> tuple[float, float]:
    """Executa o binário e retorna (fo, tempo_segundos)."""
    result = subprocess.run(
        [str(HEURISTIC_BIN), str(input_file), str(machine_id)],
        capture_output=True,
        text=True,
        check=True,
    )
    fo_match = FO_RE.search(result.stdout)
    time_match = TIME_RE.search(result.stdout)
    if not fo_match or not time_match:
        raise RuntimeError(
            f"saída do heuristic não casou com o padrão esperado "
            f"(input={input_file}, machine_id={machine_id})\n{result.stdout[-500:]}"
        )
    return float(fo_match.group(1)), float(time_match.group(1))


def collect_comparisons(run_config: dict) -> list[dict]:
    rows = []

    for dt, cfg in run_config.items():
        date_slug = iso_to_ddmmyyyy(dt)
        machines_wanted = set(cfg.get("machines", []))

        for status in cfg.get("only_status", []):
            instance_dir = TRUSTED_DIR / date_slug / status
            input_file = instance_dir / "input.json"
            output_file = instance_dir / "output.json"

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

            for mach in output_data.get("machines_scheduling", []):
                machine_id = mach["machine_id"]
                machine_name = machine_name_by_id.get(machine_id)

                if machine_name not in machines_wanted:
                    continue

                mip_fo = mach.get("objective_function")
                mip_time = mach.get("solve_time_seconds")

                print(f"[run] {dt} / status={status} / {machine_name} (machine_id={machine_id})")
                try:
                    heuristic_fo, heuristic_time = run_heuristic(input_file, machine_id)
                except (RuntimeError, subprocess.CalledProcessError) as e:
                    print(f"  [ERRO] {e}")
                    continue

                fo_diff = heuristic_fo - mip_fo
                fo_diff_pct = (fo_diff / mip_fo * 100) if mip_fo else float("nan")
                time_diff = heuristic_time - mip_time

                rows.append(
                    {
                        "dt": dt,
                        "status": status,
                        "machine_id": machine_id,
                        "machine_name": machine_name,
                        "mip_fo": mip_fo,
                        "heuristic_fo": heuristic_fo,
                        "fo_diff": fo_diff,
                        "fo_diff_pct": fo_diff_pct,
                        "mip_time_seconds": mip_time,
                        "heuristic_time_seconds": heuristic_time,
                        "time_diff_seconds": time_diff,
                    }
                )
                print(
                    f"  fo: mip={mip_fo:.6f} heuristic={heuristic_fo:.6f} diff={fo_diff:+.6f} ({fo_diff_pct:+.2f}%)"
                    f" | tempo: mip={mip_time:.3f}s heuristic={heuristic_time:.3f}s diff={time_diff:+.3f}s"
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
    if not RUN_CONFIG_JSON.exists():
        print(f"run_config.json não encontrado em {RUN_CONFIG_JSON}")
        sys.exit(1)

    build_heuristic()

    with open(RUN_CONFIG_JSON, encoding="utf-8") as f:
        run_config = json.load(f)

    rows = collect_comparisons(run_config)
    if not rows:
        print("Nenhuma comparação gerada.")
        return

    write_csv(rows, OUT_CSV)


if __name__ == "__main__":
    main()
