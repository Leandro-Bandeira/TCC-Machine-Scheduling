"""
Dashboard Interativo (Streamlit): Case AFM (Real Solution) vs Heurística ILS/VNS.

Lê `Case_AFM-main/baseline_vs_heuristic.csv` e apresenta:
- KPIs gerais de alocação, ganho de tarefas, função objetivo e tempo de execução.
- Agrupamento temporal configurável por Mês ou Semana.
- Ganho de tarefas que poderiam ter sido produzidas (e variação de um mês/semana para outro).
- Análise de ganho por tempo de execução/produção e desempenho por máquina.

Uso:
    streamlit run Case_AFM-main/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

CASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = CASE_DIR / "baseline_vs_heuristic.csv"

st.set_page_config(
    page_title="Case AFM vs Heurística — Dashboard",
    page_icon="📊",
    layout="wide",
)


@st.cache_data(ttl=60)
def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["dt"] = pd.to_datetime(df["dt"])
    df["real_allocated"] = (df["count_jobs"] - df["real_unallocated"]).clip(lower=0)
    df["heuristic_allocated"] = (df["count_jobs"] - df["heuristic_unallocated"]).clip(lower=0)
    df["tasks_gained"] = df["real_unallocated"] - df["heuristic_unallocated"]
    df["fo_improvement_pct"] = -df["fo_diff_pct"]
    df["month"] = df["dt"].dt.to_period("M").astype(str)
    # Semana começando na segunda-feira (formato YYYY-MM-DD do início da semana)
    df["week_start"] = df["dt"].dt.to_period("W-SUN").apply(lambda p: p.start_time)
    df["week"] = df["week_start"].dt.strftime("%Y-%m-%d")
    return df.sort_values("dt").reset_index(drop=True)


def aggregate_by_period(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    period_col = "month" if freq == "Mensal" else "week"
    agg = (
        df.groupby(period_col, as_index=False)
        .agg(
            instances=("dt", "count"),
            total_jobs=("count_jobs", "sum"),
            real_allocated=("real_allocated", "sum"),
            heuristic_allocated=("heuristic_allocated", "sum"),
            real_unallocated=("real_unallocated", "sum"),
            heuristic_unallocated=("heuristic_unallocated", "sum"),
            tasks_gained=("tasks_gained", "sum"),
            real_fo_mean=("real_solution_fo", "mean"),
            heuristic_fo_mean=("mean_heuristic_fo", "mean"),
            fo_improvement_pct_mean=("fo_improvement_pct", "mean"),
            real_time_sum=("real_solution_time_seconds", "sum"),
            heuristic_time_sum=("mean_heuristic_time_seconds", "sum"),
            heuristic_time_mean=("mean_heuristic_time_seconds", "mean"),
            horizon_sum=("H", "sum"),
        )
        .sort_values(period_col)
        .reset_index(drop=True)
    )
    agg = agg.rename(columns={period_col: "periodo"})
    agg["real_alloc_rate_pct"] = (
        agg["real_allocated"] / agg["total_jobs"].replace(0, pd.NA) * 100
    ).fillna(0.0)
    agg["heuristic_alloc_rate_pct"] = (
        agg["heuristic_allocated"] / agg["total_jobs"].replace(0, pd.NA) * 100
    ).fillna(0.0)
    agg["tasks_gained_cumulative"] = agg["tasks_gained"].cumsum()
    agg["real_unallocated_cumulative"] = agg["real_unallocated"].cumsum()
    agg["heuristic_unallocated_cumulative"] = agg["heuristic_unallocated"].cumsum()
    agg["tasks_diff_total"] = agg["heuristic_allocated"] - agg["real_allocated"]
    agg["tasks_gained_per_heur_sec"] = (
        agg["tasks_gained"] / agg["heuristic_time_sum"].replace(0, pd.NA)
    ).fillna(0.0)
    return agg


def main() -> None:
    st.title("📊 Case AFM (Real Solution) vs Heurística ILS/VNS")
    st.caption(
        "Análise comparativa de alocação de tarefas, redução de Função Objetivo e tempo de execução."
    )

    with st.sidebar:
        st.header("Configurações")
        csv_input = st.text_input("Arquivo CSV", value=str(DEFAULT_CSV))
        csv_path = Path(csv_input)
        if st.button("Recarregar dados"):
            load_data.clear()

    if not csv_path.exists():
        st.error(f"Arquivo CSV não encontrado: `{csv_path}`")
        st.info(
            "Execute `python3 Case_AFM-main/compare_heuristic.py` para gerar o CSV."
        )
        st.stop()

    df_raw = load_data(csv_path)
    if df_raw.empty:
        st.warning("O CSV está vazio.")
        st.stop()

    with st.sidebar:
        granularity = st.radio("Agrupamento temporal", ["Mensal", "Semanal"], index=0)
        machines_all = sorted(df_raw["machine_name"].dropna().unique().tolist())
        selected_machines = st.multiselect(
            "Máquinas",
            options=machines_all,
            default=machines_all,
        )
        min_dt = df_raw["dt"].min().date()
        max_dt = df_raw["dt"].max().date()
        date_range = st.date_input(
            "Período",
            value=(min_dt, max_dt),
            min_value=min_dt,
            max_value=max_dt,
        )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_dt, end_dt = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start_dt, end_dt = pd.Timestamp(min_dt), pd.Timestamp(max_dt)

    df = df_raw[
        df_raw["machine_name"].isin(selected_machines)
        & (df_raw["dt"] >= start_dt)
        & (df_raw["dt"] <= end_dt)
    ].copy()

    if df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        st.stop()

    # -------------------------------------------------------------------------
    # KPIs principais
    # -------------------------------------------------------------------------
    total_jobs = float(df["count_jobs"].sum())
    real_unalloc = float(df["real_unallocated"].sum())
    heur_unalloc = float(df["heuristic_unallocated"].sum())
    tasks_gained = real_unalloc - heur_unalloc
    real_alloc_rate = ((total_jobs - real_unalloc) / total_jobs * 100) if total_jobs else 0.0
    heur_alloc_rate = ((total_jobs - heur_unalloc) / total_jobs * 100) if total_jobs else 0.0
    unalloc_reduction_pct = (tasks_gained / real_unalloc * 100) if real_unalloc > 0 else 0.0

    avg_fo_improv = float(df["fo_improvement_pct"].mean())
    total_real_time = float(df["real_solution_time_seconds"].sum())
    total_heur_time = float(df["mean_heuristic_time_seconds"].sum())

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Instâncias / Jobs", f"{len(df):,}", f"{int(total_jobs):,} jobs")
    k2.metric(
        "Tarefas Ganhas (Heurística)",
        f"+{tasks_gained:,.1f}",
        f"-{unalloc_reduction_pct:.1f}% não alocados",
    )
    k3.metric(
        "Taxa de Alocação (Heurística)",
        f"{heur_alloc_rate:.1f}%",
        f"+{heur_alloc_rate - real_alloc_rate:.1f} pp vs Real ({real_alloc_rate:.1f}%)",
    )
    k4.metric("Redução Média de FO", f"{avg_fo_improv:.1f}%")
    k5.metric(
        "Tempo Total Heurística",
        f"{total_heur_time:.2f}s",
        f"Real: {total_real_time:.3f}s",
    )

    period_df = aggregate_by_period(df, granularity)

    tab_time, tab_perf, tab_machine, tab_data = st.tabs(
        [
            "📅 Agrupamento Mês/Semana & Ganho de Tarefas",
            "⏱️ Ganho por Tempo & Função Objetivo",
            "🏭 Análise por Máquina",
            "📋 Dados Detalhados",
        ]
    )

    # -------------------------------------------------------------------------
    # Aba 1: Agrupamento por Mês/Semana & Ganho de Tarefas
    # -------------------------------------------------------------------------
    with tab_time:
        st.subheader(f"Visão {granularity}: Tarefas Alocadas e Ganho de Produção")

        col_a, col_b = st.columns(2)
        with col_a:
            fig_alloc = go.Figure()
            fig_alloc.add_trace(
                go.Bar(
                    x=period_df["periodo"],
                    y=period_df["real_allocated"],
                    name="Real Solution (Alocadas)",
                    marker_color="#636EFA",
                )
            )
            fig_alloc.add_trace(
                go.Bar(
                    x=period_df["periodo"],
                    y=period_df["heuristic_allocated"],
                    name="Heurística (Alocadas)",
                    marker_color="#00CC96",
                )
            )
            fig_alloc.update_layout(
                barmode="group",
                title=f"Tarefas Alocadas por Período ({granularity})",
                xaxis_title="Período",
                yaxis_title="Tarefas alocadas",
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_alloc, use_container_width=True)

        with col_b:
            fig_gain = go.Figure()
            fig_gain.add_trace(
                go.Bar(
                    x=period_df["periodo"],
                    y=period_df["tasks_gained"],
                    name="Tarefas ganhas no período",
                    marker_color="#00CC96",
                    text=period_df["tasks_gained"].round(1),
                    textposition="outside",
                )
            )
            fig_gain.add_trace(
                go.Scatter(
                    x=period_df["periodo"],
                    y=period_df["tasks_gained_cumulative"],
                    name="Ganho acumulado",
                    mode="lines+markers",
                    yaxis="y2",
                    line=dict(color="#EF553B", width=2.5),
                )
            )
            fig_gain.update_layout(
                title=f"Tarefas que Poderiam Ter Sido Produzidas ({granularity})",
                xaxis_title="Período",
                yaxis_title="Tarefas ganhas (Real - Heurística)",
                yaxis2=dict(
                    title="Acumulado",
                    overlaying="y",
                    side="right",
                ),
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_gain, use_container_width=True)

        st.subheader("Ganho ou Perda: Total Heurística vs Total Real")
        diff_df = period_df.copy()
        diff_df["resultado"] = diff_df["tasks_diff_total"].apply(
            lambda v: "Ganho" if v >= 0 else "Perda"
        )
        fig_diff_total = px.bar(
            diff_df,
            x="periodo",
            y="tasks_diff_total",
            color="resultado",
            color_discrete_map={"Ganho": "#00CC96", "Perda": "#EF553B"},
            text=diff_df["tasks_diff_total"].map(lambda v: f"{v:+.1f}"),
            title=f"Ganho ou Perda de Tarefas Produzidas: Total Heurística - Total Real ({granularity})",
            labels={
                "periodo": "Período",
                "tasks_diff_total": "Ganho / Perda de tarefas",
            },
        )
        fig_diff_total.update_traces(textposition="outside", cliponaxis=False)
        fig_diff_total.update_xaxes(type="category")
        max_diff = float(diff_df["tasks_diff_total"].max() or 0)
        min_diff = float(diff_df["tasks_diff_total"].min() or 0)
        fig_diff_total.update_yaxes(
            range=[
                min_diff * 1.15 if min_diff < 0 else 0,
                max_diff * 1.15 if max_diff > 0 else 10,
            ]
        )
        st.plotly_chart(fig_diff_total, use_container_width=True)

        st.subheader("Gargalo Operacional Acumulado (Backlog de Jobs Não Produzidos)")
        max_backlog = float(period_df["real_unallocated_cumulative"].max() or 0)
        fig_backlog = go.Figure()
        fig_backlog.add_trace(
            go.Scatter(
                x=period_df["periodo"],
                y=period_df["real_unallocated_cumulative"],
                name="Backlog Acumulado (Real Solution)",
                mode="lines+markers+text",
                text=period_df["real_unallocated_cumulative"].round(0).astype(int),
                textposition="top center",
                cliponaxis=False,
                fill="tozeroy",
                line=dict(color="#EF553B", width=2.5),
            )
        )
        fig_backlog.add_trace(
            go.Scatter(
                x=period_df["periodo"],
                y=period_df["heuristic_unallocated_cumulative"],
                name="Backlog Acumulado (Heurística)",
                mode="lines+markers",
                fill="tozeroy",
                line=dict(color="#00CC96", width=2.5),
            )
        )
        fig_backlog.update_layout(
            title=f"Acúmulo de Jobs Deixados de Produzir ao Longo dos Períodos ({granularity})",
            xaxis_title="Período",
            yaxis_title="Jobs não produzidos (acumulado)",
            yaxis=dict(range=[0, max_backlog * 1.15 if max_backlog > 0 else 10]),
            margin=dict(t=70, r=40),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig_backlog, use_container_width=True)

        st.dataframe(
            period_df[
                [
                    "periodo",
                    "instances",
                    "total_jobs",
                    "real_allocated",
                    "heuristic_allocated",
                    "tasks_diff_total",
                    "real_unallocated_cumulative",
                    "heuristic_unallocated_cumulative",
                    "tasks_gained_cumulative",
                    "real_alloc_rate_pct",
                    "heuristic_alloc_rate_pct",
                ]
            ].rename(
                columns={
                    "periodo": "Período",
                    "instances": "Instâncias",
                    "total_jobs": "Total Jobs",
                    "real_allocated": "Alocados (Real)",
                    "heuristic_allocated": "Alocados (Heurística)",
                    "tasks_diff_total": "Ganho / Perda (Heur. - Real)",
                    "real_unallocated_cumulative": "Backlog Acum. (Real)",
                    "heuristic_unallocated_cumulative": "Backlog Acum. (Heurística)",
                    "tasks_gained_cumulative": "Gargalo Evitado Acum.",
                    "real_alloc_rate_pct": "Taxa Aloc. Real (%)",
                    "heuristic_alloc_rate_pct": "Taxa Aloc. Heur. (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    # -------------------------------------------------------------------------
    # Aba 2: Ganho por Tempo & Função Objetivo
    # -------------------------------------------------------------------------
    with tab_perf:
        st.subheader("Ganho por Tempo de Produção / Execução")
        c1, c2 = st.columns(2)
        with c1:
            fig_time = go.Figure()
            fig_time.add_trace(
                go.Bar(
                    x=period_df["periodo"],
                    y=period_df["heuristic_time_sum"],
                    name="Tempo Total Heurística (s)",
                    marker_color="#AB63FA",
                )
            )
            fig_time.add_trace(
                go.Scatter(
                    x=period_df["periodo"],
                    y=period_df["tasks_gained_per_heur_sec"],
                    name="Tarefas ganhas / segundo (Heurística)",
                    mode="lines+markers",
                    yaxis="y2",
                    line=dict(color="#00CC96", width=2.5),
                )
            )
            fig_time.update_layout(
                title=f"Tempo Computacional vs Ganho de Tarefas por Segundo ({granularity})",
                xaxis_title="Período",
                yaxis_title="Tempo total heurística (s)",
                yaxis2=dict(
                    title="Tarefas ganhas / s",
                    overlaying="y",
                    side="right",
                ),
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_time, use_container_width=True)

        with c2:
            fig_scatter = px.scatter(
                df,
                x="mean_heuristic_time_seconds",
                y="tasks_gained",
                color="machine_name",
                size="count_jobs",
                hover_data=["dt", "status", "real_solution_fo", "mean_heuristic_fo"],
                title="Relação Tempo da Heurística vs Tarefas Ganhas (por instância)",
                labels={
                    "mean_heuristic_time_seconds": "Tempo médio heurística (s)",
                    "tasks_gained": "Tarefas ganhas",
                    "machine_name": "Máquina",
                    "count_jobs": "Jobs",
                },
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        st.subheader("Redução da Função Objetivo (FO)")
        fig_fo = px.bar(
            period_df,
            x="periodo",
            y="fo_improvement_pct_mean",
            text=period_df["fo_improvement_pct_mean"].map(lambda v: f"{v:.1f}%"),
            title=f"Redução Média da FO: Heurística vs Real Solution ({granularity})",
            labels={
                "periodo": "Período",
                "fo_improvement_pct_mean": "Redução média de FO (%)",
            },
            color_discrete_sequence=["#19D3F3"],
        )
        fig_fo.update_traces(textposition="outside")
        st.plotly_chart(fig_fo, use_container_width=True)

    # -------------------------------------------------------------------------
    # Aba 3: Análise por Máquina
    # -------------------------------------------------------------------------
    with tab_machine:
        mach_df = (
            df.groupby("machine_name", as_index=False)
            .agg(
                instances=("dt", "count"),
                total_jobs=("count_jobs", "sum"),
                real_unallocated=("real_unallocated", "sum"),
                heuristic_unallocated=("heuristic_unallocated", "sum"),
                tasks_gained=("tasks_gained", "sum"),
                fo_improvement_pct_mean=("fo_improvement_pct", "mean"),
                real_time_mean=("real_solution_time_seconds", "mean"),
                heuristic_time_mean=("mean_heuristic_time_seconds", "mean"),
            )
            .sort_values("tasks_gained", ascending=False)
        )
        mach_df["tasks_gained_per_sec"] = (
            mach_df["tasks_gained"]
            / (mach_df["heuristic_time_mean"] * mach_df["instances"]).replace(0, pd.NA)
        ).fillna(0.0)

        m1, m2 = st.columns(2)
        with m1:
            fig_m_gain = px.bar(
                mach_df,
                x="machine_name",
                y="tasks_gained",
                color="machine_name",
                text=mach_df["tasks_gained"].round(1),
                title="Tarefas Ganhas por Máquina",
                labels={"machine_name": "Máquina", "tasks_gained": "Tarefas ganhas"},
            )
            fig_m_gain.update_traces(textposition="outside")
            st.plotly_chart(fig_m_gain, use_container_width=True)

        with m2:
            fig_m_time = px.bar(
                mach_df,
                x="machine_name",
                y="heuristic_time_mean",
                color="machine_name",
                text=mach_df["heuristic_time_mean"].map(lambda v: f"{v:.3f}s"),
                title="Tempo Médio de Execução da Heurística por Máquina",
                labels={
                    "machine_name": "Máquina",
                    "heuristic_time_mean": "Tempo médio (s)",
                },
            )
            fig_m_time.update_traces(textposition="outside")
            st.plotly_chart(fig_m_time, use_container_width=True)

        st.dataframe(mach_df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # Aba 4: Dados Detalhados
    # -------------------------------------------------------------------------
    with tab_data:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar dados filtrados (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="baseline_vs_heuristic_filtrado.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
