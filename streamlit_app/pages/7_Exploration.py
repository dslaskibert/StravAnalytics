import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from utils import format_pace, load_data, STRAVA_ORANGE, STRAVA_BLUE, PLOT_BG, PAPER_BG

df = load_data()
df_km = load_data("data/activities_km.csv")

st.title("🔎 Exploration")
st.caption("Mes données Strava sous tous les angles")

# Préparation commune
df["date_only"] = pd.to_datetime(df["start_date_local"]).dt.tz_localize(None).dt.floor("D")
df["year_int"] = df["date_only"].dt.year
df["month_num"] = df["date_only"].dt.month
df["month_name"] = df["date_only"].dt.strftime("%b")

def season_from_month(m):
    if m in [12, 1, 2]: return "Hiver"
    if m in [3, 4, 5]: return "Printemps"
    if m in [6, 7, 8]: return "Été"
    return "Automne"

df["season"] = df["month_num"].map(season_from_month)
df["elev_per_km"] = df["total_elevation_gain_m"] / df["distance_km"]

JOURS_ORDER = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
SAISON_ORDER = ["Hiver", "Printemps", "Été", "Automne"]
MONTHS_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ──────────────────────────────────────────────────────────────────────────────
# Section 1 : Rythme hebdomadaire
# ──────────────────────────────────────────────────────────────────────────────

