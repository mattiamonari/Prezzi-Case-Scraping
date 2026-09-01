import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
from db_utils import get_db_connection

st.set_page_config(page_title="Esplora Dettaglio - OMI", layout="wide")

TUTTI = "Tutti"

@st.cache_data
def get_province():
    conn = get_db_connection()
    return pd.read_sql_query("SELECT id, nome FROM provincia ORDER BY nome", conn)

@st.cache_data
def get_comuni(provincia_id):
    conn = get_db_connection()
    return pd.read_sql_query("SELECT id, nome FROM comune WHERE provincia_id = ? ORDER BY nome", conn, params=(provincia_id,))

@st.cache_data
def get_dati_comune(comune_id):
    conn = get_db_connection()
    query = """
    SELECT 
        q.semestre_id as semestre,
        z.cod_zona || ' - ' || z.fascia_descrizione as zona,
        u.id as utilizzo,
        q.tipologia,
        q.stato_conservativo,
        q.val_compravendita_min,
        q.val_compravendita_max,
        q.val_locazione_min,
        q.val_locazione_max
    FROM quotazioni q
    JOIN zona z ON q.zona_id = z.id
    JOIN utilizzo u ON q.utilizzo_id = u.id
    WHERE z.comune_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(comune_id,))
    
    # Ordiniamo correttamente il semestre
    df.sort_values(by='semestre', inplace=True)
    df['anno'] = df['semestre'].astype(str).str[:4]
    df['sem_num'] = df['semestre'].astype(str).str[4:]
    df['semestre_label'] = df['anno'] + " (" + df['sem_num'].map({'1': 'Gen-Giu', '2': 'Lug-Dic'}) + ")"
    
    # Calcoliamo la media
    df['media_compravendita'] = (df['val_compravendita_min'] + df['val_compravendita_max']) / 2
    df['media_locazione'] = (df['val_locazione_min'] + df['val_locazione_max']) / 2
    
    return df

st.title("🔍 Esplora Dettaglio Comune")

st.sidebar.header("Filtri Ricerca")

metrica = st.sidebar.radio("Tipo Valore", options=["Compravendita (€/mq)", "Locazione (€/mq x mese)"])
is_compra = metrica == "Compravendita (€/mq)"
col_min = 'val_compravendita_min' if is_compra else 'val_locazione_min'
col_max = 'val_compravendita_max' if is_compra else 'val_locazione_max'
col_med = 'media_compravendita' if is_compra else 'media_locazione'

df_province = get_province()
if df_province.empty:
    st.warning("Il database è vuoto. Esegui prima lo scraping!")
    st.stop()

prov_dict = dict(zip(df_province['nome'], df_province['id']))
selected_prov_nome = st.sidebar.selectbox("Provincia", options=list(prov_dict.keys()))
provincia_id = prov_dict[selected_prov_nome]

df_comuni = get_comuni(provincia_id)
if df_comuni.empty:
    st.warning("Nessun comune trovato per questa provincia.")
    st.stop()

comuni_dict = dict(zip(df_comuni['nome'], df_comuni['id']))
selected_comune_nome = st.sidebar.selectbox("Comune", options=list(comuni_dict.keys()))
comune_id = comuni_dict[selected_comune_nome]

df = get_dati_comune(comune_id)

if df.empty:
    st.info("Nessuna quotazione trovata per questo comune.")
    st.stop()

st.sidebar.markdown("---")

semestri_disp = [TUTTI] + list(df['semestre_label'].unique())
sel_semestre = st.sidebar.selectbox("Semestre", options=semestri_disp)

zone_disp = [TUTTI] + list(df['zona'].unique())
sel_zona = st.sidebar.selectbox("Fascia/Zona", options=zone_disp)

utilizzi_disp = [TUTTI] + list(df['utilizzo'].unique())
sel_utilizzo = st.sidebar.selectbox("Tipo destinazione", options=utilizzi_disp)

df_filtered = df.copy()
if sel_semestre != TUTTI:
    df_filtered = df_filtered[df_filtered['semestre_label'] == sel_semestre]
if sel_zona != TUTTI:
    df_filtered = df_filtered[df_filtered['zona'] == sel_zona]
if sel_utilizzo != TUTTI:
    df_filtered = df_filtered[df_filtered['utilizzo'] == sel_utilizzo]

if df_filtered.empty:
    st.warning("Nessun dato corrisponde ai filtri selezionati.")
    st.stop()


st.subheader(f"Andamento Storico - {selected_comune_nome}")
if sel_semestre == TUTTI:
    df_trend = df_filtered.groupby(['semestre', 'semestre_label']).agg({
        col_min: 'mean', col_max: 'mean', col_med: 'mean'
    }).reset_index().sort_values('semestre')

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_trend['semestre_label'], y=df_trend[col_max], mode='lines', line=dict(width=0), showlegend=False, name='Max'))
    fig.add_trace(go.Scatter(x=df_trend['semestre_label'], y=df_trend[col_min], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(0, 100, 250, 0.2)', showlegend=False, name='Min'))
    fig.add_trace(go.Scatter(x=df_trend['semestre_label'], y=df_trend[col_med], mode='lines+markers', line=dict(color='blue', width=3), name='Media'))
    
    fig.update_layout(xaxis_title="Semestre", yaxis_title=metrica, hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, width="stretch")
else:
    st.info("Filtro Semestre attivo. Deseleziona il semestre per vedere l'andamento storico.")

st.markdown("---")

st.subheader("Dettaglio per Tipologia e Stato Conservativo")
target_semestre = sel_semestre if sel_semestre != TUTTI else df_filtered['semestre_label'].iloc[-1]
df_breakdown = df_filtered[df_filtered['semestre_label'] == target_semestre]

if not df_breakdown.empty:
    df_breakdown['Tipologia_Stato'] = df_breakdown['tipologia'] + " (" + df_breakdown['stato_conservativo'] + ")"
    df_bar = df_breakdown.groupby('Tipologia_Stato').agg({
        col_min: 'mean', col_max: 'mean', col_med: 'mean'
    }).reset_index()
    
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=df_bar['Tipologia_Stato'], y=df_bar[col_med],
        error_y=dict(type='data', symmetric=False, array=df_bar[col_max] - df_bar[col_med], arrayminus=df_bar[col_med] - df_bar[col_min]),
        marker_color='lightblue', name='Media'
    ))
    fig_bar.update_layout(xaxis_title="Tipologia e Stato", yaxis_title=metrica, xaxis_tickangle=-45, margin=dict(l=0, r=0, t=30, b=100))
    st.plotly_chart(fig_bar, width="stretch")
else:
    st.write("Nessun dato disponibile.")
