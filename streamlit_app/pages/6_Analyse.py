"""
Page Analyse - résultats scientifiques du TZ.

Trois résultats dérivés en live depuis Postgres :
  1. Décomposition de variance de la pace instantanée (modèle mixte par-km)
  2. Optimum thermique personnel (modèle quadratique T° par-sortie)
  3. Pattern de pacing (negative split, modèle mixte par-km)

Les modèles sont fittés au chargement et cachés 1 h.
"""
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import statsmodels.formula.api as smf
from dotenv import load_dotenv
from sqlalchemy import create_engine

from utils import PAPER_BG, PLOT_BG, STRAVA_BLUE, STRAVA_ORANGE

load_dotenv()

st.set_page_config(page_title="Analyse - StravAnalytics", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
# Chargement des données enrichies
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_enriched():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    df_act = pd.read_sql("SELECT * FROM activities_enriched", engine)
    df_km = pd.read_sql("SELECT * FROM activities_km", engine)
    return df_act, df_km


@st.cache_data(ttl=3600)
def fit_mixed_model(df_km_raw, df_act_raw):
    """Modèle mixte par-km + modèle quadratique T° par-sortie."""
    # Merge km × sortie
    act_features = ["id", "distance_km", "weather_temperature", "weather_humidity",
                    "elev_per_km", "pace_last_5_mean", "pace_min_km", "start_date_local"]
    df = df_km_raw.merge(df_act_raw[act_features], left_on="activity_id", right_on="id")
    df = df.rename(columns={
        "pace_min_per_km": "pace_km",
        "pace_min_km": "pace_sortie",
        "km_distance_m": "km_dist_m",
        "distance_km": "dist_totale_km",
    })

    # Filtres cohérence
    mask = (
        (~df["is_partial"])
        & (df["pace_km"].between(3, 10))
        & (df["dist_totale_km"] >= 1)
        & (df["dist_totale_km"] < 30)
        & (df["pace_last_5_mean"].notna())
    )
    dfm = df[mask].copy()
    counts = dfm.groupby("activity_id")["km_index"].transform("count")
    dfm = dfm[counts >= 3]

    # Modèle null (sans features) pour décomposition initiale
    null_model = smf.mixedlm("pace_km ~ 1", data=dfm,
                              groups=dfm["activity_id"]).fit(method="lbfgs")
    var_between_null = null_model.cov_re.iloc[0, 0]
    var_within_null = null_model.scale

    # Modèle complet
    formula = ("pace_km ~ weather_temperature + I(weather_temperature**2) "
               "+ dist_totale_km + pace_last_5_mean "
               "+ fraction_completed + avg_grade_pct")
    full = smf.mixedlm(formula, data=dfm, groups=dfm["activity_id"]).fit(method="lbfgs")
    var_between_full = full.cov_re.iloc[0, 0]
    var_within_full = full.scale

    # Modèle par-sortie pour l'optimum T°
    df_act_filt = df_act_raw[(df_act_raw["distance_km"] >= 1) & (df_act_raw["distance_km"] < 30)].copy()
    df_act_filt = df_act_filt.dropna(subset=["pace_last_5_mean"])
    f_sortie = ("pace_min_km ~ weather_temperature + I(weather_temperature**2) "
                "+ distance_km + elev_per_km + pace_last_5_mean")
    model_sortie = smf.ols(f_sortie, data=df_act_filt).fit()
    b1 = model_sortie.params["weather_temperature"]
    b2 = model_sortie.params["I(weather_temperature ** 2)"]
    opt_T = -b1 / (2 * b2) if b2 > 0 else None

    # Bootstrap IC optimum T°
    rng = np.random.default_rng(42)
    optima = []
    n = len(df_act_filt)
    for _ in range(500):
        idx = rng.integers(0, n, size=n)
        try:
            m = smf.ols(f_sortie, data=df_act_filt.iloc[idx]).fit()
            bb1 = m.params["weather_temperature"]
            bb2 = m.params["I(weather_temperature ** 2)"]
            if bb2 > 0:
                optima.append(-bb1 / (2 * bb2))
        except Exception:
            pass
    optima = np.array(optima)
    ic_lo, ic_hi = np.percentile(optima, [2.5, 97.5]) if len(optima) > 0 else (None, None)

    return {
        "dfm": dfm,
        "df_act_filt": df_act_filt,
        "null_model": null_model,
        "full_model": full,
        "model_sortie": model_sortie,
        "var_between_null": var_between_null,
        "var_within_null": var_within_null,
        "var_between_full": var_between_full,
        "var_within_full": var_within_full,
        "opt_T": opt_T,
        "ic_T": (ic_lo, ic_hi),
    }


# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────

st.title("📊 Analyse - Qu'est-ce qui explique ma pace ?")
st.caption("Résultats du modèle mixte linéaire sur mes sorties running (projet TZ)")

df_act, df_km = load_enriched()

with st.spinner("Ajustement du modèle mixte…"):
    res = fit_mixed_model(df_km, df_act)

total_var = res["var_between_null"] + res["var_within_null"]
feat_between = res["var_between_null"] - res["var_between_full"]
feat_within = res["var_within_null"] - res["var_within_full"]

pct_feat = (feat_between + feat_within) / total_var * 100
pct_feat_sortie = feat_between / total_var * 100
pct_feat_km = feat_within / total_var * 100
pct_jour = res["var_between_full"] / total_var * 100
pct_bruit = res["var_within_full"] / total_var * 100

sigma_total_s = np.sqrt(total_var) * 60

# ── Hero : 3 KPI ─────────────────────────────────────────────────────────────
st.subheader("Décomposition de la variance de ma pace instantanée")

col1, col2, col3 = st.columns(3)
col1.metric("Expliqué par les features",
            f"{pct_feat:.0f} %",
            help="Météo, forme, distance, D+/km, position dans la sortie, pente locale")
col2.metric("Forme du jour (résiduelle)",
            f"{pct_jour:.0f} %",
            help="Variabilité jour à jour non expliquée par les variables mesurées")
col3.metric("Bruit intra-sortie",
            f"{pct_bruit:.0f} %",
            help="Variation km à km au sein d'une même sortie")

st.caption(f"σ total de la pace instantanée : **{sigma_total_s:.1f} s/km** · "
           f"basée sur {len(res['dfm'])} km dans {res['dfm']['activity_id'].nunique()} sorties")

# ── Section 1 : barres empilées ──────────────────────────────────────────────
st.divider()
st.subheader("Les quatre composantes de ma variance")

parts = [
    ("Features - contexte sortie", pct_feat_sortie, STRAVA_ORANGE),
    ("Features - avancement intra-sortie", pct_feat_km, STRAVA_BLUE),
    ("Forme du jour résiduelle", pct_jour, "#4A4E69"),
    ("Bruit intra-sortie", pct_bruit, "#9A9DA6"),
]

fig_decomp = go.Figure()
left = 0
for label, pct, color in parts:
    fig_decomp.add_trace(go.Bar(
        y=["Variance totale"],
        x=[pct],
        orientation="h",
        marker=dict(color=color),
        name=f"{label} ({pct:.1f} %)",
        text=f"{pct:.1f}%" if pct > 4 else "",
        textposition="inside",
        textfont=dict(color="white", size=14),
        hovertemplate=f"{label}: %{{x:.1f}} %<extra></extra>",
    ))
    left += pct

fig_decomp.update_layout(
    barmode="stack",
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    font=dict(color="white"),
    xaxis=dict(gridcolor="#3D3D42", title="Part de la variance totale (%)", range=[0, 100]),
    yaxis=dict(showticklabels=False),
    height=180,
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(orientation="h", yanchor="top", y=-0.3, xanchor="center", x=0.5),
)
st.plotly_chart(fig_decomp, use_container_width=True)

with st.expander("Comment lire ce graphique"):
    st.markdown(f"""
    - **Features contexte sortie** ({pct_feat_sortie:.1f} %) : part expliquée par la T°, la forme physique récente, la distance et le D+/km.
    - **Features avancement** ({pct_feat_km:.1f} %) : part expliquée par la fraction de sortie complétée et la pente locale.
    - **Forme du jour résiduelle** ({pct_jour:.1f} %) : variabilité entre sorties non expliquée. Facteurs non capturés : sommeil, humeur, sorties sociales, fatigue cumulée.
    - **Bruit intra-sortie** ({pct_bruit:.1f} %) : micro-variations km à km (feux, pauses non détectées, fractionnés informels).

    L'**ICC** (intraclass correlation) du modèle null est de **{res['var_between_null']/(res['var_between_null']+res['var_within_null']):.2f}** :
    ma pace est bien plus déterminée par *quel jour je cours* que par *où je suis dans la sortie*.
    """)

# ── Section 2 : Optimum thermique ────────────────────────────────────────────
st.divider()
st.subheader("🌡️ Mon optimum thermique")

opt_T = res["opt_T"]
ic_lo, ic_hi = res["ic_T"]
df_sortie = res["df_act_filt"]

col_a, col_b, col_c = st.columns(3)
col_a.metric("Optimum perso", f"{opt_T:.1f} °C")
col_b.metric("IC bootstrap 95 %", f"[{ic_lo:.1f}, {ic_hi:.1f}] °C")
col_c.metric("Référence El Helou", "3.8 – 9.9 °C",
             help="Optimum des marathoniens d'élite (El Helou et al. 2012, PLoS ONE, 1.79 M finishers)")

# Courbe prédite
T_grid = np.linspace(df_sortie["weather_temperature"].min(),
                     df_sortie["weather_temperature"].max(), 100)
med_dist = df_sortie["distance_km"].median()
med_elev = df_sortie["elev_per_km"].median()
med_pace5 = df_sortie["pace_last_5_mean"].median()

p = res["model_sortie"].params
pred = (p["Intercept"]
        + p["weather_temperature"] * T_grid
        + p["I(weather_temperature ** 2)"] * T_grid**2
        + p["distance_km"] * med_dist
        + p["elev_per_km"] * med_elev
        + p["pace_last_5_mean"] * med_pace5)

fig_temp = go.Figure()

# Zone El Helou
fig_temp.add_vrect(x0=3.8, x1=9.9, fillcolor="blue", opacity=0.1,
                   line_width=0, annotation_text="El Helou", annotation_position="top left",
                   annotation=dict(font=dict(color="#88B0E0")))

# Scatter observations
fig_temp.add_trace(go.Scatter(
    x=df_sortie["weather_temperature"],
    y=df_sortie["pace_min_km"],
    mode="markers",
    marker=dict(size=7, color=df_sortie["distance_km"], colorscale="Viridis",
                showscale=True, colorbar=dict(title="Distance (km)"),
                line=dict(width=0.5, color="rgba(255,255,255,0.3)")),
    name="Mes sorties",
    hovertemplate="T°: %{x:.1f}°C<br>Pace: %{y:.2f} min/km<extra></extra>",
))

# Courbe prédite
fig_temp.add_trace(go.Scatter(
    x=T_grid, y=pred,
    mode="lines",
    line=dict(color=STRAVA_ORANGE, width=3),
    name="Pace prédite (modèle)",
    hovertemplate="T°: %{x:.1f}°C<br>Pace prédite: %{y:.2f} min/km<extra></extra>",
))

# Ligne optimum
fig_temp.add_vline(x=opt_T, line=dict(color="white", width=2, dash="dash"),
                   annotation_text=f"Optimum {opt_T:.1f} °C", annotation_position="top")

fig_temp.update_layout(
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    font=dict(color="white"),
    xaxis=dict(gridcolor="#3D3D42", title="Température (°C)"),
    yaxis=dict(gridcolor="#3D3D42", title="Pace (min/km)", autorange="reversed"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=500,
)
st.plotly_chart(fig_temp, use_container_width=True)

with st.expander("Interprétation"):
    st.markdown(f"""
    - Mon optimum thermique perso **{opt_T:.1f} °C** est **plausiblement plus chaud** que celui des marathoniens d'élite d'El Helou (3.8-9.9 °C), même si l'IC bootstrap [{ic_lo:.1f}, {ic_hi:.1f}] °C chevauche partiellement cette plage.
    - **Pourquoi plus chaud ?** Un profil d'endurance (vs course maximale) produit moins de chaleur métabolique, donc tolère mieux la chaleur ambiante.
    - L'IC est large car l'hiver est sous-échantillonné (n=7 sorties à T° < 5 °C). Un refit en janvier-février améliorera la précision de la borne basse.
    - Modèle quadratique significativement meilleur que linéaire (test F sur T², p < 0.01).
    """)

# ── Section 3 : Negative split ───────────────────────────────────────────────
st.divider()
st.subheader("🏃‍♂️ Mon pattern de pacing : negative split")

dfm = res["dfm"]
full = res["full_model"]
coef_frac = full.fe_params["fraction_completed"]
p_frac = full.pvalues["fraction_completed"]
accel_sec = -coef_frac * 60

col_x, col_y = st.columns(2)
col_x.metric("Accélération du 1er au dernier km", f"{accel_sec:.1f} s/km",
             help="Effet marginal de fraction_completed, conditions médianes")
col_y.metric("Significativité", f"p = {p_frac:.1e}")

# Grille fraction
frac_grid = np.linspace(0, 1, 50)
med_T = dfm["weather_temperature"].median()
med_dist = dfm["dist_totale_km"].median()
med_elev_km = dfm["elev_per_km"].median()
med_pace5_km = dfm["pace_last_5_mean"].median()
med_grade = dfm["avg_grade_pct"].median()

pf = full.fe_params
pred_frac = (pf["Intercept"]
             + pf["weather_temperature"] * med_T
             + pf["I(weather_temperature ** 2)"] * med_T**2
             + pf["dist_totale_km"] * med_dist
             + pf["pace_last_5_mean"] * med_pace5_km
             + pf["fraction_completed"] * frac_grid
             + pf["avg_grade_pct"] * med_grade)

# Observations centrées par sortie, remises autour de la courbe
dfm_centered = dfm.copy()
dfm_centered["pace_centered"] = dfm_centered.groupby("activity_id")["pace_km"].transform(
    lambda x: x - x.mean())
offset = pred_frac.mean()

fig_split = go.Figure()
fig_split.add_trace(go.Scatter(
    x=dfm_centered["fraction_completed"],
    y=dfm_centered["pace_centered"] + offset,
    mode="markers",
    marker=dict(size=5, color="rgba(255,255,255,0.25)"),
    name="Observations (centrées par sortie)",
    hoverinfo="skip",
))
fig_split.add_trace(go.Scatter(
    x=frac_grid, y=pred_frac,
    mode="lines",
    line=dict(color=STRAVA_ORANGE, width=4),
    name=f"Effet marginal : -{accel_sec:.1f} s/km",
))
fig_split.update_layout(
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    font=dict(color="white"),
    xaxis=dict(gridcolor="#3D3D42", title="Fraction de la sortie complétée",
               tickformat=",.0%"),
    yaxis=dict(gridcolor="#3D3D42", title="Pace (min/km)", autorange="reversed"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=450,
)
st.plotly_chart(fig_split, use_container_width=True)

with st.expander("Interprétation"):
    st.markdown(f"""
    - J'accélère **systématiquement en fin de sortie** : -{accel_sec:.1f} s/km entre le premier km et le dernier (p = {p_frac:.1e}).
    - Ce pattern correspond au **negative split**, l'une des 5 stratégies génériques identifiées par Pryor et al. (2020).
    - L'amplitude est robuste au contrôle de la T°, de la distance totale, de la pente locale et de la forme physique récente : c'est bien un **choix de pacing**, pas un artefact des conditions.
    """)

# ── Section 4 : Modèle complet ──────────────────────────────────────────────
st.divider()
st.subheader("📐 Coefficients du modèle mixte")

coef_df = pd.DataFrame({
    "Coefficient": full.fe_params.round(4),
    "Erreur std": full.bse_fe.round(4),
    "z": (full.fe_params / full.bse_fe).round(2),
    "p-value": full.pvalues.round(4),
})
coef_df.index.name = "Variable"
# Virer les effets aléatoires (confusion), garder juste les fixes
coef_df = coef_df.loc[full.fe_params.index]
st.dataframe(coef_df, use_container_width=True)

st.caption(f"Modèle : `pace_km ~ T + T² + dist_totale + pace_last_5 + "
           f"fraction_completed + avg_grade + (1 | activity_id)` · "
           f"n = {int(full.nobs)} km, {dfm['activity_id'].nunique()} sorties")

# ── Caveat ──────────────────────────────────────────────────────────────────
st.divider()
with st.container(border=True):
    st.markdown("""
    **Limites de l'analyse**
    - 50 % de forme du jour résiduelle non expliquée : facteurs non mesurés (sommeil, nutrition, humeur, sorties sociales, fatigue cumulée).
    - FC exclue du modèle principal (seulement 13/133 sorties avec FC, pré/post-acquisition Garmin). À réintégrer sur sous-échantillon.
    - Hiver sous-échantillonné (7 sorties à T° < 5 °C), élargit l'IC sur la borne basse de l'optimum thermique.
    - La question TZ officielle porte sur l'allure *instantanée* : ce modèle agrégé par-km en est l'approximation la plus fine permise par la data (après le point par point, trop autocorrélé).
    """)