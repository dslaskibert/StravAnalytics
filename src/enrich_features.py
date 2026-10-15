"""
Enrichit activities_clean avec les features d'entraînement et de forme.
Sortie : table Postgres `activities_enriched`.

Usage :
    python src/enrich_features.py
"""
import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# -- Config
WINDOWS_VOL = [7, 14, 28, 90]
WINDOW_MONOTONY = 28
LAST_N_PACE = 5
FAST_THRESHOLD_MIN_KM = 0.5  # une sortie est "rapide" si pace < pace_mean - 0.5 min


def rolling_backward_sum(dates, values, days):
    """Somme glissante backward exclusive (ne compte pas la sortie elle-même)."""
    out = np.zeros(len(dates))
    d = dates.values
    v = np.asarray(values)
    for i in range(len(d)):
        mask = (d < d[i]) & (d >= d[i] - pd.Timedelta(days=days))
        out[i] = v[mask].sum()
    return out


def rolling_backward_count(dates, days):
    out = np.zeros(len(dates), dtype=int)
    d = dates.values
    for i in range(len(d)):
        mask = (d < d[i]) & (d >= d[i] - pd.Timedelta(days=days))
        out[i] = mask.sum()
    return out


def rolling_monotony(dates, values, days):
    """Monotonie = mean(volumes journaliers) / std sur fenêtre glissante."""
    out = np.full(len(dates), np.nan)
    d = dates.values
    v = np.asarray(values)
    for i in range(len(d)):
        mask = (d < d[i]) & (d >= d[i] - pd.Timedelta(days=days))
        if mask.sum() >= 3:
            daily = pd.Series(v[mask]).values
            if daily.std() > 0:
                out[i] = daily.mean() / daily.std()
    return out


def last_n_pace_mean(dates, paces, n):
    out = np.full(len(dates), np.nan)
    d = dates.values
    p = np.asarray(paces)
    for i in range(len(d)):
        past = p[(d < d[i])]
        if len(past) >= n:
            out[i] = past[-n:].mean()
        elif len(past) > 0:
            out[i] = past.mean()
    return out


def days_since_last_fast(dates, paces, threshold):
    out = np.full(len(dates), np.nan)
    d = dates.values
    p = np.asarray(paces)
    pace_global_mean = np.nanmean(p)
    fast_mask = p < (pace_global_mean - threshold)
    for i in range(len(d)):
        past_dates = d[(d < d[i]) & fast_mask]
        if len(past_dates) > 0:
            out[i] = (d[i] - past_dates.max()) / np.timedelta64(1, "D")
    return out


def main():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)

    print("Chargement activities_clean...")
    df = pd.read_sql("SELECT * FROM activities_clean", engine)
    print(f"  {len(df)} sorties")

    # Tri chronologique
    df["date_utc"] = pd.to_datetime(df["start_date_local"], utc=True)
    df = df.sort_values("date_utc").reset_index(drop=True)
    df["date_only"] = df["date_utc"].dt.floor("D").dt.tz_localize(None)

    # Features dérivées simples
    df["pause_ratio"] = df["pause_seconds"] / df["moving_time_seconds"]
    df["elev_per_km"] = df["total_elevation_gain_m"] / df["distance_km"]

    # Volumes glissants
    print("Calcul volumes glissants...")
    for w in WINDOWS_VOL:
        df[f"vol_{w}d_km"] = rolling_backward_sum(df["date_only"], df["distance_km"], w)
        df[f"n_runs_{w}d"] = rolling_backward_count(df["date_only"], w)

    # ACWR = charge aiguë (7j) / charge chronique (28j)
    df["acwr_7_28"] = df["vol_7d_km"] / df["vol_28d_km"].replace(0, np.nan)

    # Monotonie
    print("Calcul monotonie...")
    df["monotony_28d"] = rolling_monotony(df["date_only"], df["distance_km"], WINDOW_MONOTONY)

    # Temps depuis dernière sortie (sans fillna artefact)
    df["days_since_last"] = df["date_only"].diff().dt.days.astype(float)

    # Pace moyenne des N dernières sorties
    print(f"Calcul pace moyenne des {LAST_N_PACE} dernières sorties...")
    df["pace_last_5_mean"] = last_n_pace_mean(df["date_only"], df["pace_min_km"], LAST_N_PACE)

    # Jours depuis dernière sortie rapide
    print("Calcul jours depuis dernière sortie rapide...")
    df["days_since_last_fast"] = days_since_last_fast(
        df["date_only"], df["pace_min_km"], FAST_THRESHOLD_MIN_KM
    )

    # Nettoyage colonnes utilitaires avant push
    df = df.drop(columns=["date_utc", "date_only"])

    # Push Postgres
    print("\nPush activities_enriched...")
    df.to_sql("activities_enriched", engine, if_exists="replace", index=False)
    print(f"OK: activities_enriched ({len(df)} lignes, {len(df.columns)} colonnes)")

    # Récap
    new_cols = [c for c in df.columns if c.startswith(("vol_", "n_runs_", "acwr_",
                                                        "monotony_", "pace_last_",
                                                        "days_since_"))]
    new_cols += ["pause_ratio", "elev_per_km"]
    print(f"\nColonnes ajoutées : {new_cols}")
    print("\nStats des nouvelles features :")
    print(df[new_cols].describe().round(2))


if __name__ == "__main__":
    main()