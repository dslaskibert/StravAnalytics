import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
import polyline
from streamlit_folium import st_folium
from utils import load_data, parse_latlng, format_pace, STRAVA_ORANGE, STRAVA_BLUE, PLOT_BG, PAPER_BG

# ── Chargement des données ──
df     = load_data()
df_map = load_data("data/activities_map.csv")
df_km  = load_data("data/activities_km.csv")

activity_id = st.session_state.get("selected_activity_id")

if activity_id is None:
    st.warning("Aucune sortie sélectionnée — retourne à la liste.")
    if st.button("← Retour à la liste"):
        st.switch_page("pages/4_Activités.py")
    st.stop()

activity     = df[df["id"] == activity_id].iloc[0]
activity_map = df_map[df_map["id"] == activity_id].iloc[0] if activity_id in df_map["id"].values else None
activity_km  = df_km[df_km["activity_id"] == activity_id].sort_values("km_index").copy()

# ── En-tête ──
col_back, col_title = st.columns([1, 8])
with col_back:
    if st.button("←"):
        st.switch_page("pages/4_Activités.py")
with col_title:
    st.title(activity["name"])
    st.caption(f"{activity['day_of_week']} {activity['date_fr']} à {activity['hour_fr']}")

# Badges flagged / manuel
badges = []
if activity["flagged"]:
    badges.append("⚠️ Flagged par Strava")
if activity["manual"]:
    badges.append("✍️ Saisie manuelle")
if badges:
    st.warning("  |  ".join(badges))

st.divider()

# ── Métriques principales ──
st.subheader("📊 Statistiques")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Distance", f"{activity['distance_km']:.2f} km")
col2.metric("Allure moyenne", format_pace(activity["pace_min_km"]))
col3.metric("Durée", f"{int(activity['moving_time_seconds'] // 60)}min {int(activity['moving_time_seconds'] % 60):02d}s")
col4.metric("Suffer score", f"{int(activity['suffer_score'])}" if pd.notna(activity["suffer_score"]) else "N/A")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Dénivelé total", f"{activity['total_elevation_gain_m']:.0f} m")
col6.metric("Point haut", f"{activity['elev_high_m']:.0f} m" if pd.notna(activity["elev_high_m"]) else "N/A")
col7.metric("Point bas", f"{activity['elev_low_m']:.0f} m" if pd.notna(activity["elev_low_m"]) else "N/A")
col8.metric("Allure max", format_pace(1 / activity["max_speed_m_s"] / 60 * 1000) if pd.notna(activity["max_speed_m_s"]) else "N/A")

col9, col10, col11, col12 = st.columns(4)
col9.metric("PR obtenus", f"{int(activity['pr_count'])}")
col10.metric("Pause", f"{int(activity['pause_seconds'])}s" if activity["pause_seconds"] > 0 else "Aucune")
col11.metric("FC moyenne", f"{int(activity['average_heartrate'])} bpm" if pd.notna(activity["average_heartrate"]) else "N/A")
col12.metric("FC max", f"{int(activity['max_heartrate'])} bpm" if pd.notna(activity["max_heartrate"]) else "N/A")

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Analyse par km
# ──────────────────────────────────────────────────────────────────────────────

km_complets = activity_km[~activity_km["is_partial"]].copy()

