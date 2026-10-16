"""
Orchestration de la pipeline StravAnalytics.

Enchaîne, dans l'ordre :
  1. fetch.py            → actualise les CSV depuis l'API Strava
  2. migrate_csv_to_pg   → pousse les CSV vers Postgres (raw/clean/map)
  3. fetch_streams       → cache les streams des nouvelles activités (incrémental)
  4. build_km_table      → agrège streams → activities_km
  5. enrich_features     → calcule features de forme → activities_enriched

Chaque étape qui échoue stoppe la chaîne et affiche l'erreur.

Usage :
    python src/refresh_pipeline.py
    python src/refresh_pipeline.py --skip-fetch   # si tu veux juste rejouer l'enrichissement
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# S'assurer que les dossiers d'écriture existent (utile en prod Docker)
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "streams").mkdir(exist_ok=True)

STEPS = [
    ("fetch",    [sys.executable, "-u", "src/fetch.py"],            "Récupération API Strava"),
    ("clean",    [sys.executable, "-u", "src/clean.py"],            "Filtrage Run + enrichissement météo"),
    ("migrate",  [sys.executable, "-u", "migrate_csv_to_pg.py"],    "CSV → Postgres (raw/clean/map)"),
    ("streams",  [sys.executable, "-u", "src/fetch_streams.py"],    "Streams par activité"),
    ("km_table", [sys.executable, "-u", "src/build_km_table.py"],   "Agrégation par km"),
    ("enrich",   [sys.executable, "-u", "src/enrich_features.py"],  "Features de forme"),
]


def run_step(name, cmd, label):
    print(f"\n{'='*70}")
    print(f"▶ {name.upper():<10} — {label}")
    print(f"  {' '.join(cmd)}")
    print("=" * 70)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    dt = time.time() - t0
    if result.returncode != 0:
        print(f"\n✗ ÉCHEC étape '{name}' (code {result.returncode}), arrêt de la pipeline.")
        sys.exit(result.returncode)
    print(f"\n✓ OK en {dt:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Saute fetch + migrate (si tu as juste modifié enrich)")
    ap.add_argument("--only", choices=[s[0] for s in STEPS],
                    help="Lance une seule étape")
    args = ap.parse_args()

    t_start = time.time()

    if args.only:
        for name, cmd, label in STEPS:
            if name == args.only:
                run_step(name, cmd, label)
                break
    else:
        for name, cmd, label in STEPS:
            if args.skip_fetch and name in ("fetch", "migrate"):
                print(f"\n⇢ SKIP {name}")
                continue
            run_step(name, cmd, label)

    print(f"\n{'='*70}")
    print(f"✓ PIPELINE COMPLÈTE en {time.time()-t_start:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()