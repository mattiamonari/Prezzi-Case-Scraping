import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Analisi Quotazioni Immobiliari", layout="wide")

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'quotazioni.db')
TUTTI = "Tutti"

@st.cache_resource
def get_db_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def run_query(query, params=()):
    conn = get_db_connection()
    return pd.read_sql_query(query, conn, params=params)

def get_top_incremento(group_col_id, group_col_nome, group_col_sub, metrica, is_compra, utilizzo, sem_start, sem_end, filter_col=None, filter_val=None):
    col_min = 'val_compravendita_min' if is_compra else 'val_locazione_min'
    col_max = 'val_compravendita_max' if is_compra else 'val_locazione_max'
    
    where_clause = ["q.semestre_id >= ?", "q.semestre_id <= ?"]
    params = [sem_start, sem_end]
    
    if utilizzo != TUTTI:
        where_clause.append("q.utilizzo_id = ?")
        params.append(utilizzo)
        
    if filter_col and filter_val:
        where_clause.append(f"{filter_col} = ?")
        params.append(filter_val)
        
    where_sql = "WHERE " + " AND ".join(where_clause)
    
    query = f"""
    WITH prezzi_semestre AS (
        SELECT 
            {group_col_id} as id, 
            {group_col_nome} as nome,
            {group_col_sub} as sub,
            q.semestre_id,
            AVG({col_min} + {col_max})/2.0 as prezzo
        FROM quotazioni q
        JOIN zona z ON q.zona_id = z.id
        JOIN comune c ON z.comune_id = c.id
        JOIN provincia p ON c.provincia_id = p.id
        {where_sql}
        GROUP BY {group_col_id}, {group_col_nome}, {group_col_sub}, q.semestre_id
    ),
    primi_ultimi AS (
        SELECT 
            id, nome, sub,
            FIRST_VALUE(prezzo) OVER(PARTITION BY id ORDER BY semestre_id ASC) as prezzo_iniziale,
            FIRST_VALUE(prezzo) OVER(PARTITION BY id ORDER BY semestre_id DESC) as prezzo_finale
        FROM prezzi_semestre
    )
    SELECT DISTINCT 
        id, nome, sub,
        prezzo_iniziale, prezzo_finale,
        ((prezzo_finale - prezzo_iniziale) / prezzo_iniziale) * 100 as incremento
    FROM primi_ultimi
    WHERE prezzo_iniziale > 0
    ORDER BY incremento DESC
    LIMIT 1
    """
    df = run_query(query, tuple(params))
    return df.iloc[0] if not df.empty else None

