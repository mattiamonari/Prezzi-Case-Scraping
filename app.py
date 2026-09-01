import streamlit as st

import os
import gzip
import shutil
import urllib.request

import requests

st.set_page_config(
    page_title="Portale OMI - Agenzia Entrate",
    page_icon="🏠",
    layout="centered"
)

# Costanti DB
DB_DIR = os.path.join(os.path.dirname(__file__), 'db')
DB_PATH = os.path.join(DB_DIR, 'quotazioni.db')

# ⚠️ INSERISCI QUI IL LINK DEL FILE GZIP DAL TUO HUGGING FACE DATASET 
# Esempio: "https://huggingface.co/datasets/tuonome/omi-data/resolve/main/quotazioni.db.gz"
HF_DATASET_URL = "INSERISCI_QUI_IL_LINK"

if not os.path.exists(DB_PATH) and HF_DATASET_URL != "INSERISCI_QUI_IL_LINK":
    os.makedirs(DB_DIR, exist_ok=True)
    with st.spinner("🔄 Primo avvio (o riavvio server): Download del database in corso..."):
        gz_path = DB_PATH + ".gz"
        try:
            # Download file con supporto per repository privati
            headers = {}
            if "HF_TOKEN" in st.secrets:
                headers["Authorization"] = f"Bearer {st.secrets['HF_TOKEN']}"
                
            with requests.get(HF_DATASET_URL, headers=headers, stream=True) as r:
                r.raise_for_status()
                with open(gz_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
            # Unzip file
            with gzip.open(gz_path, 'rb') as f_in:
                with open(DB_PATH, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Pulizia
            os.remove(gz_path)
            st.rerun() # Ricarica per pulire lo spinner
        except Exception as e:
            st.error(f"Errore durante il download del DB: {e}")
            st.stop()


st.title("🏠 Analisi Quotazioni OMI")

st.markdown("""
Benvenuto nella Dashboard di Analisi delle Quotazioni Immobiliari (OMI).

Questa applicazione è divisa in due sezioni principali. Usa il menù di navigazione laterale a sinistra per spostarti:

### 🏆 1. Leaderboard & Indicatori
Una vista "a imbuto" (Funnel) per scoprire in automatico le zone con la maggiore crescita dei prezzi. 
Seleziona una provincia o un comune e scopri immediatamente quali sono i top performer in base all'incremento percentuale storico.

### 🔍 2. Esplora Dettaglio
La vista analitica profonda. Seleziona una provincia e un comune per caricare tutti i dati locali. 
Usa i filtri avanzati per isolare Semestri, Fasce/Zone e Destinazioni d'uso, e visualizza l'andamento temporale e lo spaccato per Tipologia e Stato Conservativo.

---
*Nota: i dati mostrati si basano sul database locale generato tramite scraping.*
""")
