"""Construit la table par-km en agrégeant les streams de chaque activité,
et l'écrit dans Postgres.

Chaque ligne = un km d'une sortie. Le dernier km incomplet est conservé
avec un flag is_partial=True.
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

CACHE_DIR = Path("data/streams")


def get_engine():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)


def build_km_rows(activity_id, stream_df):
    """Découpe un stream en tranches de 1km et calcule les métriques par tranche."""
    if stream_df.empty or "distance" not in stream_df.columns:
        return []

    # Index du km : 0 = premier km, 1 = deuxième km, ...
    stream_df = stream_df.copy()
    stream_df["km_index"] = (stream_df["distance"] // 1000).astype(int)

    total_distance_m = stream_df["distance"].max()
    max_km = int(total_distance_m // 1000)  # dernier km complet

    rows = []
    for km_idx, group in stream_df.groupby("km_index"):
        if len(group) < 2:
            continue

        # Métriques distance/temps
        dist_covered = group["distance"].iloc[-1] - group["distance"].iloc[0]
        time_elapsed = group["time"].iloc[-1] - group["time"].iloc[0]
        pace_min_per_km = (time_elapsed / 60) / (dist_covered / 1000) if dist_covered > 0 else None

        # Métriques dénivelé
        if "altitude" in group.columns:
            alt = group["altitude"].values
            deltas = np.diff(alt)
            elev_gain_m = float(deltas[deltas > 0].sum()) if len(deltas) else 0.0
            elev_loss_m = float(-deltas[deltas < 0].sum()) if len(deltas) else 0.0
            elev_delta_m = float(alt[-1] - alt[0])
            avg_grade_pct = (elev_delta_m / dist_covered * 100) if dist_covered > 0 else None
        else:
            elev_gain_m = elev_loss_m = elev_delta_m = avg_grade_pct = None

        # HR et cadence (peuvent être absentes)
        avg_hr = float(group["heartrate"].mean()) if "heartrate" in group.columns else None
        avg_cad = float(group["cadence"].mean()) if "cadence" in group.columns else None

        # État d'avancement dans la sortie
        distance_before_km = km_idx * 1000.0  # metres parcourus avant ce km

        # Flag partiel : le dernier km n'est complet que si sa distance >= 1000m
        is_partial = (km_idx == max_km) and (dist_covered < 1000)

        rows.append({
            "activity_id": activity_id,
            "km_index": int(km_idx) + 1,  # 1-indexed dans la table
            "km_distance_m": float(dist_covered),
            "pace_min_per_km": float(pace_min_per_km) if pace_min_per_km else None,
            "elev_gain_m": elev_gain_m,
            "elev_loss_m": elev_loss_m,
            "elev_delta_m": elev_delta_m,
            "avg_grade_pct": float(avg_grade_pct) if avg_grade_pct is not None else None,
            "avg_heartrate": avg_hr if avg_hr is not None and not pd.isna(avg_hr) else None,
            "avg_cadence": avg_cad if avg_cad is not None and not pd.isna(avg_cad) else None,
            "distance_before_km": distance_before_km,
            "is_partial": bool(is_partial),
        })

    # Après, calculer fraction_completed et elev_gain_before
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

    # Écriture dans Postgres
    engine = get_engine()
    df_km.to_sql("activities_km", engine, if_exists="replace", index=False)
    print(f"\nTable 'activities_km' écrite dans Postgres.")

    # Petit check post-écriture
    with engine.connect() as conn:
        from sqlalchemy import text
        n = conn.execute(text("SELECT COUNT(*) FROM activities_km")).scalar()
        print(f"  Vérification : {n} lignes dans la table.")


if __name__ == "__main__":
    main()