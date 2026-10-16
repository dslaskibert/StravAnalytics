import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import subprocess
import sys
from pathlib import Path

from utils import format_pace, load_data, STRAVA_ORANGE, STRAVA_BLUE, PLOT_BG, PAPER_BG

df = load_data()
df_enriched = load_data("data/activities_enriched.csv")

st.title("StravAnalytics 🏃")
st.header("Analyse de mes activités Strava")

col_r1, col_r2, col_r3 = st.columns([1, 1, 4])

with col_r1:
    if st.button("🔄 Recharger", help="Vide le cache serveur, relit la base Postgres (rapide)"):
        st.cache_data.clear()
        st.rerun()

with col_r2:
    if st.button("🔁 Depuis Strava",
                 help="Lance la pipeline complète : fetch Strava + enrichissement (~1 min)"):
        with st.spinner("Pipeline en cours — fetch, clean, migrate, streams, km, enrich..."):
            root = Path(__file__).resolve().parents[2]
            script = root / "src" / "refresh_pipeline.py"
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, cwd=str(root), timeout=300,
            )
            if result.returncode == 0:
                st.cache_data.clear()
                st.success("✓ Pipeline terminée, données à jour.")
                st.rerun()
            else:
                st.error(f"✗ Erreur pipeline :\n{result.stdout[-2000:]}\n{result.stderr[-1000:]}")

# ──────────────────────────────────────────────────────────────────────────────
# État actuel (cockpit) — recalculé à partir d'AUJOURD'HUI
# ──────────────────────────────────────────────────────────────────────────────

today = pd.Timestamp.now().normalize()
df["date_only"] = pd.to_datetime(df["start_date_local"]).dt.tz_localize(None).dt.floor("D")

last_run_date = df["date_only"].max()
days_since_last_run = (today - last_run_date).days

def vol_last_days(days):
    cutoff = today - pd.Timedelta(days=days)
    mask = df["date_only"] >= cutoff
    return df.loc[mask, "distance_km"].sum(), int(mask.sum())

vol_7d, n_7d = vol_last_days(7)
vol_14d, n_14d = vol_last_days(14)
vol_28d, n_28d = vol_last_days(28)
vol_90d, n_90d = vol_last_days(90)

# ACWR : charge aiguë 7j / charge chronique moyenne 28j (ramenée à 7j)
acwr_today = vol_7d / (vol_28d / 4) if vol_28d > 0 else None

# Pace moyenne des 5 dernières sorties réelles
df_sorted = df.sort_values("date_only")
pace_last_5 = df_sorted.tail(5)["pace_min_km"].mean()
pace_globale = df["pace_min_km"].mean()
delta_pace = pace_last_5 - pace_globale

# Jours depuis dernière sortie rapide
pace_mean = df["pace_min_km"].mean()
fast = df_sorted[df_sorted["pace_min_km"] < (pace_mean - 0.5)]
if len(fast) > 0:
    last_fast_date = fast["date_only"].max()
    days_since_fast = (today - last_fast_date).days
else:
    days_since_fast = None

# Monotonie des 28 derniers jours : mean(distance quotidienne) / std
cutoff_28 = today - pd.Timedelta(days=28)
df_28 = df[df["date_only"] >= cutoff_28]
daily_vol = df_28.groupby("date_only")["distance_km"].sum()
# Reindex avec tous les jours pour inclure les jours à 0
all_days = pd.date_range(cutoff_28, today, freq="D")
daily_vol = daily_vol.reindex(all_days, fill_value=0)
monotony = daily_vol.mean() / daily_vol.std() if daily_vol.std() > 0 else None


def acwr_status(acwr):
    if acwr is None or pd.isna(acwr):
        return "—"
    if acwr < 0.8:
        return "Sous-charge"
    if acwr <= 1.3:
        return "Zone optimale"
    if acwr <= 1.5:
        return "Zone de risque"
    return "Risque élevé"


st.subheader("🎯 État actuel de l'entraînement")
st.caption(f"Dernière sortie : {last_run_date.strftime('%d/%m/%Y')} · aujourd'hui : {today.strftime('%d/%m/%Y')}")

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Volume 7 derniers jours",
    f"{vol_7d:.1f} km",
    delta=f"{n_7d} sorties",
    delta_color="off",
)
col2.metric(
    "Volume 28 derniers jours",
    f"{vol_28d:.1f} km",
    delta=f"{n_28d} sorties",
    delta_color="off",
)
col3.metric(
    f"ACWR 7/28 — {acwr_status(acwr_today)}",
    f"{acwr_today:.2f}" if acwr_today is not None else "—",
    help="Charge aiguë 7j / charge chronique moyenne 28j. Zone optimale : 0.8 - 1.3",
)
col4.metric(
    "Jours depuis dernière sortie",
    f"{days_since_last_run} j",
    delta_color="off",
)

