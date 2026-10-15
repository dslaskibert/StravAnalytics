"""
Nettoyage des activités brutes + enrichissement météo.

Lit  : data/activities.csv (raw)
Écrit : data/activities_clean.csv (Run filtrées, enrichies)
        data/activities_map.csv (données géo pour la carte)

Météo : incrémental (ne refetch que les nouvelles sorties).

Usage :
    python src/clean.py
"""
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "streamlit_app"))
from utils import parse_latlng  # noqa: E402

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_COLS = ["weather_temperature", "weather_humidity",
                "weather_precipitation", "weather_code"]

JOURS_FR = {
    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
    "Thursday": "Jeudi", "Friday": "Vendredi",
    "Saturday": "Samedi", "Sunday": "Dimanche",
}
MOIS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

COLS_TO_DROP = [
    "external_id", "upload_id", "type", "start_date",
    "timezone", "workout_type", "private", "visibility",
    "commute", "trainer", "utc_offset", "has_heartrate",
    "average_cadence",
    "start_latlng", "end_latlng", "map_id",
    "summary_polyline", "gear_id",
    "location_city", "location_state", "location_country",
    "distance_m", "elapsed_time_seconds",
    "average_watts", "max_watts", "weighted_average_watts",
    "device_watts", "kilojoules",
    "kudos_count", "comment_count", "photo_count",
    "total_photo_count", "achievement_count",
    "coords", "lat", "lon",
]


def main():
    raw_path = ROOT / "data" / "activities.csv"
    clean_path = ROOT / "data" / "activities_clean.csv"
    map_path = ROOT / "data" / "activities_map.csv"

    # 0. Charger la raw
    df = pd.read_csv(raw_path)
    print(f"Raw totale : {len(df)} activités")

    # 1. Filtrer Run
    df = df[df["sport_type"] == "Run"].copy()
    print(f"Runs only : {len(df)} activités")

    # 2. Dates
    df["start_date_local"] = pd.to_datetime(df["start_date_local"], utc=True)

    # 3. Colonnes dérivées FR
    df["day_of_week"] = df["start_date_local"].dt.day_name().map(JOURS_FR)
    df["date_fr"] = df["start_date_local"].apply(
        lambda x: f"{x.day} {MOIS_FR[x.month]} {x.year}"
    )
    df["hour_fr"] = df["start_date_local"].apply(
        lambda x: f"{x.hour}h{x.minute:02d}"
    )
    df["date"] = df["start_date_local"].dt.date
    df["hour"] = df["start_date_local"].dt.hour
    df["month"] = df["start_date_local"].dt.tz_localize(None).dt.to_period("M")
    df["year"] = df["start_date_local"].dt.year

    # 4. Unités
    df["distance_km"] = df["distance_m"] / 1000
    df["pace_min_km"] = (1 / df["average_speed_m_s"]) / 60 * 1000
    df["pause_seconds"] = df["elapsed_time_seconds"] - df["moving_time_seconds"]

    # 5. df_map avant drop
    df_map = df[["id", "map_id", "summary_polyline",
                 "start_latlng", "end_latlng",
                 "location_city", "date"]].copy()

    # 5.5 Coords pour météo (temporaire)
    df["coords"] = df["start_latlng"].apply(parse_latlng)
    df["lat"] = df["coords"].apply(lambda x: x[0] if x else None)
    df["lon"] = df["coords"].apply(lambda x: x[1] if x else None)

    # 5.6 Enrichissement météo incrémental
    for col in WEATHER_COLS:
        df[col] = None

    try:
        df_existing = pd.read_csv(clean_path)
        existing_weather_cols = [c for c in WEATHER_COLS if c in df_existing.columns]
        if existing_weather_cols:
            df_existing = df_existing[["id"] + existing_weather_cols]
            df = df.drop(columns=existing_weather_cols, errors="ignore")
            df = df.merge(df_existing, on="id", how="left")
            print(f"Météo existante : {df['weather_temperature'].notna().sum()} sorties")
    except FileNotFoundError:
        print("Pas de fichier existant, fetch complet.")

    # Fetch météo pour les sorties sans données
    fetched = 0
    for idx, row in df.iterrows():
        if pd.notna(row.get("weather_temperature")):
            continue
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue

        params = {
            "latitude": row["lat"],
            "longitude": row["lon"],
            "start_date": str(row["date"]),
            "end_date": str(row["date"]),
            "hourly": ["temperature_2m", "relative_humidity_2m",
                       "precipitation", "weather_code"],
            "timezone": "Europe/Paris",
        }
        try:
            response = requests.get(WEATHER_URL, params=params).json()
            hour_idx = int(row["hour"])
            df.at[idx, "weather_temperature"] = response["hourly"]["temperature_2m"][hour_idx]
            df.at[idx, "weather_humidity"] = response["hourly"]["relative_humidity_2m"][hour_idx]
            df.at[idx, "weather_precipitation"] = response["hourly"]["precipitation"][hour_idx]
            df.at[idx, "weather_code"] = response["hourly"]["weather_code"][hour_idx]
            fetched += 1
            print(f"  Météo fetchée pour {row['date']} ({fetched})")
        except Exception as e:
            print(f"  Erreur météo idx {idx} : {e}")

    print(f"Météo fetchée pour {fetched} nouvelles sorties.")

    # 6. Drop colonnes inutiles
    df = df.drop(columns=[c for c in COLS_TO_DROP if c in df.columns])

    # 7. Sauvegarde
    df.to_csv(clean_path, index=False)
    df_map.to_csv(map_path, index=False)
    print(f"\nOK: activities_clean.csv ({len(df)} lignes)")
    print(f"OK: activities_map.csv ({len(df_map)} lignes)")


if __name__ == "__main__":
    main()