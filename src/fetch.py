# Maintenant qu'on est authentifiés, on va récupérer toutes les activités.

# Charger les variables du .env
# Créer un client Strava avec le token d'accès
# Gérer le refresh automatique du token (expire toutes les 6h)
# Récupérer toutes les activités
# Les sauvegarder dans un fichier data/activities.csv

import os
import time
import pandas as pd
from dotenv import load_dotenv
from stravalib import Client

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

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
        print("Token refreshed successfully.")


def fetch_activities(client):
    refresh_token(client)

    activities_list_cleaned = []

    all_activities = client.get_activities()

    for activity in all_activities:
        activities_list_cleaned.append({

            # ===== IDENTIFIANTS =====
            "id": activity.id,
            "external_id": activity.external_id,
            "upload_id": activity.upload_id,

            # ===== INFOS GÉNÉRALES =====
            "name": activity.name,
            "sport_type": activity.sport_type.root,
            "type": activity.type.root,
            "workout_type": activity.workout_type,
            "private": activity.private,
            "visibility": activity.visibility,
            "manual": activity.manual,
            "commute": activity.commute,
            "trainer": activity.trainer,
            "flagged": activity.flagged,

            # ===== DATE / TEMPS =====
            "start_date": activity.start_date,
            "start_date_local": activity.start_date_local,
            "timezone": activity.timezone,
            "utc_offset": activity.utc_offset,

            "moving_time_seconds": int(activity.moving_time)
            if activity.moving_time else None,

            "elapsed_time_seconds": int(activity.elapsed_time)
            if activity.elapsed_time else None,

            # ===== DISTANCES / VITESSES =====
            "distance_m": float(activity.distance)
            if activity.distance else None,

            "average_speed_m_s": float(activity.average_speed)
            if activity.average_speed else None,

            "max_speed_m_s": float(activity.max_speed)
            if activity.max_speed else None,

            # ===== DÉNIVELÉ =====
            "total_elevation_gain_m": activity.total_elevation_gain,
            "elev_high_m": activity.elev_high,
            "elev_low_m": activity.elev_low,

            # ===== FRÉQUENCE CARDIAQUE =====
            "has_heartrate": activity.has_heartrate,
            "average_heartrate": activity.average_heartrate,
            "max_heartrate": activity.max_heartrate,

            # ===== CADENCE =====
            "average_cadence": activity.average_cadence,

            # ===== PUISSANCE =====
            "average_watts": activity.average_watts,
            "max_watts": activity.max_watts,
            "weighted_average_watts": activity.weighted_average_watts,
            "device_watts": activity.device_watts,
            "kilojoules": activity.kilojoules,

            # ===== SOCIAL =====
            "achievement_count": activity.achievement_count,
            "kudos_count": activity.kudos_count,
            "comment_count": activity.comment_count,
            "photo_count": activity.photo_count,
            "total_photo_count": activity.total_photo_count,
            "pr_count": activity.pr_count,

            # ===== EFFORT =====
            "suffer_score": activity.suffer_score,

            # ===== LOCALISATION =====
            "start_latlng": (
                list(activity.start_latlng)
                if activity.start_latlng else None
            ),

            "end_latlng": (
                list(activity.end_latlng)
                if activity.end_latlng else None
            ),

            "location_city": activity.location_city,
            "location_state": activity.location_state,
            "location_country": activity.location_country,

            # ===== MAP =====
            "map_id": activity.map.id if activity.map else None,
            "summary_polyline": (
                activity.map.summary_polyline
                if activity.map else None
            ),

            # ===== ÉQUIPEMENT =====
            "gear_id": activity.gear_id,
        })

    return activities_list_cleaned


def save_to_csv(activities_list_cleaned):
    df = pd.DataFrame(activities_list_cleaned)
    df.to_csv("data/activities.csv", index=False)
    print("Activities saved to data/activities.csv")


if __name__ == "__main__":
    client = get_client()
    activities = fetch_activities(client)
    save_to_csv(activities)
    print(f"Done! {len(activities)} activities saved.")