def draw_kpi_card(label, data, selected_value=None):
    if selected_value:
        main_value = selected_value
        subtitle = "Selezionata/o dal filtro"
        incr_html = "<div style='font-size: 16px; color: #888;'>Fisso</div>"
    elif data is not None:
        main_value = data['nome']
        subtitle = data['sub']
        incr = data['incremento']
        color = "green" if incr > 0 else "red" if incr < 0 else "gray"
        arrow = "▲" if incr > 0 else "▼" if incr < 0 else ""
        incr_html = f"<div style='font-size: 16px; font-weight: bold; color: {color};'>{arrow} {incr:+.1f}%</div>"
    else:
        main_value = "N/A"
        subtitle = "-"
        incr_html = ""

    html = f"""
    <div style="padding: 10px 0px; font-family: sans-serif;">
        <div style="font-size: 14px; color: #666; margin-bottom: 5px;">{label}</div>
        <div style="font-size: 24px; font-weight: bold; line-height: 1.2; word-wrap: break-word;">{main_value}</div>
        <div style="font-size: 14px; color: #999; margin-bottom: 8px;">{subtitle}</div>
        {incr_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


st.title("📈 Dashboard Immobiliare OMI")

# CSS per evitare che il testo dei KPI lunghi venga troncato coi puntini
st.markdown("""
<style>
[data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    white-space: normal !important;
    word-wrap: break-word !important;
    line-height: 1.2 !important;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.header("Filtri Ricerca")

metrica = st.sidebar.radio("Tipo Valore", options=["Compravendita (€/mq)", "Locazione (€/mq x mese)"])
is_compra = metrica == "Compravendita (€/mq)"

df_utilizzi = run_query("SELECT id FROM utilizzo")
utilizzi_opts = [TUTTI] + df_utilizzi['id'].tolist()
sel_utilizzo = st.sidebar.selectbox("Destinazione d'Uso", options=utilizzi_opts, index=1 if len(utilizzi_opts)>1 else 0)

df_province = run_query("SELECT id, nome FROM provincia ORDER BY nome")
prov_opts = {TUTTI: TUTTI}
prov_opts.update(dict(zip(df_province['nome'], df_province['id'])))
sel_prov_nome = st.sidebar.selectbox("Provincia", options=list(prov_opts.keys()))
provincia_id = prov_opts[sel_prov_nome]

comune_id = TUTTI
if provincia_id != TUTTI:
    df_comuni = run_query("SELECT id, nome FROM comune WHERE provincia_id = ? ORDER BY nome", (provincia_id,))
    comuni_opts = {TUTTI: TUTTI}
    comuni_opts.update(dict(zip(df_comuni['nome'], df_comuni['id'])))
    sel_com_nome = st.sidebar.selectbox("Comune", options=list(comuni_opts.keys()))
    comune_id = comuni_opts[sel_com_nome]

# --- SEZIONE KPI ---
st.subheader("🏆 Leaderboard Incrementi Storici (Totale)")

st.sidebar.markdown("---")
st.sidebar.subheader("Orizzonte Temporale")

df_sems = run_query("SELECT id FROM semestre ORDER BY id ASC")
if not df_sems.empty:
    tutti_sems = df_sems['id'].tolist()
    latest_sem = tutti_sems[-1]
    
    time_opts = ["Tutto lo storico", "Ultimi 10 anni", "Ultimi 5 anni", "Ultimi 2 anni", "Personalizzato"]
    sel_time = st.sidebar.radio("Scegli l'intervallo:", options=time_opts)
    
    sem_start = None
    sem_end = latest_sem
    
    if sel_time == "Ultimi 10 anni":
        sem_start = str(int(latest_sem[:4]) - 10) + latest_sem[4:]
    elif sel_time == "Ultimi 5 anni":
        sem_start = str(int(latest_sem[:4]) - 5) + latest_sem[4:]
    elif sel_time == "Ultimi 2 anni":
        sem_start = str(int(latest_sem[:4]) - 2) + latest_sem[4:]
    elif sel_time == "Personalizzato":
        def fmt_sem(s):
            return s[:4] + " (" + ('Gen-Giu' if s[4:]=='1' else 'Lug-Dic') + ")"
        fmt_list = [fmt_sem(s) for s in tutti_sems]
        
        sel_range = st.sidebar.select_slider("Seleziona Semestri", options=fmt_list, value=(fmt_list[0], fmt_list[-1]))
        
        idx_start = fmt_list.index(sel_range[0])
        idx_end = fmt_list.index(sel_range[1])
        sem_start = tutti_sems[idx_start]
        sem_end = tutti_sems[idx_end]
    else:
        sem_start = tutti_sems[0]
        
    if sem_start not in tutti_sems:
        valid_starts = [s for s in tutti_sems if s >= sem_start]
        sem_start = valid_starts[0] if valid_starts else tutti_sems[0]
else:
    sem_start, sem_end = "0", "99999"


col1, col2, col3 = st.columns(3)

with col1:
    if provincia_id == TUTTI:
        top_prov = get_top_incremento("p.id", "p.nome", "'Nazionale'", metrica, is_compra, sel_utilizzo, sem_start, sem_end)
        draw_kpi_card("Miglior Provincia", top_prov)
    else:
        draw_kpi_card("Miglior Provincia", None, selected_value=sel_prov_nome)

with col2:
    if comune_id == TUTTI:
        filter_col = "c.provincia_id" if provincia_id != TUTTI else None
        filter_val = provincia_id if provincia_id != TUTTI else None
        top_com = get_top_incremento("c.id", "c.nome", "p.nome || ' (' || p.id || ')'", metrica, is_compra, sel_utilizzo, sem_start, sem_end, filter_col, filter_val)
        draw_kpi_card("Miglior Comune", top_com)
    else:
        draw_kpi_card("Miglior Comune", None, selected_value=sel_com_nome)

with col3:
    if comune_id != TUTTI:
        filter_col = "z.comune_id"
        filter_val = comune_id
    elif provincia_id != TUTTI:
        filter_col = "c.provincia_id"
        filter_val = provincia_id
    else:
        filter_col = filter_val = None
        
    top_zona = get_top_incremento("z.id", "z.fascia_descrizione", "c.nome || ' (' || p.id || ')'", metrica, is_compra, sel_utilizzo, sem_start, sem_end, filter_col, filter_val)
    draw_kpi_card("Miglior Fascia/Zona", top_zona)

st.markdown("---")

def draw_trend_chart(col_obj, title, filter_col, filter_val, is_compra, utilizzo, sem_start, sem_end, y_axis_title):
    col_min = 'val_compravendita_min' if is_compra else 'val_locazione_min'
    col_max = 'val_compravendita_max' if is_compra else 'val_locazione_max'
    
    where_q = ["q.semestre_id >= ?", "q.semestre_id <= ?"]
    prm = [sem_start, sem_end]
    
    if utilizzo != TUTTI:
        where_q.append("q.utilizzo_id = ?")
        prm.append(utilizzo)
        
    if filter_col and filter_val:
        where_q.append(f"{filter_col} = ?")
        prm.append(filter_val)
        
    where_sql = "WHERE " + " AND ".join(where_q)
    
    query = f"""
    SELECT 
        q.semestre_id as semestre,
        AVG({col_min}) as p_min,
        AVG({col_max}) as p_max,
        AVG({col_min} + {col_max})/2.0 as p_med
    FROM quotazioni q
    JOIN zona z ON q.zona_id = z.id
    JOIN comune c ON z.comune_id = c.id
    {where_sql}
    GROUP BY q.semestre_id
    ORDER BY q.semestre_id ASC
    """
    df_trend = run_query(query, tuple(prm))
    
    if not df_trend.empty:
        df_trend['anno'] = df_trend['semestre'].astype(str).str[:4]
        df_trend['sem_num'] = df_trend['semestre'].astype(str).str[4:]
        df_trend['sem_label'] = df_trend['anno'] + " (" + df_trend['sem_num'].map({'1': 'Gen-Giu', '2': 'Lug-Dic'}) + ")"

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_trend['sem_label'], y=df_trend['p_max'], mode='lines', line=dict(width=0), showlegend=False, name='Max', hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=df_trend['sem_label'], y=df_trend['p_min'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(0, 100, 250, 0.2)', showlegend=False, name='Min', hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=df_trend['sem_label'], y=df_trend['p_med'], mode='lines+markers', line=dict(color='blue', width=2), name='Media'))
        
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            xaxis_title="",
            yaxis_title=y_axis_title,
            hovermode="x unified",
            margin=dict(l=0, r=0, t=30, b=0),
            height=300
        )
        col_obj.plotly_chart(fig, use_container_width=True)
    else:
        col_obj.info(f"Nessun dato per: {title}")

st.markdown("---")
st.subheader("Andamento Temporale Vincitori")

colA, colB, colC = st.columns(3)

# 1. Grafico Provincia
prov_target_id = top_prov['id'] if provincia_id == TUTTI and top_prov is not None else provincia_id
prov_target_nome = top_prov['nome'] if provincia_id == TUTTI and top_prov is not None else sel_prov_nome
if prov_target_id != TUTTI:
    draw_trend_chart(colA, f"Provincia: {prov_target_nome}", "c.provincia_id", prov_target_id, is_compra, sel_utilizzo, sem_start, sem_end, metrica)
else:
    draw_trend_chart(colA, "Media Nazionale", None, None, is_compra, sel_utilizzo, sem_start, sem_end, metrica)

# 2. Grafico Comune
com_target_id = top_com['id'] if comune_id == TUTTI and top_com is not None else comune_id
com_target_nome = top_com['nome'] if comune_id == TUTTI and top_com is not None else sel_com_nome
if com_target_id != TUTTI:
    draw_trend_chart(colB, f"Comune: {com_target_nome}", "z.comune_id", com_target_id, is_compra, sel_utilizzo, sem_start, sem_end, metrica)
else:
    colB.info("Nessun Comune vincitore da mostrare.")

# 3. Grafico Zona
if top_zona is not None:
    draw_trend_chart(colC, f"Zona: {top_zona['nome']}", "z.id", top_zona['id'], is_compra, sel_utilizzo, sem_start, sem_end, metrica)
else:
    colC.info("Nessuna Zona vincitrice da mostrare.")
