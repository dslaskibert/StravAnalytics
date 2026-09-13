import streamlit as st
import pandas as pd
import ast
import os
from sqlalchemy import create_engine

# ── Couleurs Strava ──
STRAVA_ORANGE = "#FC4C02"
STRAVA_BLUE   = "#4FC3F7"
PLOT_BG       = "#2D2D32"
PAPER_BG      = "#242428"

@st.cache_resource
def _engine():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)

@st.cache_data(ttl=3600)
def load_data(path="data/activities_clean.csv"):
    # Traduit le chemin CSV historique en nom de table Postgres
    # ex: "data/activities_clean.csv" -> "activities_clean"
    table = os.path.splitext(os.path.basename(path))[0]
    df = pd.read_sql(f"SELECT * FROM {table}", _engine())
    if "month" in df.columns:
        df["month"] = df["month"].astype("period[M]")
    return df

def format_pace(pace_decimal):
    if pd.isna(pace_decimal):
        return "N/A"
    negative = pace_decimal < 0
    pace_decimal = abs(pace_decimal)
    minutes = int(pace_decimal)
    seconds = round((pace_decimal - minutes) * 60)
    return f"-{minutes}:{seconds:02d}" if negative else f"{minutes}:{seconds:02d}"

def parse_latlng(val):
    if pd.isna(val):
        return None
    val_parsed = ast.literal_eval(val)
    return tuple(val_parsed[0][1])