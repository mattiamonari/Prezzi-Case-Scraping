import os
import gzip
import shutil
import urllib.request
import sqlite3
import streamlit as st
import requests

# Costanti DB
DB_DIR = os.path.join(os.path.dirname(__file__), 'db')
DB_PATH = os.path.join(DB_DIR, 'quotazioni.db')
HF_DATASET_URL = "INSERISCI_QUI_IL_LINK"

def ensure_db():
    if not os.path.exists(DB_PATH) and HF_DATASET_URL != "INSERISCI_QUI_IL_LINK":
        os.makedirs(DB_DIR, exist_ok=True)
        with st.spinner("🔄 Primo avvio (o riavvio server): Download del database in corso..."):
            gz_path = DB_PATH + ".gz"
            try:
                headers = {}
                if "HF_TOKEN" in st.secrets:
                    headers["Authorization"] = f"Bearer {st.secrets['HF_TOKEN']}"
                    
                with requests.get(HF_DATASET_URL, headers=headers, stream=True) as r:
                    r.raise_for_status()
                    with open(gz_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            
                with gzip.open(gz_path, 'rb') as f_in:
                    with open(DB_PATH, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(gz_path)
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante il download del DB: {e}")
                st.stop()

@st.cache_resource
def get_db_connection():
    ensure_db()
    return sqlite3.connect(DB_PATH, check_same_thread=False)