st.header("📅 Rythme hebdomadaire")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Volume et allure par jour de semaine")
    by_day = df.groupby("day_of_week").agg(
        n=("id", "count"),
        total_km=("distance_km", "sum"),
        mean_pace=("pace_min_km", "mean"),
    ).reindex(JOURS_ORDER).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=by_day["day_of_week"], y=by_day["total_km"],
        name="Distance totale (km)",
        marker=dict(color=STRAVA_ORANGE),
        yaxis="y1",
        hovertemplate="%{x}<br>%{y:.0f} km<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=by_day["day_of_week"], y=by_day["mean_pace"],
        mode="lines+markers",
        name="Allure moyenne (min/km)",
        line=dict(color=STRAVA_BLUE, width=2),
        marker=dict(size=10),
        yaxis="y2",
        hovertemplate="%{x}<br>%{y:.2f} min/km<extra></extra>",
    ))
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(title="Distance totale (km)", gridcolor="#3D3D42"),
        yaxis2=dict(title="Allure (min/km)", overlaying="y", side="right",
                    showgrid=False, autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Heure de sortie préférée")
    by_hour = df.groupby("hour").size().reindex(range(24), fill_value=0).reset_index(name="n")
    by_hour.columns = ["hour", "n"]

    fig = go.Figure(go.Barpolar(
        r=by_hour["n"],
        theta=by_hour["hour"] * 15,
        width=15,
        marker=dict(color=by_hour["n"], colorscale="Oranges", showscale=False),
        hovertemplate="%{theta}°<br>%{r} sorties<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=PLOT_BG,
            angularaxis=dict(
                rotation=90, direction="clockwise",
                tickmode="array",
                tickvals=[i * 15 for i in range(24)],
                ticktext=[f"{i}h" for i in range(24)],
                gridcolor="#3D3D42",
            ),
            radialaxis=dict(gridcolor="#3D3D42", color="white"),
        ),
        paper_bgcolor=PAPER_BG, font=dict(color="white"),
        showlegend=False, height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Section 2 : Saisonnalité
# ──────────────────────────────────────────────────────────────────────────────

st.header("🌍 Saisonnalité")

st.subheader("Volume mensuel, année par année")
by_year_month = df.groupby(["year_int", "month_num"]).agg(
    total_km=("distance_km", "sum")
).reset_index()
by_year_month["month_name"] = by_year_month["month_num"].apply(lambda m: MONTHS_ORDER[m-1])

fig = go.Figure()
colors = [STRAVA_ORANGE, STRAVA_BLUE, "#A8E063", "#E040FB", "#FFC107"]
for i, year in enumerate(sorted(by_year_month["year_int"].unique())):
    sub = by_year_month[by_year_month["year_int"] == year].sort_values("month_num")
    fig.add_trace(go.Scatter(
        x=sub["month_num"], y=sub["total_km"],
        mode="lines+markers",
        name=str(year),
        line=dict(color=colors[i % len(colors)], width=2),
        marker=dict(size=8),
    ))
fig.update_layout(
    plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
    xaxis=dict(title="Mois", tickmode="array", tickvals=list(range(1, 13)),
               ticktext=MONTHS_ORDER, gridcolor="#3D3D42"),
    yaxis=dict(title="Distance totale (km)", gridcolor="#3D3D42"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=400,
)
st.plotly_chart(fig, use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Allure par saison")
    fig = px.box(df, x="season", y="pace_min_km", category_orders={"season": SAISON_ORDER},
                 color_discrete_sequence=[STRAVA_ORANGE],
                 labels={"season": "Saison", "pace_min_km": "Allure (min/km)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", autorange="reversed"),
        height=400, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Allure par mois")
    df_sorted_month = df.copy()
    df_sorted_month["month_abbr"] = df_sorted_month["month_num"].apply(lambda m: MONTHS_ORDER[m-1])
    fig = px.box(df_sorted_month, x="month_abbr", y="pace_min_km",
                 category_orders={"month_abbr": MONTHS_ORDER},
                 color_discrete_sequence=[STRAVA_BLUE],
                 labels={"month_abbr": "Mois", "pace_min_km": "Allure (min/km)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", autorange="reversed"),
        height=400, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Section 3 : Météo étendue
# ──────────────────────────────────────────────────────────────────────────────

st.header("🌦️ Météo étendue")

df_meteo = df.dropna(subset=["weather_temperature", "weather_humidity", "weather_precipitation"]).copy()

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("Allure vs humidité")
    fig = px.scatter(df_meteo, x="weather_humidity", y="pace_min_km",
                     trendline="ols",
                     hover_data=["name", "date_fr"],
                     labels={"weather_humidity": "Humidité (%)",
                             "pace_min_km": "Allure (min/km)"},
                     color_discrete_sequence=[STRAVA_ORANGE])
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", autorange="reversed"),
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Allure vs précipitations")
    bins = [-0.001, 0, 0.5, 2, 5, 20]
    labels = ["Sec", "0-0.5", "0.5-2", "2-5", "5+"]
    df_meteo["precip_bin"] = pd.cut(df_meteo["weather_precipitation"], bins=bins, labels=labels)
    by_precip = df_meteo.groupby("precip_bin", observed=True).agg(
        mean_pace=("pace_min_km", "mean"),
        n=("id", "count"),
    ).reset_index()
    fig = px.bar(by_precip, x="precip_bin", y="mean_pace",
                 text="n",
                 labels={"precip_bin": "Pluie (mm/h)", "mean_pace": "Allure moyenne (min/km)"},
                 color_discrete_sequence=[STRAVA_BLUE])
    fig.update_traces(texttemplate="%{text} sorties", textposition="outside")
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42"),
        height=350, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col3:
    st.subheader("Humidité par saison")
    fig = px.box(df_meteo, x="season", y="weather_humidity",
                 category_orders={"season": SAISON_ORDER},
                 color_discrete_sequence=["#A8E063"],
                 labels={"season": "Saison", "weather_humidity": "Humidité (%)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42"),
        height=350, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Dans quelles conditions je cours ?")
col1, col2, col3 = st.columns(3)
with col1:
    fig = px.histogram(df_meteo, x="weather_temperature", nbins=25,
                       color_discrete_sequence=[STRAVA_ORANGE],
                       labels={"weather_temperature": "Température (°C)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", title="Sorties"),
        height=280, title="Température",
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = px.histogram(df_meteo, x="weather_humidity", nbins=25,
                       color_discrete_sequence=[STRAVA_BLUE],
                       labels={"weather_humidity": "Humidité (%)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", title="Sorties"),
        height=280, title="Humidité",
    )
    st.plotly_chart(fig, use_container_width=True)

with col3:
    fig = px.histogram(df_meteo, x="weather_precipitation", nbins=15,
                       color_discrete_sequence=["#A8E063"],
                       labels={"weather_precipitation": "Précipitations (mm/h)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", title="Sorties"),
        height=280, title="Précipitations",
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Section 4 : Records et top sorties
# ──────────────────────────────────────────────────────────────────────────────

st.header("🏆 Records et top sorties")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Top 10 sorties les plus rapides")
    top_fast = df.nsmallest(10, "pace_min_km")[["date_fr", "name", "distance_km", "pace_min_km"]].copy()
    top_fast["pace_fmt"] = top_fast["pace_min_km"].apply(format_pace)
    top_fast = top_fast.rename(columns={
        "date_fr": "Date", "name": "Sortie",
        "distance_km": "Distance (km)", "pace_fmt": "Allure"
    })[["Date", "Sortie", "Distance (km)", "Allure"]]
    st.dataframe(top_fast, use_container_width=True, hide_index=True,
                 column_config={"Distance (km)": st.column_config.NumberColumn(format="%.2f")})

with col2:
    st.subheader("Top 10 sorties les plus longues")
    top_long = df.nlargest(10, "distance_km")[["date_fr", "name", "distance_km", "pace_min_km"]].copy()
    top_long["pace_fmt"] = top_long["pace_min_km"].apply(format_pace)
    top_long = top_long.rename(columns={
        "date_fr": "Date", "name": "Sortie",
        "distance_km": "Distance (km)", "pace_fmt": "Allure"
    })[["Date", "Sortie", "Distance (km)", "Allure"]]
    st.dataframe(top_long, use_container_width=True, hide_index=True,
                 column_config={"Distance (km)": st.column_config.NumberColumn(format="%.2f")})

st.subheader("Progression de ma meilleure allure dans le temps")
df_prog = df.sort_values("date_only").copy()
df_prog["pace_cummin"] = df_prog["pace_min_km"].cummin()

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df_prog["date_only"], y=df_prog["pace_min_km"],
    mode="markers", name="Allure par sortie",
    marker=dict(color=STRAVA_BLUE, size=5, opacity=0.5),
    hovertemplate="%{x|%d/%m/%Y}<br>%{y:.2f} min/km<extra></extra>",
))
fig.add_trace(go.Scatter(
    x=df_prog["date_only"], y=df_prog["pace_cummin"],
    mode="lines", name="Meilleure allure cumulée",
    line=dict(color=STRAVA_ORANGE, width=3),
    hovertemplate="%{x|%d/%m/%Y}<br>Record : %{y:.2f} min/km<extra></extra>",
))
fig.update_layout(
    plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
    xaxis=dict(title="Date", gridcolor="#3D3D42"),
    yaxis=dict(title="Allure (min/km)", gridcolor="#3D3D42", autorange="reversed"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=400,
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Section 5 : Dénivelé
# ──────────────────────────────────────────────────────────────────────────────

st.header("⛰️ Dénivelé")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Distribution du dénivelé par km")
    df_elev = df[df["elev_per_km"].notna() & (df["elev_per_km"] < 50)]  # exclut outliers trail
    fig = px.histogram(df_elev, x="elev_per_km", nbins=30,
                       color_discrete_sequence=[STRAVA_ORANGE],
                       labels={"elev_per_km": "Dénivelé par km (m/km)"})
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", title="Sorties"),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Médiane : {df_elev['elev_per_km'].median():.1f} m/km · Max : {df['elev_per_km'].max():.1f} m/km")

with col2:
    st.subheader("Allure vs pente locale (par km)")
    df_km_valid = df_km[(~df_km["is_partial"]) & (df_km["pace_min_per_km"].between(3, 10))].copy()
    sample = df_km_valid.sample(min(2000, len(df_km_valid)), random_state=0)
    fig = px.scatter(sample, x="avg_grade_pct", y="pace_min_per_km",
                     trendline="ols",
                     opacity=0.3,
                     labels={"avg_grade_pct": "Pente moyenne (%)",
                             "pace_min_per_km": "Allure (min/km)"},
                     color_discrete_sequence=[STRAVA_BLUE])
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG, font=dict(color="white"),
        xaxis=dict(gridcolor="#3D3D42"),
        yaxis=dict(gridcolor="#3D3D42", autorange="reversed"),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)
    corr = df_km_valid[["avg_grade_pct", "pace_min_per_km"]].corr().iloc[0, 1]
    st.caption(f"Corrélation pente-allure (par km) : r = {corr:.3f} · "
               f"cohérent avec Minetti (coût énergétique × pente)")