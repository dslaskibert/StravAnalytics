"""Récupère les streams (distance, altitude, HR, cadence) pour chaque
activité Run et les cache localement en Parquet.

Idempotent : ne re-télécharge pas ce qui est déjà en cache.
"""

import os
import time
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from stravalib import Client

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
CACHE_DIR = Path("data/streams")
STREAM_TYPES = ["time", "distance", "altitude", "heartrate", "cadence"]
RATE_LIMIT_SLEEP = 1.0  # 1s entre 2 appels -> 900 req/15min (sous les 1000)

def get_client():
    client = Client()
    client.access_token = os.getenv("STRAVA_ACCESS_TOKEN")
    client.refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")
    client.token_expires = int(os.getenv("STRAVA_TOKEN_EXPIRES_AT"))
    return client


def refresh_token_if_needed(client):
    if time.time() > client.token_expires:
        print("Access token expired, refreshing...")
        token = client.refresh_access_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            refresh_token=client.refresh_token,
        )
        client.access_token = token["access_token"]
        client.refresh_token = token["refresh_token"]
        client.token_expires = int(token["expires_at"])
        print("Token refreshed.")

def cache_path(activity_id):
    return CACHE_DIR / f"streams_{activity_id}.parquet"


def fetch_one_stream(client, activity_id):
    """Retourne un DataFrame (une ligne par seconde) ou None si vide."""
    streams = client.get_activity_streams(
        activity_id, types=STREAM_TYPES, resolution="high"
    )
    if not streams or "time" not in streams:
        return None

    data = {name: streams[name].data for name in streams if name in STREAM_TYPES}
    return pd.DataFrame(data)

def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Charger la liste des activités Run
    activities = pd.read_csv("data/activities.csv")
    runs = activities[activities["sport_type"] == "Run"]
    print(f"{len(runs)} activités Run à traiter.")

    client = get_client()

    fetched, skipped, empty, errors = 0, 0, 0, 0

    for i, row in enumerate(runs.itertuples(), 1):
        activity_id = row.id
        path = cache_path(activity_id)

        if path.exists():
            skipped += 1
            continue

        refresh_token_if_needed(client)

        try:
            df = fetch_one_stream(client, activity_id)
            if df is None or df.empty:
                print(f"  [{i}/{len(runs)}] {activity_id}: pas de stream (activité manuelle ?)")
                empty += 1
                continue

            df.to_parquet(path, index=False)
            fetched += 1
            print(f"  [{i}/{len(runs)}] {activity_id}: {len(df)} points -> {path.name}")

        except Exception as e:
            print(f"  [{i}/{len(runs)}] {activity_id}: ERREUR {e}")
            errors += 1

        time.sleep(RATE_LIMIT_SLEEP)

    print(f"\nBilan : {fetched} téléchargées, {skipped} déjà en cache, "
          f"{empty} sans stream, {errors} erreurs.")


if __name__ == "__main__":
    main()
