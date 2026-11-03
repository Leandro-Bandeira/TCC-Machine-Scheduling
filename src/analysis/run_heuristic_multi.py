"""
Executa a heurística ILS (C++) várias vezes para uma máquina e mantém a melhor solução.

O binário `./heuristic <input.json> <machine_id>` sobrescreve a entrada da máquina em
`output_heuristic.json` a cada execução. Este módulo:
1. Roda o binário `n_runs` vezes (padrão 10), lendo a FO de cada execução.
2. Mantém em `output_heuristic.json` apenas a melhor solução (menor FO), que é a usada
   como warm start pelo `optimize.py`.
3. Acrescenta à entrada da máquina as estatísticas de todas as execuções:
   `heuristic_mean_fo`, `heuristic_mean_unallocated`, `heuristic_mean_time_seconds`
   (médias) e `heuristic_runs_fo` (FO de cada execução).
   Os campos originais (`objective_function`, `solve_time_seconds`,
   `count_jobs_not_allocated`, `jobs`) continuam sendo os da MELHOR execução.

Uso:
    python3 -m src.analysis.run_heuristic_multi <input.json> <machine_id> [--runs 10]
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
HEURISTIC_BIN = BASE_DIR / "src" / "heuristics" / "heuristic"
N_RUNS = 10


def _read_machine_entry(heuristic_file: Path, machine_id: int) -> dict | None:
    """Lê a entrada da máquina em `output_heuristic.json` (None se ausente)."""
    if not heuristic_file.exists():
        return None
    with open(heuristic_file, encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("machines_scheduling", []):
        if m.get("machine_id") == machine_id:
            return m
    return None


def _write_machine_entry(heuristic_file: Path, machine_id: int, entry: dict) -> None:
    """Substitui (ou insere) a entrada da máquina em `output_heuristic.json`."""
    with open(heuristic_file, encoding="utf-8") as f:
        data = json.load(f)
    machines = data.setdefault("machines_scheduling", [])
    for i, m in enumerate(machines):
        if m.get("machine_id") == machine_id:
            machines[i] = entry
            break
    else:
        machines.append(entry)
    with open(heuristic_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        f.write("\n")


def run_heuristic_best_of(
    input_file: Path, machine_id: int, n_runs: int = N_RUNS
) -> dict:
    """
    Roda a heurística `n_runs` vezes e deixa a melhor solução em `output_heuristic.json`.

    O binário usa `time(0)` como semente; para evitar execuções idênticas, cada nova
    execução só começa em um segundo diferente da anterior.

    Args:
        input_file: Caminho do `input.json` da instância.
        machine_id: ID da máquina.
        n_runs: Número de execuções.

    Returns:
        A entrada da melhor solução, com as médias (`heuristic_mean_fo`,
        `heuristic_mean_unallocated`, `heuristic_mean_time_seconds`) e
        `heuristic_runs_fo` adicionados.

    Raises:
        RuntimeError: Se nenhuma execução produzir solução.
        subprocess.CalledProcessError: Se o binário retornar erro.
    """
    input_file = Path(input_file)
    heuristic_file = input_file.parent / "output_heuristic.json"

    best: dict | None = None
    fos: list[float] = []
    times: list[float] = []
    unallocated: list[float] = []
    last_second = -1

    for _ in range(n_runs):
        now = int(time.time())
        if now == last_second:
            time.sleep(1 - (time.time() - now))
        last_second = int(time.time())

        subprocess.run(
            [str(HEURISTIC_BIN), str(input_file), str(machine_id)],
            capture_output=True,
            text=True,
            check=True,
        )
        entry = _read_machine_entry(heuristic_file, machine_id)
        if entry is None or entry.get("objective_function") is None:
            continue

        fos.append(entry["objective_function"])
        times.append(entry.get("solve_time_seconds") or 0.0)
        unallocated.append(entry.get("count_jobs_not_allocated") or 0)
        if best is None or entry["objective_function"] < best["objective_function"]:
            best = entry

    if best is None:
        raise RuntimeError(
            f"Heurística não produziu solução para machine_id={machine_id} em {input_file}"
        )

    best["heuristic_mean_fo"] = sum(fos) / len(fos)
    best["heuristic_mean_unallocated"] = sum(unallocated) / len(unallocated)
    best["heuristic_mean_time_seconds"] = sum(times) / len(times)
    best["heuristic_runs_fo"] = fos
    _write_machine_entry(heuristic_file, machine_id, best)
    return best


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Roda a heurística N vezes e mantém a melhor solução."
    )
    parser.add_argument("input_file", type=Path)
    parser.add_argument("machine_id", type=int)
    parser.add_argument("--runs", type=int, default=N_RUNS)
    args = parser.parse_args()

    best = run_heuristic_best_of(args.input_file, args.machine_id, args.runs)
    print(
        f"  [Heurística] best={best['objective_function']:.6f} "
        f"mean={best['heuristic_mean_fo']:.6f} ({len(best['heuristic_runs_fo'])} execuções)"
    )


if __name__ == "__main__":
    main()
