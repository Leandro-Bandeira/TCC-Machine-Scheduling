import json
import argparse
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unidecode import unidecode

import pandas as pd
import plotly.express as px
import streamlit as st

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LATEST_DIR = BASE_DIR / "data" / "latest"
MODEL_CONFIG_DIR = BASE_DIR / "data" / "raw" / "model_config"
WORK_DAYS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

st.set_page_config(page_title="Planejamento de Produção", layout="wide")


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest-dir", type=Path, default=LATEST_DIR)
    parser.add_argument("--model-config-dir", type=Path, default=MODEL_CONFIG_DIR)
    args, _ = parser.parse_known_args()
    return args


@lru_cache(None)
def add_business_days(base_date: datetime, n: int) -> datetime:
    d = base_date
    remaining = n
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1
    return d


# -----------------------------------------------------------------------------
# Funções de visualização
# -----------------------------------------------------------------------------


def create_week_gantt(df: pd.DataFrame):
    df = df.copy()
    draw_priority = {"indisponivel": 0, "setup": 1, "job": 2}
    df["__draw_priority"] = df["tipo"].map(draw_priority).fillna(1).astype(int)
    df = df.sort_values(["__draw_priority", "inicio", "fim"]).drop(columns="__draw_priority")

    job_days = set(df.loc[df["tipo"] == "job", "inicio"].dt.date)
    if job_days:
        df = df[df["inicio"].dt.date.isin(job_days)]
    else:
        df = df.iloc[0:0]

    hidden_weekdays = []
    if job_days:
        first_day = min(job_days)
        last_day = max(job_days)
        current = first_day
        while current <= last_day:
            if current.weekday() < 5 and current not in job_days:
                hidden_weekdays.append(current)
            current += timedelta(days=1)

    machines = sorted(
        df.loc[df["tipo"] == "job", "maquina"].dropna().unique().tolist()
    )
    palette = [
        "#3B6BA5", "#2A7F7F", "#6A7D2C", "#5B4E77", "#726C15",
        "#8C5A2B", "#2E6B3D", "#1E88E5", "#00838F", "#6D4C41",
        "#7CB342", "#8E24AA", "#3949AB", "#00ACC1", "#5E548E",
    ]
    machine_color_map = {m: palette[i % len(palette)] for i, m in enumerate(machines)}
    machine_color_map.update({
        "SETUP": "#E67E22",
        "INDISPONIVEL": "#708090",
        "JOB_ATRASADO": "#d63031",
    })

    fig = px.timeline(
        df,
        x_start="inicio",
        x_end="fim",
        y="machine_y",
        color="color_tag",
        custom_data=["hover_label"],
        title="Gantt Interativo – Visão por Semana",
        color_discrete_map=machine_color_map,
    )
    fig.update_traces(hovertemplate="%{customdata[0]}")
    fig.update_traces(marker_line_color="black", marker_line_width=2)

    rangebreaks = [dict(bounds=["sat", "mon"])]
    if hidden_weekdays:
        rangebreaks.extend(
            dict(values=[day.strftime("%Y-%m-%d")]) for day in hidden_weekdays
        )

    fig.update_xaxes(rangebreaks=rangebreaks)
    fig.update_xaxes(tickformat="%b %d", dtick=24 * 60 * 60 * 1000)

    yinfo = (
        df[["maquina", "machine_y", "machine_label"]]
        .drop_duplicates()
        .copy()
    )
    yinfo["band_idx"] = (
        yinfo["machine_y"]
        .str.extract(r"_(\d+)$", expand=False)
        .fillna("0")
        .astype(int)
    )
    yinfo = yinfo.sort_values(["maquina", "band_idx"])

    y_order = yinfo["machine_y"].tolist()
    y_texts = yinfo["machine_label"].tolist()

    fig.update_yaxes(
        autorange="reversed",
        categoryorder="array",
        categoryarray=y_order,
        tickmode="array",
        tickvals=y_order,
        ticktext=y_texts,
    )

    return fig


