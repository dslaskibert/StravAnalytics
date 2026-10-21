"""Construit la table par-km en agrégeant les streams de chaque activité,
et l'écrit dans Postgres.

Chaque ligne = un km d'une sortie. Le dernier km incomplet est conservé
avec un flag is_partial=True.

Corrections v2 (27/09/2026) :
- pace basé sur moving_time (filtrage sur stream 'moving') au lieu de elapsed
- D+ lissé (rolling mean) puis seuillé pour éliminer le bruit GPS
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

CACHE_DIR = Path("data/streams")

# Paramètres D+ lissé
ELEV_SMOOTH_WINDOW = 20      # nb de points de la fenêtre de lissage
ELEV_THRESHOLD_M   = 0.01    # filtre le bruit résiduel post-lissage (seuil absolu, adapté à l'enregistrement 1 Hz à ~3 m/s)
# Paramètre : vitesse en dessous de laquelle on considère qu'on ne bouge pas
MOVING_SPEED_THRESHOLD_MS = 0.3  # m/s ≈ 1.8 km/h (marche très lente)


def get_engine():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)


def compute_moving_time(group):
    """Somme les intervalles de temps où on est en mouvement.

    On reconstruit 'moving' à partir de la vitesse instantanée :
    speed[i] = (distance[i+1] - distance[i]) / (time[i+1] - time[i])
    Un intervalle est "moving" si speed > MOVING_SPEED_THRESHOLD_MS.

    Approche défendable : c'est ce que Strava fait en interne pour ses
    splits (elle ne se sert pas de l'accéléromètre).
    """
    if len(group) < 2:
        return 0.0

    times = group["time"].values.astype(float)
    dists = group["distance"].values.astype(float)

    dt = np.diff(times)
    dd = np.diff(dists)

    # Vitesse instantanée sur chaque intervalle
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = np.where(dt > 0, dd / dt, 0)

    is_moving = speed > MOVING_SPEED_THRESHOLD_MS
    return float(dt[is_moving].sum())


def compute_elev_smoothed(altitude_values, window=ELEV_SMOOTH_WINDOW, threshold_m=ELEV_THRESHOLD_M):
    """Calcule D+, D-, delta net et pente moyenne avec lissage + seuil.

    Approche Strava-like :
    1. Lisser la série d'altitude (rolling mean centrée)
    2. Ne compter que les variations > threshold_m entre points lissés consécutifs
    """
    if len(altitude_values) < 2:
        return 0.0, 0.0, 0.0

    # Lissage
    alt_s = pd.Series(altitude_values).rolling(
        window=window, center=True, min_periods=1
    ).mean().values

    deltas = np.diff(alt_s)
    gain = float(deltas[deltas > threshold_m].sum())
    loss = float(-deltas[deltas < -threshold_m].sum())
    net = float(alt_s[-1] - alt_s[0])
    return gain, loss, net


def build_km_rows(activity_id, stream_df):
    """Découpe un stream en tranches de 1km et calcule les métriques par tranche."""
    if stream_df.empty or "distance" not in stream_df.columns:
        return []

    stream_df = stream_df.copy()
    stream_df["km_index"] = (stream_df["distance"] // 1000).astype(int)

    total_distance_m = stream_df["distance"].max()
    max_km = int(total_distance_m // 1000)  # dernier km complet

    rows = []
    for km_idx, group in stream_df.groupby("km_index"):
        if len(group) < 2:
            continue

        # Distance parcourue dans ce km
        dist_covered = group["distance"].iloc[-1] - group["distance"].iloc[0]

        # --- TEMPS : moving_time uniquement (fix v2) ---
        moving_time_s = compute_moving_time(group)
        pace_min_per_km = (
            (moving_time_s / 60) / (dist_covered / 1000)
            if dist_covered > 0 and moving_time_s > 0 else None
        )

        # --- DÉNIVELÉ : lissé + seuillé (fix v2) ---
        if "altitude" in group.columns:
            alt_vals = group["altitude"].values
            elev_gain_m, elev_loss_m, elev_delta_m = compute_elev_smoothed(alt_vals)
            avg_grade_pct = (elev_delta_m / dist_covered * 100) if dist_covered > 0 else None
        else:
            elev_gain_m = elev_loss_m = elev_delta_m = avg_grade_pct = None

        # HR et cadence
        avg_hr = float(group["heartrate"].mean()) if "heartrate" in group.columns else None
        avg_cad = float(group["cadence"].mean()) if "cadence" in group.columns else None

        distance_before_km = km_idx * 1000.0
        is_partial = (km_idx == max_km) and (dist_covered < 1000)

        rows.append({
            "activity_id": activity_id,
            "km_index": int(km_idx) + 1,
            "km_distance_m": float(dist_covered),
            "pace_min_per_km": float(pace_min_per_km) if pace_min_per_km else None,
            "moving_time_s": float(moving_time_s),  # NOUVEAU : utile pour vérifs
            "elev_gain_m": elev_gain_m,
            "elev_loss_m": elev_loss_m,
            "elev_delta_m": elev_delta_m,
            "avg_grade_pct": float(avg_grade_pct) if avg_grade_pct is not None else None,
            "avg_heartrate": avg_hr if avg_hr is not None and not pd.isna(avg_hr) else None,
            "avg_cadence": avg_cad if avg_cad is not None and not pd.isna(avg_cad) else None,
            "distance_before_km": distance_before_km,
            "is_partial": bool(is_partial),
        })

    # Fraction complétée et D+ cumulé
    total_km_effective = len(rows)
    cum_elev = 0.0
    for i, row in enumerate(rows):
        row["fraction_completed"] = (i + 1) / total_km_effective if total_km_effective else None
        row["elev_gain_before_m"] = cum_elev
        cum_elev += row["elev_gain_m"] or 0.0

    return rows


def main():
    stream_files = sorted(CACHE_DIR.glob("streams_*.parquet"))
    print(f"{len(stream_files)} fichiers de streams à traiter.")

    all_km_rows = []
    for i, path in enumerate(stream_files, 1):
        activity_id = int(path.stem.replace("streams_", ""))
        stream_df = pd.read_parquet(path)
        rows = build_km_rows(activity_id, stream_df)
        all_km_rows.extend(rows)
        if i % 20 == 0:
            print(f"  [{i}/{len(stream_files)}] traitées, {len(all_km_rows)} lignes km jusqu'ici")

    df_km = pd.DataFrame(all_km_rows)
    print(f"\nTable construite : {len(df_km)} lignes ({df_km['activity_id'].nunique()} sorties)")
    print(f"  Lignes partielles (is_partial=True) : {df_km['is_partial'].sum()}")

    engine = get_engine()
    df_km.to_sql("activities_km", engine, if_exists="replace", index=False)
    print(f"\nTable 'activities_km' écrite dans Postgres.")

    with engine.connect() as conn:
        from sqlalchemy import text
        n = conn.execute(text("SELECT COUNT(*) FROM activities_km")).scalar()
        print(f"  Vérification : {n} lignes dans la table.")


if __name__ == "__main__":
    main()