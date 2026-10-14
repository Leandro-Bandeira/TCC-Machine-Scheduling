#!/usr/bin/env python3
"""
Script de análise de ganhos dos movimentos de busca local a partir de execucao_debug.txt.

Uso:
    python3 src/analysis/moves_gain.py [caminho_execucao_debug.txt]
    python3 -m src.analysis.moves_gain [caminho_execucao_debug.txt]
"""

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analisa os ganhos dos movimentos de busca local registrados em execucao_debug.txt."
    )
    parser.add_argument(
        "log_path",
        nargs="?",
        default=None,
        help="Caminho para o arquivo execucao_debug.txt (padrão: busca em ./execucao_debug.txt ou src/heuristics/execucao_debug.txt).",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Caminho opcional para exportar a tabela consolidada em CSV.",
    )
    return parser.parse_args()


def resolve_log_path(provided_path: str | None) -> Path:
    if provided_path:
        p = Path(provided_path)
        if not p.exists():
            print(f"[ERRO] Arquivo não encontrado: {p}", file=sys.stderr)
            sys.exit(1)
        return p

    candidates = [
        Path("execucao_debug.txt"),
        Path("src/heuristics/execucao_debug.txt"),
        Path(__file__).resolve().parent.parent / "heuristics" / "execucao_debug.txt",
    ]
    for c in candidates:
        if c.exists():
            return c

    print(
        "[ERRO] Nenhum arquivo execucao_debug.txt fornecido ou encontrado nos caminhos padrão.",
        file=sys.stderr,
    )
    print("Uso: python3 src/analysis/moves_gain.py <caminho_execucao_debug.txt>", file=sys.stderr)
    sys.exit(1)


def parse_moves(log_file: Path) -> list[dict]:
    """Lê o arquivo de log e extrai os registros de movimentos e ganhos."""
    records = []

    pattern_new = re.compile(
        r"Movimento:\s*([^,]+),\s*Ganho:\s*([0-9.eE+-]+)(?:,\s*FO_Anterior:\s*([0-9.eE+-]+),\s*FO_Nova:\s*([0-9.eE+-]+))?"
    )

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_str = line.strip()
            match_new = pattern_new.search(line_str)
            if match_new:
                move_name = match_new.group(1).strip()
                gain = float(match_new.group(2))
                fo_ant = float(match_new.group(3)) if match_new.group(3) else None
                fo_nova = float(match_new.group(4)) if match_new.group(4) else None
                records.append({
                    "movimento": move_name,
                    "ganho": gain,
                    "fo_anterior": fo_ant,
                    "fo_nova": fo_nova,
                })

    return records


def aggregate_stats(records: list[dict]) -> list[dict]:
    """Agrega estatísticas por movimento sem depender de bibliotecas externas."""
    by_move = defaultdict(list)
    for r in records:
        if r["ganho"] is not None:
            by_move[r["movimento"]].append(r["ganho"])

    if not by_move:
        return []

    total_overall_gain = sum(sum(vals) for vals in by_move.values())
    total_overall_count = sum(len(vals) for vals in by_move.values())

    rows = []
    for move_name, vals in by_move.items():
        count = len(vals)
        tot_gain = sum(vals)
        avg_gain = tot_gain / count if count > 0 else 0.0
        min_gain = min(vals)
        max_gain = max(vals)
        pct_gain = (tot_gain / total_overall_gain * 100.0) if total_overall_gain > 0 else 0.0
        pct_count = (count / total_overall_count * 100.0) if total_overall_count > 0 else 0.0

        rows.append({
            "Movimento": move_name,
            "Qtd": count,
            "% Qtd": pct_count,
            "Ganho Total": tot_gain,
            "Ganho Médio": avg_gain,
            "Mínimo": min_gain,
            "Máximo": max_gain,
            "% Ganho": pct_gain,
        })

    # Ordena decrescente por Ganho Total
    rows.sort(key=lambda x: x["Ganho Total"], reverse=True)
    return rows


def print_table(rows: list[dict], log_file: Path) -> None:
    print("\n" + "=" * 98)
    print("           RELATÓRIO DE GANHOS POR MOVIMENTO DE BUSCA LOCAL (RVND)")
    print("=" * 98)
    print(f"Arquivo analisado: {log_file.resolve()}")
    total_count = sum(r["Qtd"] for r in rows)
    print(f"Total de melhorias aceitas registradas: {total_count}")
    print("-" * 98)

    if not rows:
        print("Nenhum movimento com ganho registrado no arquivo de log.")
        print("=" * 98 + "\n")
        return

    # Cabeçalho da tabela
    header = f"{'Movimento':<14} | {'Qtd':>6} | {'% Qtd':>7} | {'Ganho Total':>14} | {'Ganho Médio':>14} | {'Mínimo':>12} | {'Máximo':>12} | {'% Ganho':>8}"
    print(header)
    print("-" * 98)

    for r in rows:
        line = (
            f"{r['Movimento']:<14} | "
            f"{r['Qtd']:>6d} | "
            f"{r['% Qtd']:>6.2f}% | "
            f"{r['Ganho Total']:>14.6f} | "
            f"{r['Ganho Médio']:>14.6f} | "
            f"{r['Mínimo']:>12.6f} | "
            f"{r['Máximo']:>12.6f} | "
            f"{r['% Ganho']:>7.2f}%"
        )
        print(line)

    print("-" * 98)
    tot_gain = sum(r["Ganho Total"] for r in rows)
    avg_global = tot_gain / total_count if total_count > 0 else 0.0
    footer = (
        f"{'TOTAL GERAL':<14} | "
        f"{total_count:>6d} | "
        f"{100.0:>6.2f}% | "
        f"{tot_gain:>14.6f} | "
        f"{avg_global:>14.6f} | "
        f"{'-':>12} | "
        f"{'-':>12} | "
        f"{100.0:>7.2f}%"
    )
    print(footer)
    print("=" * 98 + "\n")


def export_csv(rows: list[dict], csv_path: Path) -> None:
    if not rows:
        return
    fieldnames = ["Movimento", "Qtd", "% Qtd", "Ganho Total", "Ganho Médio", "Mínimo", "Máximo", "% Ganho"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[EXPORT] Tabela exportada em: {csv_path.resolve()}\n")


def main():
    args = parse_arguments()
    log_path = resolve_log_path(args.log_path)
    records = parse_moves(log_path)

    if not records:
        print(f"[AVISO] Nenhum registro de movimento com ganho encontrado em: {log_path}")
        return

    rows = aggregate_stats(records)
    print_table(rows, log_path)

    if args.csv:
        export_csv(rows, Path(args.csv))


if __name__ == "__main__":
    main()