if len(km_complets) >= 3:
    st.subheader("📈 Analyse par kilomètre")

    # ── Classification pacing ──
    mean_pace = km_complets["pace_min_per_km"].mean()
    std_pace = km_complets["pace_min_per_km"].std()
    cv_pace = std_pace / mean_pace if mean_pace > 0 else 0

    # Fastest / slowest km
    fastest_idx = km_complets["pace_min_per_km"].idxmin()
    slowest_idx = km_complets["pace_min_per_km"].idxmax()
    fastest_km = int(km_complets.loc[fastest_idx, "km_index"])
    slowest_km = int(km_complets.loc[slowest_idx, "km_index"])
    fastest_pace = km_complets.loc[fastest_idx, "pace_min_per_km"]
    slowest_pace = km_complets.loc[slowest_idx, "pace_min_per_km"]

    # Negative/positive split : comparer 1er tiers et dernier tiers
    n = len(km_complets)
    first_third = km_complets.head(max(1, n // 3))["pace_min_per_km"].mean()
    last_third = km_complets.tail(max(1, n // 3))["pace_min_per_km"].mean()
    split_delta = last_third - first_third

    if cv_pace <= 0.05:
        split_type = "Even split"
        split_desc = "allure régulière du début à la fin (CV ≤ 5 %)"
        split_color = "🟦"
    elif split_delta < -0.1:
        split_type = "Negative split"
        split_desc = f"accélération en fin de sortie ({-split_delta*60:.0f} s/km plus rapide sur le dernier tiers)"
        split_color = "🟢"
    elif split_delta > 0.1:
        split_type = "Positive split"
        split_desc = f"ralentissement en fin de sortie ({split_delta*60:.0f} s/km plus lent sur le dernier tiers)"
        split_color = "🟠"
    else:
        split_type = "Allure stable"
        split_desc = f"faible variation entre 1er et dernier tiers ({split_delta*60:+.0f} s/km)"
        split_color = "🟦"

    col_a, col_b, col_c = st.columns(3)
    col_a.metric(f"{split_color} Stratégie de pacing", split_type, help=split_desc)
    col_b.metric("Km le plus rapide", f"km {fastest_km}", delta=format_pace(fastest_pace),
                 delta_color="off")
    col_c.metric("Km le plus lent", f"km {slowest_km}", delta=format_pace(slowest_pace),
                 delta_color="off")

    st.caption(f"CV pace : {cv_pace*100:.1f} % · 1er tiers : {format_pace(first_third)} · dernier tiers : {format_pace(last_third)}")

    # ── Figure pace par km + grade ──
    fig_km = go.Figure()

    # Barres pace
    bar_colors = []
    for i, row in km_complets.iterrows():
        if i == fastest_idx:
            bar_colors.append("#4CAF50")   # vert pour le plus rapide
        elif i == slowest_idx:
            bar_colors.append("#F44336")   # rouge pour le plus lent
        else:
            bar_colors.append(STRAVA_ORANGE)

    fig_km.add_trace(go.Bar(
        x=km_complets["km_index"],
        y=km_complets["pace_min_per_km"],
        marker=dict(color=bar_colors),
        name="Allure (min/km)",
        yaxis="y1",
        hovertemplate="Km %{x}<br>Allure : %{y:.2f} min/km<extra></extra>",
    ))

    # Ligne grade
    fig_km.add_trace(go.Scatter(
        x=km_complets["km_index"],
        y=km_complets["avg_grade_pct"],
        mode="lines+markers",
        line=dict(color=STRAVA_BLUE, width=2),
        marker=dict(size=8, color=STRAVA_BLUE),
        name="Pente moy. (%)",
        yaxis="y2",
        hovertemplate="Km %{x}<br>Pente : %{y:.1f} %<extra></extra>",
    ))

    # Ligne horizontale pace moyenne
    fig_km.add_hline(y=mean_pace, line=dict(color="white", width=1, dash="dash"),
                     annotation_text=f"Moyenne : {format_pace(mean_pace)}",
                     annotation_position="right", yref="y1")

    fig_km.update_layout(
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=PAPER_BG,
        font=dict(color="white"),
        xaxis=dict(title="Km", gridcolor="#3D3D42",
                   tickmode="linear", dtick=1),
        yaxis=dict(title="Allure (min/km)", gridcolor="#3D3D42",
                   autorange="reversed"),
        yaxis2=dict(title="Pente (%)", overlaying="y", side="right",
                    showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        barmode="group",
    )

    st.plotly_chart(fig_km, use_container_width=True)

    # ── FC et cadence si dispo ──
    if km_complets["avg_heartrate"].notna().any():
        st.markdown("##### Fréquence cardiaque et cadence par km")
        fig_hr = go.Figure()

        fig_hr.add_trace(go.Scatter(
            x=km_complets["km_index"],
            y=km_complets["avg_heartrate"],
            mode="lines+markers",
            line=dict(color="#E74C3C", width=2),
            marker=dict(size=8),
            name="FC (bpm)",
            yaxis="y1",
        ))

        if km_complets["avg_cadence"].notna().any():
            fig_hr.add_trace(go.Scatter(
                x=km_complets["km_index"],
                y=km_complets["avg_cadence"],
                mode="lines+markers",
                line=dict(color="#9B59B6", width=2),
                marker=dict(size=8),
                name="Cadence (ppm)",
                yaxis="y2",
            ))

        fig_hr.update_layout(
            plot_bgcolor=PLOT_BG,
            paper_bgcolor=PAPER_BG,
            font=dict(color="white"),
            xaxis=dict(title="Km", gridcolor="#3D3D42", tickmode="linear", dtick=1),
            yaxis=dict(title="FC (bpm)", gridcolor="#3D3D42"),
            yaxis2=dict(title="Cadence (ppm)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=350,
        )
        st.plotly_chart(fig_hr, use_container_width=True)
elif len(activity_km) > 0:
    st.info(f"Sortie trop courte pour une analyse par km détaillée ({len(km_complets)} km complets).")

st.divider()

# ── Carte GPS ──
if activity_map is not None and pd.notna(activity_map["summary_polyline"]):
    st.subheader("🗺️ Tracé GPS")
    coordinates = polyline.decode(activity_map["summary_polyline"])
    center      = coordinates[len(coordinates) // 2]

    m = folium.Map(location=center, zoom_start=14)

    # Tracé principal
    folium.PolyLine(
        locations=coordinates,
        color=STRAVA_ORANGE,
        weight=4,
        opacity=0.9
    ).add_to(m)

    # Marqueur départ
    folium.Marker(
        location=coordinates[0],
        popup="Départ",
        icon=folium.Icon(color="green", icon="play", prefix="fa")
    ).add_to(m)

    # Marqueur arrivée
    folium.Marker(
        location=coordinates[-1],
        popup="Arrivée",
        icon=folium.Icon(color="red", icon="stop", prefix="fa")
    ).add_to(m)

    st_folium(m, use_container_width=True, height=400)
else:
    st.info("Pas de tracé GPS disponible pour cette sortie.")

st.divider()

# ── Lien Strava ──
st.markdown(
    f'<a href="https://www.strava.com/activities/{activity_id}" target="_blank">'
    f'<button style="background-color:{STRAVA_ORANGE};color:white;border:none;'
    f'padding:8px 16px;border-radius:4px;cursor:pointer;font-size:14px;">'
    f'Voir sur Strava →</button></a>',
    unsafe_allow_html=True
)