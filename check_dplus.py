import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
engine = create_engine(os.environ['DATABASE_URL'].replace('postgres://', 'postgresql://', 1))

df_after = pd.read_sql('SELECT activity_id, SUM(elev_gain_m) AS dplus_km_sum FROM activities_km GROUP BY activity_id', engine)
df_strava = pd.read_sql('SELECT id AS activity_id, total_elevation_gain_m AS dplus_strava FROM activities_clean', engine)

cmp = df_after.merge(df_strava, on='activity_id')
cmp_f = cmp[cmp['dplus_strava'] > 10].copy()
cmp_f['ecart_pct'] = (cmp_f['dplus_km_sum'] - cmp_f['dplus_strava']) / cmp_f['dplus_strava'] * 100

print(f'N sorties : {len(cmp_f)}')
print(f'Ecart median : {cmp_f["ecart_pct"].median():.1f} %')
print(f'Ecart P25-P75 : {cmp_f["ecart_pct"].quantile(0.25):.1f} % -> {cmp_f["ecart_pct"].quantile(0.75):.1f} %')