col5, col6, col7, col8 = st.columns(4)
col5.metric(
    "Pace moyenne récente (5 dernières)",
    format_pace(pace_last_5) if pd.notna(pace_last_5) else "—",
    delta=f"{format_pace(delta_pace)} vs globale",
    delta_color="inverse",
)
col6.metric(
    "Monotonie 28 j",
    f"{monotony:.2f}" if monotony is not None else "—",
    help="Mean(volumes journaliers) / std sur 28j. Plus haut = entraînement régulier.",
)
col7.metric(
    "Jours depuis dernière sortie rapide",
    f"{days_since_fast} j" if days_since_fast is not None else "—",
    help="Sortie plus rapide que ma moyenne - 0.5 min/km",
    delta_color="off",
)
col8.metric(
    "Volume 90 derniers jours",
    f"{vol_90d:.1f} km",
    delta=f"{n_90d} sorties",
    delta_color="off",
)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Évolution mensuelle (section existante)
# ──────────────────────────────────────────────────────────────────────────────

current_month = pd.Period(pd.Timestamp.now(), "M")
last_month = current_month - 1

runs_this_month = len(df[df["month"] == current_month])
runs_last_month = len(df[df["month"] == last_month])
distance_this_month = df[df["month"] == current_month]["distance_km"].sum()
distance_last_month = df[df["month"] == last_month]["distance_km"].sum()
pace_this_month = df[df["month"] == current_month]["pace_min_km"].mean()
pace_last_month = df[df["month"] == last_month]["pace_min_km"].mean()

st.subheader("📅 Ce mois-ci")

col1, col2, col3 = st.columns(3)

col1.metric(
    label="Courses ce mois",
    value=runs_this_month,
    delta=f"{runs_this_month - runs_last_month:+d} vs mois dernier"
)
col2.metric(
    label="Distance ce mois (km)",
    value=f"{distance_this_month:.1f}",
    delta=f"{distance_this_month - distance_last_month:+.1f} vs mois dernier"
)
col3.metric(
    label="Allure ce mois (min/km)",
    value=format_pace(pace_this_month) if pd.notna(pace_this_month) else "—",
    delta=format_pace(pace_this_month - pace_last_month) + " vs mois dernier" if pd.notna(pace_this_month) and pd.notna(pace_last_month) else None,
    delta_color="inverse"
)

st.divider()
st.subheader("🏅 Statistiques all time")

col1, col2, col3 = st.columns(3)
col1.metric("Nombre de courses", len(df))
col2.metric("Distance totale (km)", df["distance_km"].sum().round(2))
col3.metric("Allure moyenne globale (min/km)", format_pace(df["pace_min_km"].mean()))

st.divider()
st.subheader("📈 Évolution")

df_evolution = df.groupby("month").agg(
    total_distance=("distance_km", "sum"),
    mean_distance=("distance_km", "mean"),
    total_time=("moving_time_seconds", "sum")
).reset_index()

df_evolution["pace_ponderee"] = df_evolution["total_time"] / 60 / df_evolution["total_distance"]
df_evolution["month"] = df_evolution["month"].astype(str)

fig = go.Figure()

fig.update_layout(
    title="Évolution de l'allure et de la distance moyenne par mois",
    xaxis=dict(title="Mois", gridcolor="#3D3D42"),
    yaxis=dict(title="Allure (min/km)", gridcolor="#3D3D42"),
    yaxis2=dict(title="Distance moyenne (km)", overlaying="y", side="right"),
    legend=dict(x=0, y=1.1, orientation="h"),
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    font=dict(color="white")
)

fig.add_trace(go.Scatter(
    x=df_evolution["month"],
    y=df_evolution["pace_ponderee"],
    name="Allure (min/km)",
    mode="lines+markers",
    line=dict(color=STRAVA_ORANGE),
    marker=dict(color=STRAVA_ORANGE),
    yaxis="y1"
))

fig.add_trace(go.Scatter(
    x=df_evolution["month"],
    y=df_evolution["mean_distance"],
    name="Distance moyenne (km)",
    mode="lines+markers",
    line=dict(color=STRAVA_BLUE),
    marker=dict(color=STRAVA_BLUE),
    yaxis="y2"
))

st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Distance vs Allure")

fig_scatter = px.scatter(
    data_frame=df,
    x="distance_km",
    y="pace_min_km",
    color="year",
    hover_data=["name", "date", "distance_km", "pace_min_km"],
    title="Relation distance / allure par sortie",
    labels={
        "distance_km": "Distance (km)",
        "pace_min_km": "Allure (min/km)",
        "year": "Année"
    },
    color_discrete_sequence=[STRAVA_ORANGE, STRAVA_BLUE, "#A8E063"]
)

fig_scatter.update_layout(
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    font=dict(color="white"),
    xaxis=dict(gridcolor="#3D3D42"),
    yaxis=dict(gridcolor="#3D3D42"),
)

st.plotly_chart(fig_scatter, use_container_width=True)