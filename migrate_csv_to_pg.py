import os
import pandas as pd
from sqlalchemy import create_engine

FILES = {
    "activities_raw":   "data/activities.csv",
    "activities_clean": "data/activities_clean.csv",
    "activities_map":   "data/activities_map.csv",
}

def main():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    for table, path in FILES.items():
        df = pd.read_csv(path)
        df.to_sql(table, engine, if_exists="replace", index=False)
        print(f"OK: {table} ({len(df)} lignes) <- {path}")

if __name__ == "__main__":
    main()