def create_gantt_by_day(df: pd.DataFrame):
    gantt_by_day = {}
    for day, day_df in df.groupby(df["inicio"].dt.date):
        draw_priority = {"indisponivel": 0, "setup": 1, "job": 2}
        day_df = day_df.copy()
        day_df["__draw_priority"] = day_df["tipo"].map(draw_priority).fillna(1).astype(int)
        day_df = day_df.sort_values(["__draw_priority", "inicio", "fim"]).drop(columns="__draw_priority")
        if not (day_df["tipo"] == "job").any():
            continue

        palette = (
            "#3B6BA5", "#2A7F7F", "#6A7D2C", "#5B4E77", "#726C15",
            "#8C5A2B", "#2E6B3D",
        )
        machines = sorted(df["maquina"].dropna().unique().tolist())
        machine_color_map = {m: palette[i % len(palette)] for i, m in enumerate(machines)}
        machine_color_map.update({
            "SETUP": "#E67E22",
            "INDISPONIVEL": "#708090",
            "JOB_ATRASADO": "#d63031",
        })

        fig = px.timeline(
            day_df,
            x_start="inicio",
            x_end="fim",
            y="machine_y",
            color="color_tag",
            custom_data=["hover_label"],
            title=f"Gantt – {day.strftime('%d/%m/%Y')}",
            color_discrete_map=machine_color_map,
        )
        fig.update_traces(hovertemplate="%{customdata[0]}")
        fig.update_traces(marker_line_color="black", marker_line_width=2)

        yinfo = (
            df[["maquina", "machine_y", "machine_label"]]
            .drop_duplicates()
            .copy()
        )
        yinfo["band_idx"] = (
            yinfo["machine_y"]
            .str.extract(r"_(\d+)$", expand=False)
            .fillna("0")
            .astype(int)
        )
        yinfo = yinfo.sort_values(["maquina", "band_idx"])

        y_order = yinfo["machine_y"].tolist()
        y_texts = yinfo["machine_label"].tolist()

        fig.update_yaxes(
            autorange="reversed",
            categoryorder="array",
            categoryarray=y_order,
            tickmode="array",
            tickvals=y_order,
            ticktext=y_texts,
        )

        start_day = datetime.combine(day, datetime.min.time())
        end_day = start_day + timedelta(days=1)
        fig.update_layout(
            height=max(600, 60 * len(y_order)),
            xaxis_title="Hora do Dia",
            yaxis_title="Máquina",
            hovermode="closest",
            showlegend=False,
            xaxis=dict(
                range=[start_day, end_day],
                tickformat="%H:%M",
                ticklabelmode="period",
                tickangle=0,
                dtick=3600000 * 2,
            ),
        )

        for hour in range(0, 24):
            hour_marker = start_day + timedelta(hours=hour)
            fig.add_vline(x=hour_marker, line_width=0.5, line_dash="dot", line_color="gray")

        gantt_by_day[day] = fig
    return gantt_by_day


def create_hover_label(row):
    if row["tipo"] == "setup":
        return (
            f"SETUP<br>"
            f"Início: {row['inicio'].strftime('%H:%M')}<br>"
            f"Fim: {row['fim'].strftime('%H:%M')}<br>"
            f"Tempo: {(row['fim'] - row['inicio']).total_seconds() / 60:.0f} min"
        )
    elif row["tipo"] == "indisponivel":
        return (
            f"Fora de turno<br>"
            f"Início: {row['inicio'].strftime('%H:%M')}<br>"
            f"Fim: {row['fim'].strftime('%H:%M')}<br>"
        )
    else:
        deadline = row.get("deadline")
        not_before = row.get("not_before_date")
        deadline_str = pd.Timestamp(deadline).strftime("%d/%m %H:%M") if pd.notna(deadline) else "-"
        not_before_str = pd.Timestamp(not_before).strftime("%d/%m %H:%M") if pd.notna(not_before) else "-"
        return (
            f"Máquina: {row['maquina']}<br>"
            f"Op: {int(row.get('order_id') or 0)}<br>"
            f"Início: {row['inicio'].strftime('%d/%m %H:%M')}<br>"
            f"Fim: {row['fim'].strftime('%d/%m %H:%M')}<br>"
            f"Not before: {not_before_str}<br>"
            f"Due date: {deadline_str}<br>"
            f"_kf_macho: {row.get('resource_id', '')}<br>"
        )


