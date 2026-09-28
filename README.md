# StravAnalytics

Full-stack data science dashboard analysant les données de course Strava, doublant comme
projet académique **TZ à l'UTC Compiègne** (6 ECTS, encadré par M. Benjamin Quost, filière
IAD, semestre A26).

## Live demo

👉 **[stravanalytics.slaskibert.fr](https://stravanalytics.slaskibert.fr)** (self-hosted sur VPS OVH via Coolify)

⚠️ Bug connu sur Firefox 155 (compression zstd HTTP/3). Utiliser Chrome ou Edge en attendant.

## Question de recherche TZ

*Comment l'allure instantanée en course s'explique-t-elle par le contexte local et l'état
d'avancement dans la sortie ?*

## Setup local

Prérequis : Python 3.10+, un compte Strava, un tunnel SSH vers la base Postgres du VPS.

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# Copier .env.example en .env et remplir les credentials
cp .env.example .env

# Ouvrir le tunnel SSH vers Postgres (dans un terminal dédié à garder ouvert)
./tunnel.ps1
```

## Usage

1. Créer une app Strava sur https://www.strava.com/settings/api
2. Remplir `.env` avec `CLIENT_ID`, `CLIENT_SECRET`, `DATABASE_URL`
3. `python src/auth.py` — authentification OAuth
4. `python src/fetch.py` — récupération des activités (CSV)
5. `python migrate_csv_to_pg.py` — sync CSV → Postgres
6. `python src/fetch_streams.py` — récupération des streams API par activité (Parquet local)
7. `python src/build_km_table.py` — construction de la table par-km dans Postgres
8. `streamlit run streamlit_app/app.py` — lancement du dashboard local

## Structure du projet

```
StravAnalytics/
├── src/
│ ├── auth.py # OAuth Strava
│ ├── fetch.py # Récupération activités (CSV)
│ ├── fetch_streams.py # Récupération streams API (Parquet)
│ └── build_km_table.py # Construction table par-km (Postgres)
├── migrate_csv_to_pg.py # Sync CSV → Postgres
├── notebooks/
│ ├── 01_exploration.ipynb # Nettoyage et feature engineering
│ ├── 02_exploration_km.ipynb # Premiers plots par-km
│ ├── 03_verif_km.ipynb # Vérification cohérence table par-km
│ ├── 04_exploration_par_sortie.ipynb # Exploration agrégée (histos, boxplots, corr)
│ ├── 05_acp.ipynb # ACP normée sur variables par-sortie
│ └── 06_heatmap_allure.ipynb # Heatmap allure intra-sortie
├── streamlit_app/
│ ├── app.py # Dashboard principal
│ ├── utils.py # Load Postgres, format, constantes
│ └── pages/
│ ├── 1_Vue_générale.py
│ ├── 2_Distances.py
│ ├── 3_Carte.py
│ ├── 4_Activités.py
│ └── 5_Détail.py
├── docs/
│ ├── journal-de-bord-TZ.md # Journal des séances TZ
│ ├── session-2026-09-30.md # Prépa séance du 30/09
│ └── biblio/ # Fiches de lecture + synthèse (Zotero pour les BibTeX)
│ ├── README.md
│ ├── synthesis.md
│ └── notes/
├── data/ # Local uniquement (non versionné à terme)
└── tunnel.ps1 # Ouverture tunnel SSH vers Postgres du VPS
```


## Stack technique

- **Langages/libs** : Python 3.10, Pandas, Scikit-learn, Plotly, Matplotlib, Seaborn, Streamlit, Folium, stravalib, Open-Meteo API
- **Données** : Strava API (activités + flux/streams), Parquet local pour les streams, Postgres 18 pour les tables agrégées
- **Infra** : VPS OVH + Coolify + Docker + domaine slaskibert.fr
- **Dev env** : VS Code + WSL2/Windows, Git/GitHub

## Roadmap

### ✅ V1.0.0 — Terminé
- [x] Pipeline OAuth2 Strava + refresh token
- [x] Cleaning et feature engineering
- [x] Dashboard Streamlit multi-pages
- [x] Déploiement initial Streamlit Cloud
- [x] Enrichissement météo Open-Meteo

### ✅ V2.0.0 — Terminé (été-automne 2026)
- [x] Migration vers self-hosting (Coolify + Docker + VPS OVH)
- [x] Passage de CSV local à Postgres 18
- [x] Récupération des streams API Strava (cache Parquet)
- [x] Construction de la table par-km (`build_km_table.py`)
- [x] Vérification et fiabilisation des données par-km (moving_time reconstruit, D+ lissé)

### 🚧 TZ (S1 2026) — En cours
- [x] Exploration agrégée (histos, boxplots, matrice corr, outliers)
- [x] ACP normée sur variables par-sortie (v4 finale, 7 variables actives)
- [x] Heatmap V1 de l'allure normalisée intra-sortie
- [x] Bibliographie physio et méthodologique (5 refs + synthèse)
- [ ] Rapport LaTeX (soutenance avant Noël)
- [ ] Modélisation prédictive de l'allure au niveau km

### Court terme
- [ ] Automatisation du fetch et build (scheduler)
- [ ] Visualisations temporelles supplémentaires (heure, jour, saison)
- [ ] Page Analyse dans le dashboard (corrélations, ACP interactive)
- [ ] Détection automatique du type de séance (endurance / seuil / VMA)

### Moyen terme
- [ ] Modèle ML de prédiction du suffer score
- [ ] Courbes de progression avec projection future
- [ ] Score de forme sur 4 dernières semaines (volume + allure)
- [ ] Application du seuil SWC 2.2-2.6% aux indicateurs longitudinaux
- [ ] Flag "précision dégradée" pour tout segment < 200m

### Long terme
- [ ] Commentaire IA sur la situation actuelle (LLM)
- [ ] Internationalisation (FR/EN)
- [ ] Multi-utilisateurs (authentification, tokens personnalisés)
- [ ] Suggestions de sorties types pour la prochaine course

## Contexte académique

Ce projet fait l'objet d'une **TZ** (unité de valeur UTC pour un projet personnel encadré,
6 ECTS PSF/CS), encadré par M. Benjamin Quost. Rendu attendu avant Noël 2026 :
- Rapport technique (format SY09-like)
- Soutenance devant M. Quost et un second examinateur
- Dashboard utilisable comme démonstration

Consulter `docs/journal-de-bord-TZ.md` pour le suivi des séances et
`docs/biblio/synthesis.md` pour le positionnement scientifique.