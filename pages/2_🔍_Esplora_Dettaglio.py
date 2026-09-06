import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import plotly.express as px
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
    df.sort_values(by='semestre', inplace=True)
    df['anno'] = df['semestre'].astype(str).str[:4]
    df['sem_num'] = df['semestre'].astype(str).str[4:]
    df['semestre_label'] = df['anno'] + " (" + df['sem_num'].map({'1': 'Gen-Giu', '2': 'Lug-Dic'}) + ")"
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

# --- Confronto zone: multiselect invece di selectbox singolo ---
zone_disp = sorted(df['zona'].unique())
sel_zone = st.sidebar.multiselect(
    "Fasce/Zone (lascia vuoto = tutte)",
    options=zone_disp,
    help="Seleziona più zone per confrontarle nello stesso grafico."
)

utilizzi_disp = [TUTTI] + list(df['utilizzo'].unique())
sel_utilizzo = st.sidebar.selectbox("Tipo destinazione", options=utilizzi_disp)

# --- FILTRAGGIO ---
df_filtered = df.copy()
if sel_semestre != TUTTI:
    df_filtered = df_filtered[df_filtered['semestre_label'] == sel_semestre]
if sel_zone:
    df_filtered = df_filtered[df_filtered['zona'].isin(sel_zone)]
if sel_utilizzo != TUTTI:
    df_filtered = df_filtered[df_filtered['utilizzo'] == sel_utilizzo]

if df_filtered.empty:
    st.warning("Nessun dato corrisponde ai filtri selezionati.")
    st.stop()

# --- Download CSV ---
csv_data = df_filtered.to_csv(index=False).encode('utf-8')
st.download_button(
    label="⬇️ Scarica dati filtrati (CSV)",
    data=csv_data,
    file_name=f"OMI_{selected_comune_nome.replace(' ', '_')}.csv",
    mime="text/csv"
)

# =================================================================
# SEZIONE 1: ANDAMENTO STORICO
# =================================================================
st.subheader(f"Andamento Storico - {selected_comune_nome}")

if sel_semestre == TUTTI:
    fig = go.Figure()

    if len(sel_zone) > 1:
        # --- Confronto multi-zona: una linea per zona ---
        colors = px.colors.qualitative.Plotly
        for i, zona in enumerate(sel_zone):
            df_zona = df_filtered[df_filtered['zona'] == zona]
            df_trend_z = df_zona.groupby(['semestre', 'semestre_label']).agg(
                {col_med: 'mean'}
            ).reset_index().sort_values('semestre')
            color = colors[i % len(colors)]
            fig.add_trace(go.Scatter(
                x=df_trend_z['semestre_label'],
                y=df_trend_z[col_med],
                mode='lines+markers',
                name=zona,
                line=dict(color=color, width=2)
            ))
        fig.update_layout(
            xaxis_title="Semestre", yaxis_title=metrica,
            hovermode="x unified",
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation='h', y=-0.25)
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Confronto tra {len(sel_zone)} zone selezionate. I prezzi mostrano la media per zona.")

    else:
        # --- Singola zona o tutte aggregate: banda min-max + media ---
        df_trend = df_filtered.groupby(['semestre', 'semestre_label']).agg({
            col_min: 'mean', col_max: 'mean', col_med: 'mean'
        }).reset_index().sort_values('semestre')

        fig.add_trace(go.Scatter(
            x=df_trend['semestre_label'], y=df_trend[col_max],
            mode='lines', line=dict(width=0), showlegend=False, name='Max', hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=df_trend['semestre_label'], y=df_trend[col_min],
            mode='lines', line=dict(width=0),
            fill='tonexty', fillcolor='rgba(0, 100, 250, 0.2)',
            showlegend=False, name='Min', hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=df_trend['semestre_label'], y=df_trend[col_med],
            mode='lines+markers', line=dict(color='blue', width=3), name='Media'
        ))
        fig.update_layout(
            xaxis_title="Semestre", yaxis_title=metrica,
            hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
        if sel_zone:
            st.caption(f"Zona selezionata: **{sel_zone[0]}**. Seleziona più zone per confrontarle.")
        else:
            st.caption("Media aggregata di tutte le zone del comune. Usa il filtro 'Fasce/Zone' per confrontare zone specifiche.")
else:
    st.info("Filtro Semestre attivo. Deseleziona il semestre per vedere l'andamento storico.")

st.markdown("---")

# =================================================================
# SEZIONE 2: DETTAGLIO TIPOLOGIA E STATO CONSERVATIVO
# =================================================================
st.subheader("Dettaglio per Tipologia e Stato Conservativo")
target_semestre = sel_semestre if sel_semestre != TUTTI else df_filtered['semestre_label'].iloc[-1]
df_breakdown = df_filtered[df_filtered['semestre_label'] == target_semestre].copy()

if not df_breakdown.empty:
    df_breakdown['Tipologia_Stato'] = df_breakdown['tipologia'] + " (" + df_breakdown['stato_conservativo'] + ")"
    df_bar = df_breakdown.groupby('Tipologia_Stato').agg({
        col_min: 'mean', col_max: 'mean', col_med: 'mean'
    }).reset_index()

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=df_bar['Tipologia_Stato'], y=df_bar[col_med],
        error_y=dict(
            type='data', symmetric=False,
            array=df_bar[col_max] - df_bar[col_med],
            arrayminus=df_bar[col_med] - df_bar[col_min]
        ),
        marker_color='lightblue', name='Media'
    ))
    fig_bar.update_layout(
        xaxis_title="Tipologia e Stato", yaxis_title=metrica,
        xaxis_tickangle=-45, margin=dict(l=0, r=0, t=30, b=100)
    )
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.write("Nessun dato disponibile.")

st.markdown("---")

# =================================================================
# SEZIONE 3: HEATMAP STORICA — Tipologia × Semestre
# =================================================================
st.subheader("🌡️ Heatmap Storica — Prezzo per Tipologia nel Tempo")
st.markdown(
    "Visualizza come è cambiato il prezzo medio di ogni tipologia immobiliare nel tempo. "
    "I colori più scuri indicano prezzi più alti."
)

all_sems_sorted = sorted(df_filtered['semestre'].unique())
last_sems = all_sems_sorted[-12:] if len(all_sems_sorted) > 12 else all_sems_sorted
df_hm_data = df_filtered[df_filtered['semestre'].isin(last_sems)].copy()

if not df_hm_data.empty and len(df_hm_data['tipologia'].unique()) > 1:
    df_hm_agg = df_hm_data.groupby(['semestre', 'semestre_label', 'tipologia'])[col_med].mean().reset_index()
    df_pivot = df_hm_agg.pivot(index='tipologia', columns='semestre_label', values=col_med)

    # Mantieni l'ordine cronologico sulle colonne
    sem_order_map = df_hm_data.drop_duplicates('semestre').sort_values('semestre').set_index('semestre_label')['semestre'].to_dict()
    ordered_cols = [c for c in sorted(df_pivot.columns, key=lambda x: sem_order_map.get(x, x)) if c in df_pivot.columns]
    df_pivot = df_pivot[ordered_cols]

    fig_hm = px.imshow(
        df_pivot.round(0),
        labels=dict(x="Semestre", y="Tipologia", color=metrica),
        aspect="auto",
        color_continuous_scale="RdYlGn_r",
        text_auto=True
    )
    fig_hm.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=max(250, len(df_pivot) * 40 + 80))
    fig_hm.update_xaxes(tickangle=-45)
    st.plotly_chart(fig_hm, use_container_width=True)
else:
    st.info("Dati insufficienti per la heatmap (servono almeno due tipologie e più semestri).")
