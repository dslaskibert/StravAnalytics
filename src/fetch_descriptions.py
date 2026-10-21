"""Récupère les descriptions Strava manquantes (incrémental + rate-limit safe).

Rate-limit Strava : 100 req / 15min. On espace à 10s/call.
Checkpoint tous les 10 appels pour ne rien perdre en cas d'interruption.
"""
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from stravalib import Client
from stravalib.exc import RateLimitExceeded

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "activities.csv"
CACHE_PATH = ROOT / "data" / "activities_descriptions.csv"

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

SLEEP_BETWEEN_CALLS = 10.0  # s — rate-limit Strava : 100 req/15min
CHECKPOINT_EVERY = 10       # sauvegarde tous les N appels


def get_client():
    client = Client()
    client.access_token = os.getenv("STRAVA_ACCESS_TOKEN")
    client.refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")
    client.token_expires = int(os.getenv("STRAVA_TOKEN_EXPIRES_AT"))
    return client


def refresh_token(client):
    if time.time() > client.token_expires:
        print("Access token expired, refreshing...")
        token_response = client.refresh_access_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            refresh_token=os.getenv("STRAVA_REFRESH_TOKEN")
        )
        os.environ["STRAVA_ACCESS_TOKEN"] = token_response['access_token']
        os.environ["STRAVA_REFRESH_TOKEN"] = token_response['refresh_token']
        os.environ["STRAVA_TOKEN_EXPIRES_AT"] = str(token_response['expires_at'])


def save_checkpoint(df_cache, new_rows):
    """Fusionne new_rows avec df_cache et sauvegarde."""
    if not new_rows:
        return df_cache
    df_new = pd.DataFrame(new_rows)
    df_all = pd.concat([df_cache, df_new], ignore_index=True)
    df_all = df_all.drop_duplicates(subset="id", keep="last")
    df_all.to_csv(CACHE_PATH, index=False)
    return df_all


def main():
    client = get_client()
    refresh_token(client)

    df_act = pd.read_csv(RAW_PATH)
    df_act = df_act[df_act["sport_type"] == "Run"].copy()
    all_ids = set(df_act["id"].astype(int))
    print(f"{len(all_ids)} activités Run au total")

    try:
        df_cache = pd.read_csv(CACHE_PATH)
        cached_ids = set(df_cache["id"].astype(int))
        print(f"Descriptions déjà en cache : {len(cached_ids)}")
    except FileNotFoundError:
        df_cache = pd.DataFrame(columns=["id", "description"])
        cached_ids = set()
        print("Pas de cache existant, fetch complet.")

    to_fetch = sorted(all_ids - cached_ids)
    print(f"À fetcher : {len(to_fetch)} sorties (pacing : {SLEEP_BETWEEN_CALLS}s/call)\n")
    est_min = len(to_fetch) * SLEEP_BETWEEN_CALLS / 60
    print(f"Durée estimée : {est_min:.1f} min\n")

    new_rows = []
    for i, act_id in enumerate(to_fetch, 1):
        try:
            activity = client.get_activity(act_id)
            desc = activity.description if activity.description else ""
            new_rows.append({"id": int(act_id), "description": desc})
            preview = (desc[:60] + "...") if len(desc) > 60 else (desc or "(vide)")
            print(f"  [{i}/{len(to_fetch)}] {act_id} : {preview}")
        except RateLimitExceeded as e:
            print(f"\n⚠ RATE LIMIT atteint à {i-1}/{len(to_fetch)}. Sauvegarde et sortie.")
            df_cache = save_checkpoint(df_cache, new_rows)
            print(f"✓ {len(df_cache)} descriptions en cache. Relance le script dans 15 min.")
            return
        except Exception as e:
            print(f"  [{i}/{len(to_fetch)}] {act_id} : ERREUR — {e}")
            new_rows.append({"id": int(act_id), "description": None})

        # Checkpoint périodique
        if i % CHECKPOINT_EVERY == 0:
            df_cache = save_checkpoint(df_cache, new_rows)
            new_rows = []
            print(f"  ↳ checkpoint sauvegardé ({len(df_cache)} total)")

        time.sleep(SLEEP_BETWEEN_CALLS)

    # Sauvegarde finale
    df_cache = save_checkpoint(df_cache, new_rows)
    print(f"\n✓ OK : {CACHE_PATH} ({len(df_cache)} descriptions)")


if __name__ == "__main__":
    main()