import streamlit as st
from dotenv import load_dotenv
load_dotenv()

vue_generale = st.Page("pages/1_Vue_générale.py", title="Vue générale", icon="🏃", default=True)
distances    = st.Page("pages/2_Distances.py",    title="Distances",    icon="📏")
carte        = st.Page("pages/3_Carte.py",        title="Carte",        icon="🗺️")
activites    = st.Page("pages/4_Activités.py",    title="Activités",    icon="📋")
detail       = st.Page("pages/5_Détail.py",       title="Détail",       icon="🔍")
analyse      = st.Page("pages/6_Analyse.py",      title="Analyse",      icon="📊")

pg = st.navigation([vue_generale, distances, carte, activites, detail, analyse])
pg.run()