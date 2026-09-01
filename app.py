import streamlit as st

st.set_page_config(
    page_title="Portale OMI - Agenzia Entrate",
    page_icon="🏠",
    layout="centered"
)

from db_utils import ensure_db
# Assicura che il DB esista se l'utente atterra qui per la prima volta
ensure_db()


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