def split_timeline_rows_by_day(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    segmented_rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        start = row.get("inicio")
        end = row.get("fim")
        if pd.isna(start) or pd.isna(end):
            continue

        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if end_ts <= start_ts:
            continue

        cursor = start_ts
        while cursor < end_ts:
            next_day = cursor.normalize() + pd.Timedelta(days=1)
            seg_end = min(end_ts, next_day)

            seg_row = row.to_dict()
            seg_row["inicio"] = cursor.to_pydatetime()
            seg_row["fim"] = seg_end.to_pydatetime()
            segmented_rows.append(seg_row)

            cursor = seg_end

    if not segmented_rows:
        return df.iloc[0:0].copy()

    return pd.DataFrame(segmented_rows, columns=df.columns).reset_index(drop=True)


def _shift_periods_for_base_day(base_day, shift_row):
    t1_ini = datetime.combine(base_day, datetime.strptime(shift_row["inicio"], "%H:%M").time())
    t1_fim = datetime.combine(base_day, datetime.strptime(shift_row["intervalo_inicio"], "%H:%M").time())
    if t1_fim < t1_ini:
        t1_fim += timedelta(days=1)

    t2_ini = datetime.combine(base_day, datetime.strptime(shift_row["intervalo_fim"], "%H:%M").time())
    if t2_ini < t1_ini:
        t2_ini += timedelta(days=1)

    t2_fim = datetime.combine(base_day, datetime.strptime(shift_row["fim"], "%H:%M").time())
    if t2_fim < t2_ini:
        t2_fim += timedelta(days=1)

    periods = []
    if t1_fim > t1_ini:
        periods.append((t1_ini, t1_fim))
    if t2_fim > t2_ini:
        periods.append((t2_ini, t2_fim))
    return periods


def is_within_shift(start, end, machine_name, shifts_df, machines_df):
    try:
        proc, rec = machine_name.split("_", 1)
    except Exception:
        return False

    row = machines_df[
        (machines_df["processo"] == proc) & (machines_df["recurso"] == rec)
    ]
    if row.empty:
        return False

    turnos = row.iloc[0]["turnos"]
    if not turnos:
        return False

    for base_day in (start.date() - timedelta(days=1), start.date()):
        weekday_name = WORK_DAYS[base_day.weekday()]
        shifts_day = shifts_df[
            (shifts_df["dia"] == weekday_name) & (shifts_df["turno"].isin(turnos))
        ]
        if shifts_day.empty:
            continue

        for _, sh in shifts_day.iterrows():
            for period_start, period_end in _shift_periods_for_base_day(base_day, sh):
                if period_start <= start and end <= period_end:
                    return True

    return False


def process_setups(
    gantt_df_with_band: pd.DataFrame,
    jobs_data: List[Dict],
    setups: Dict,
    time_step: int,
    machines_df,
    shifts_df,
) -> pd.DataFrame:
    """
    setups: {str(machine_id): {str(from_job_id): {str(to_job_id): setup_slots}}}
    """
    if gantt_df_with_band.empty:
        return pd.DataFrame()

    job_machine = {j["id"]: j.get("assigned_machine_id") for j in jobs_data}

    rows = []
    jobs = gantt_df_with_band[gantt_df_with_band["tipo"] == "job"]

    for band_id, group in jobs.groupby("machine_y"):
        g = group.sort_values(["inicio", "fim"]).reset_index(drop=True)

        for i in range(len(g) - 1):
            a = g.loc[i]
            b = g.loc[i + 1]

            job_i = int(a["job_id"])
            job_j = int(b["job_id"])

            machine_id = job_machine.get(job_i)
            setup_slots = setups.get(str(machine_id), {}).get(str(job_i), {}).get(str(job_j), 0)
            setup_min = int(setup_slots) * time_step

            end_prev = a["fim"]
            start_next = b["inicio"]

            if start_next <= end_prev:
                continue

            inside_shift = is_within_shift(
                end_prev, start_next, a["maquina"], shifts_df, machines_df
            )
            if not inside_shift:
                continue

            if setup_min <= 0:
                setup_min = int((start_next - end_prev).total_seconds() / 60)

            start = start_next - timedelta(minutes=setup_min)
            start = max(start, end_prev)
            end = start_next

            rows.append({
                "maquina": a["maquina"],
                "inicio": start,
                "fim": end,
                "machine_y": a["machine_y"],
                "machine_label": a["machine_label"],
                "tipo": "setup",
                "color_tag": "SETUP",
                "job_id": None,
                "hover_label": (
                    f"SETUP<br>"
                    f"De job {job_i} → {job_j}<br>"
                    f"Início: {start.strftime('%H:%M')}<br>"
                    f"Fim: {end.strftime('%H:%M')}"
                ),
                "tempo_processamento_minutos": setup_min,
                "tempo_processamento_minutos_total": setup_min,
            })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Função principal
# -----------------------------------------------------------------------------


def main():
    args = _parse_args()
    latest_dir: Path = args.latest_dir

    if not latest_dir.is_dir():
        st.error(f"Diretório data/latest não encontrado: {latest_dir}. Execute data_output_process.py primeiro.")
        st.stop()

    status_dirs = [
        item for item in sorted(latest_dir.iterdir())
        if item.is_dir()
        and (item / "input.json").exists()
        and (item / "result.parquet").exists()
    ]

    if not status_dirs:
        st.error("Nenhum resultado encontrado em data/latest. Execute data_output_process.py primeiro.")
        st.stop()

    st.sidebar.title("Configurações")
    selected = st.sidebar.selectbox("Status / Lote", [d.name for d in status_dirs])
    status_dir = latest_dir / selected

    with open(status_dir / "input.json") as f:
        input_data = json.load(f)

    schedule_df = pd.read_parquet(status_dir / "result.parquet")

    # Keep only scheduled jobs (pre-processed jobs have NaT inicio)
    schedule_df = schedule_df[schedule_df["inicio"].notna()].copy()
    for col in ["inicio", "fim", "not_before_date", "deadline"]:
        if col in schedule_df.columns:
            schedule_df[col] = pd.to_datetime(schedule_df[col], errors="coerce")

    schedule_df["tipo"] = "job"

    if schedule_df.empty:
        st.warning("Nenhum job agendado encontrado.")
        return

    # ============================================================
    # ARQUIVOS DE PARÂMETROS
    # ============================================================
    model_config_dir = args.model_config_dir

    def parse_turnos_to_list(val):
        if pd.isna(val):
            return []
        val = str(val).strip().lower()
        if val == "geral":
            return [0]
        return [int(v.strip()) for v in val.split(",") if v.strip().isdigit()]

    def _parse_turno_to_int(val):
        try:
            if str(val).strip().lower() == "geral":
                return 0
            return int(val)
        except Exception:
            return 0

    def normalize_string(value):
        if pd.isna(value):
            return ""
        return unidecode(str(value)).lower().replace(" ", "")

    try:
        machines_df = pd.read_csv(
            model_config_dir / "brut_machine_information.csv",
            converters={
                "turnos": parse_turnos_to_list,
                "processo": normalize_string,
                "recurso": normalize_string,
            },
        )
    except Exception as e:
        st.error(f"Erro ao carregar brut_machine_information.csv: {e}")
        return

    try:
        shifts_df = pd.read_csv(
            model_config_dir / "brut_shifts.csv",
            converters={"turno": _parse_turno_to_int},
        )
    except Exception as e:
        st.error(f"Erro ao carregar brut_shifts.csv: {e}")
        return

    expected_cols = {"dia", "turno", "inicio", "intervalo_inicio", "intervalo_fim", "fim"}
    missing_cols = expected_cols - set(shifts_df.columns)
    if missing_cols:
        st.error(f"brut_shifts.csv não contém colunas obrigatórias: {missing_cols}")
        st.stop()

    time_step = int(input_data.get("time_step", 5))
    jobs = input_data.get("jobs", [])
    setups = input_data.get("setups", {})

    st.title("Visualização de Gantt – Planejamento de Produção")

    # ============================================================
    # CONSTRUÇÃO DO DATAFRAME DE SCHEDULE
    # ============================================================
    df = schedule_df.copy()
    df["delay"] = (df["fim"] - df["deadline"]).dt.days.fillna(0).clip(lower=0).astype(int)
    df["tempo_processamento_minutos_total"] = (
        (df["fim"] - df["inicio"]).dt.total_seconds() / 60
    ).fillna(0).astype(int)

    expanded_rows = []
    for _, row in df.iterrows():
        new_row = row.to_dict()
        new_row["day"] = new_row["inicio"].date()
        new_row["tempo_processamento_minutos"] = int(
            (new_row["fim"] - new_row["inicio"]).total_seconds() / 60
        )
        expanded_rows.append(new_row)

    expanded_df = pd.DataFrame(expanded_rows)
    expanded_df["date"] = expanded_df["inicio"].dt.date
    expanded_df["sub_machine"] = expanded_df["sub_machine"].fillna(0).astype(int)

    expanded_df_with_band_list = []
    for (machine, date, sm), group in expanded_df.groupby(["maquina", "date", "sub_machine"]):
        group = group.copy()
        group["machine_y"] = group["maquina"] + "_" + group["sub_machine"].astype(str)
        expanded_df_with_band_list.append(group)

    expanded_df_with_band = pd.concat(expanded_df_with_band_list, ignore_index=True)
    expanded_df_with_band["machine_label"] = expanded_df_with_band["maquina"]
    expanded_df_with_band = expanded_df_with_band.sort_values(
        ["maquina", "sub_machine", "inicio"]
    ).reset_index(drop=True)

    # -------------------- SETUPS --------------------
    setup_df = process_setups(
        expanded_df_with_band, jobs, setups, time_step, machines_df, shifts_df
    )

    if not setup_df.empty:
        expanded_df_with_band = pd.concat(
            [expanded_df_with_band, setup_df], ignore_index=True
        )

    # -------------------- INDISPONIBILIDADE ENTRE JOBS --------------------
    indisponiveis = []
    jobs_sorted = (
        expanded_df_with_band[expanded_df_with_band["tipo"] == "job"]
        .sort_values(["maquina", "sub_machine", "inicio"])
    )

    for (machine, sm), group in jobs_sorted.groupby(["maquina", "sub_machine"]):
        group = group.sort_values("inicio").reset_index(drop=True)

        for i in range(len(group) - 1):
            current_job = group.loc[i]
            next_job = group.loc[i + 1]

            end_a = current_job["fim"]
            start_b = next_job["inicio"]

            if end_a.date() != start_b.date():
                continue

            if start_b > end_a:
                if not setup_df.empty:
                    has_setup_between = setup_df[
                        (setup_df["machine_y"] == current_job["machine_y"])
                        & (setup_df["inicio"] >= end_a)
                        & (setup_df["fim"] <= start_b)
                    ]
                    if not has_setup_between.empty:
                        continue

                indisponiveis.append({
                    "maquina": machine,
                    "sub_machine": sm,
                    "inicio": end_a,
                    "fim": start_b,
                    "machine_y": f"{machine}_{sm}",
                    "machine_label": machine,
                    "color_tag": "INDISPONIVEL",
                    "tipo": "indisponivel",
                    "hover_label": (
                        f"Fora do turno<br>"
                        f"Início: {end_a.strftime('%H:%M')}<br>"
                        f"Fim: {start_b.strftime('%H:%M')}"
                    ),
                })

    # -------------------- FORA DE TURNO --------------------
    fora_turno_rows = []

    machines_band = (
        expanded_df_with_band[["maquina", "sub_machine"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    jobs_for_horizon = expanded_df_with_band[expanded_df_with_band["tipo"] == "job"]
    if not jobs_for_horizon.empty:
        horizon_start = pd.Timestamp(jobs_for_horizon["inicio"].min()).normalize()
        horizon_end = pd.Timestamp(jobs_for_horizon["fim"].max())
        total_days = (horizon_end.normalize() - horizon_start).days + 1

        for day_offset in range(total_days):
            dia_ts = horizon_start + pd.Timedelta(days=day_offset)
            dia = dia_ts.date()
            dia_inicio = dia_ts.to_pydatetime()
            dia_fim_exclusive = (dia_ts + pd.Timedelta(days=1)).to_pydatetime()

            for _, m in machines_band.iterrows():
                proc_norm, recurso_norm = m["maquina"].split("_", 1)

                row_m = machines_df[
                    (machines_df["processo"] == proc_norm)
                    & (machines_df["recurso"] == recurso_norm)
                ]
                if row_m.empty:
                    continue

                machine_turnos = row_m["turnos"].iloc[0]
                if not machine_turnos:
                    continue

                periodos_trabalho = []
                for base_day in (dia - timedelta(days=1), dia):
                    day_name = WORK_DAYS[base_day.weekday()]
                    machine_shifts = shifts_df[
                        (shifts_df["dia"] == day_name)
                        & (shifts_df["turno"].isin(machine_turnos))
                    ]
                    if machine_shifts.empty:
                        continue

                    for _, row_s in machine_shifts.iterrows():
                        for ini_raw, fim_raw in _shift_periods_for_base_day(base_day, row_s):
                            ini = max(ini_raw, dia_inicio)
                            fim = min(fim_raw, dia_fim_exclusive)
                            if fim > ini:
                                periodos_trabalho.append((ini, fim))

                if not periodos_trabalho:
                    continue

                cursor = dia_inicio
                for ini, fim in sorted(periodos_trabalho):
                    if ini > cursor:
                        fora_turno_rows.append({
                            "maquina": m["maquina"],
                            "sub_machine": m["sub_machine"],
                            "inicio": cursor,
                            "fim": ini,
                            "machine_y": f'{m["maquina"]}_{m["sub_machine"]}',
                            "machine_label": m["maquina"],
                            "color_tag": "INDISPONIVEL",
                            "tipo": "indisponivel",
                            "hover_label": "Fora do turno",
                        })
                    if fim > cursor:
                        cursor = fim

                if cursor < dia_fim_exclusive:
                    fora_turno_rows.append({
                        "maquina": m["maquina"],
                        "sub_machine": m["sub_machine"],
                        "inicio": cursor,
                        "fim": dia_fim_exclusive,
                        "machine_y": f'{m["maquina"]}_{m["sub_machine"]}',
                        "machine_label": m["maquina"],
                        "color_tag": "INDISPONIVEL",
                        "tipo": "indisponivel",
                        "hover_label": "Fora do turno",
                    })

    if fora_turno_rows:
        expanded_df_with_band = pd.concat(
            [expanded_df_with_band, pd.DataFrame(fora_turno_rows)], ignore_index=True
        )

    if indisponiveis:
        expanded_df_with_band = pd.concat(
            [expanded_df_with_band, pd.DataFrame(indisponiveis)], ignore_index=True
        )

    # -------------------------------------------------------
    # MERGE FINAL
    # -------------------------------------------------------
    expanded_df_with_band["sub_machine"] = (
        expanded_df_with_band["sub_machine"].fillna(0).astype(int)
    )
    expanded_df_with_band["machine_y"] = (
        expanded_df_with_band["maquina"].astype(str)
        + "_"
        + expanded_df_with_band["sub_machine"].astype(str)
    )
    expanded_df_with_band["machine_label"] = expanded_df_with_band["maquina"]

    def _color_tag(row):
        if row["tipo"] == "setup":
            return "SETUP"
        if row["tipo"] == "indisponivel":
            return "INDISPONIVEL"
        if (
            pd.notna(row.get("deadline"))
            and pd.notna(row.get("fim"))
            and pd.Timestamp(row["fim"]) > pd.Timestamp(row["deadline"])
        ):
            return "JOB_ATRASADO"
        return row["maquina"]

    expanded_df_with_band["color_tag"] = expanded_df_with_band.apply(_color_tag, axis=1)

    render_df = split_timeline_rows_by_day(expanded_df_with_band)
    render_df["hover_label"] = render_df.apply(create_hover_label, axis=1)

    # ----------------- Plotagem -----------------
    st.subheader("Gráfico de Gantt Interativo – Semana")
    fig_week = create_week_gantt(render_df)
    st.plotly_chart(fig_week, use_container_width=True)

    st.subheader("Gráficos de Gantt por Dia")
    gantt_by_day = create_gantt_by_day(render_df)
    for day, fig in gantt_by_day.items():
        st.write(f"**Gantt para o dia {day.strftime('%d/%m/%Y')}**")
        st.plotly_chart(fig, use_container_width=True)


main()
