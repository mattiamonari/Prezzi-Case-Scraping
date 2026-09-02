import streamlit as st
import pandas as pd
import plotly.express as px
from db_utils import get_db_connection

st.set_page_config(page_title="Analisi Avanzata", layout="wide", page_icon="📊")

st.title("📊 Analisi Avanzata & Rendimenti")
st.markdown("""
Esplora i dati immobiliari sotto nuove lenti: dai prezzi assoluti (i più cari e i più economici), 
al calcolo del rendimento da locazione (ROI), fino all'analisi della polarizzazione (divario Centro-Periferia) e alla resilienza storica.
""")

# CSS to make charts look slightly better
st.markdown("""
<style>
.stPlotlyChart {
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)

# Helper for queries
@st.cache_data(show_spinner=False)
def run_query(query, params=()):
    try:
        conn = get_db_connection()
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Errore SQL Reale:\n{e}\n\nQuery:\n{query}\n\nParams:\n{params}")
        return pd.DataFrame()

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filtri Globali")

# 1. Utilizzo
df_utilizzi = run_query("SELECT id FROM utilizzo")
utilizzi_opts = df_utilizzi['id'].tolist()
sel_utilizzo = st.sidebar.selectbox("Destinazione d'Uso", options=utilizzi_opts, index=1 if len(utilizzi_opts)>1 else 0)

# 2. Semestre
df_sems = run_query("SELECT id FROM semestre ORDER BY id ASC")
tutti_sems = df_sems['id'].tolist() if not df_sems.empty else []
sel_semestre = st.sidebar.selectbox("Semestre di Riferimento", options=tutti_sems[::-1]) # default a max

# 3. Provincia
df_province = run_query("SELECT id, nome FROM provincia ORDER BY nome")
prov_opts = {"Tutta Italia": "TUTTI"}
prov_opts.update(dict(zip(df_province['nome'], df_province['id'])))
sel_prov_nome = st.sidebar.selectbox("Provincia", options=list(prov_opts.keys()))
provincia_id = prov_opts[sel_prov_nome]

# 4. Livello di Dettaglio (Comune o Zona)
livello = st.sidebar.radio("Livello di Dettaglio (per Top & Flop)", options=["Comune", "Zona"])
table_name = "agg_comune" if livello == "Comune" else "agg_zona"


# --- BUILD BASE WHERE CLAUSE ---
where_clause = ["semestre_id = ?", "utilizzo_id = ?"]
params = [sel_semestre, sel_utilizzo]

if provincia_id != "TUTTI":
    where_clause.append("provincia_id = ?")
    params.append(provincia_id)

where_sql = "WHERE " + " AND ".join(where_clause)


# ---------------------------------------------------------
# SEZIONE 1: TOP & FLOP PREZZI ASSOLUTI
# ---------------------------------------------------------
st.markdown("---")
st.header("1. Top & Flop Prezzi Assoluti")
st.markdown(f"Scopri le/i {livello.lower()}i più costose/i e più economiche/i nel semestre selezionato.")

col_m, col_s = st.columns([2, 1])
with col_m:
    metrica_tf = st.radio("Scegli la metrica per la classifica:", ["Compravendita (€/mq)", "Locazione (€/mq x mese)"], horizontal=True)
with col_s:
    num_top_flop = st.slider("Risultati da mostrare", min_value=10, max_value=100, value=10, step=10)

col_prezzo = "prezzo_compra" if metrica_tf == "Compravendita (€/mq)" else "prezzo_loca"

query_base = f"""
SELECT nome, sub, {col_prezzo} as prezzo
FROM {table_name}
{where_sql} AND {col_prezzo} > 0
"""

df_top = run_query(query_base + f" ORDER BY prezzo DESC LIMIT {num_top_flop}", tuple(params))
df_flop = run_query(query_base + f" ORDER BY prezzo ASC LIMIT {num_top_flop}", tuple(params))

if not df_top.empty and not df_flop.empty:
    col1, col2 = st.columns(2)
    
    # Altezza dinamica del grafico in base al numero di elementi per non schiacciare le barre
    plot_height = max(400, num_top_flop * 25)
    
    with col1:
        st.subheader(f"🏆 I {num_top_flop} {livello}i Più Costosi")
        # Ordiniamo in modo crescente così il più alto è in cima nel bar_h
        df_top_plot = df_top.sort_values('prezzo', ascending=True)
        fig_top = px.bar(
            df_top_plot, x='prezzo', y='nome', text_auto='.0f', orientation='h',
            hover_data=['sub'], labels={'nome': '', 'prezzo': metrica_tf},
            color='prezzo', color_continuous_scale='Reds'
        )
        fig_top.update_layout(height=plot_height, margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False)
        with st.container(height=500):
            st.plotly_chart(fig_top, use_container_width=True)

    with col2:
        st.subheader(f"📉 I {num_top_flop} {livello}i Più Economici")
        df_flop_plot = df_flop.sort_values('prezzo', ascending=False)
        fig_flop = px.bar(
            df_flop_plot, x='prezzo', y='nome', text_auto='.0f', orientation='h',
            hover_data=['sub'], labels={'nome': '', 'prezzo': metrica_tf},
            color='prezzo', color_continuous_scale='Greens_r'
        )
        fig_flop.update_layout(height=plot_height, margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False)
        with st.container(height=500):
            st.plotly_chart(fig_flop, use_container_width=True)
else:
    st.info("Nessun dato disponibile per i filtri selezionati.")


# ---------------------------------------------------------
# SEZIONE 2: RENDIMENTO DA LOCAZIONE (ROI)
# ---------------------------------------------------------
st.markdown("---")
st.header("2. Rendimento da Locazione (ROI Lordo)")
st.markdown(f"""
Il rendimento percentuale annuo indica quanto rende affittare un immobile rispetto al suo prezzo d'acquisto. 
*(Calcolato a livello di **{livello}** come: Affitto mensile × 12 / Prezzo compravendita)*.
""")

query_roi = f"""
SELECT nome, sub, prezzo_compra, prezzo_loca, 
       ((prezzo_loca * 12.0) / prezzo_compra) * 100 AS roi
FROM {table_name}
{where_sql} AND prezzo_compra > 0 AND prezzo_loca > 0
ORDER BY roi DESC
LIMIT 15
"""
df_roi = run_query(query_roi, tuple(params))

if not df_roi.empty:
    df_roi_plot = df_roi.sort_values('roi', ascending=True)
    fig_roi = px.bar(
        df_roi_plot, x='roi', y='nome', text_auto='.1f', orientation='h',
        hover_data=['sub', 'prezzo_compra', 'prezzo_loca'], 
        labels={'nome': '', 'roi': 'ROI Lordo Annuo (%)'},
        color='roi', color_continuous_scale='Viridis'
    )
    fig_roi.update_layout(margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False, height=500)
    fig_roi.update_traces(texttemplate='%{x:.1f}%')
    st.plotly_chart(fig_roi, use_container_width=True)
else:
    st.info("Dati insufficienti per calcolare il ROI in questa selezione.")


# ---------------------------------------------------------
# SEZIONE 3: POLARIZZAZIONE (Forbice Prezzi nei Comuni)
# ---------------------------------------------------------
st.markdown("---")
st.header("3. Analisi della Polarizzazione (Forbice di Prezzo)")
st.markdown("""
Questa analisi mostra in quali Comuni c'è la maggiore differenza di prezzo tra le zone più care (es. Centro Storico) e le zone più economiche (es. Periferia).  
*N.B. L'analisi è basata sulle diverse "Fasce/Zone" censite dall'OMI all'interno dello stesso Comune.*
""")

# We need the zone table grouped by comune
where_clause_pol = ["z.semestre_id = ?", "z.utilizzo_id = ?"]
params_pol = [sel_semestre, sel_utilizzo]
if provincia_id != "TUTTI":
    where_clause_pol.append("z.provincia_id = ?")
    params_pol.append(provincia_id)

where_sql_pol = "WHERE " + " AND ".join(where_clause_pol)

query_polarizzazione = f"""
SELECT 
    c.nome AS comune, 
    p.nome AS provincia,
    MAX(z.prezzo_compra) AS max_prezzo, 
    MIN(z.prezzo_compra) AS min_prezzo,
    (MAX(z.prezzo_compra) - MIN(z.prezzo_compra)) AS forbice_assoluta,
    (MAX(z.prezzo_compra) / MIN(z.prezzo_compra)) AS forbice_relativa
FROM agg_zona z
JOIN comune c ON z.comune_id = c.id
JOIN provincia p ON z.provincia_id = p.id
{where_sql_pol} AND z.prezzo_compra > 0
GROUP BY c.id, c.nome, p.nome
HAVING COUNT(z.id) > 1
ORDER BY forbice_relativa DESC
LIMIT 15
"""

df_pol = run_query(query_polarizzazione, tuple(params_pol))

if not df_pol.empty:
    fig_pol = px.scatter(
        df_pol, x="min_prezzo", y="max_prezzo", size="forbice_relativa", color="forbice_assoluta",
        hover_name="comune", hover_data=["provincia", "forbice_assoluta"],
        labels={"min_prezzo": "Prezzo Minimo in Comune (€/mq)", "max_prezzo": "Prezzo Massimo in Comune (€/mq)"},
        title="Disuguaglianza dei prezzi intra-comunale (Rapporto Max/Min)",
        color_continuous_scale="Turbo"
    )
    # Aggiungi una linea diagonale di y=x (nessuna forbice)
    max_val = max(df_pol['max_prezzo'].max(), df_pol['min_prezzo'].max())
    fig_pol.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color="grey", dash="dash"))
    
    st.plotly_chart(fig_pol, use_container_width=True)
    
    with st.expander("Mostra tabella Dati Polarizzazione"):
        st.dataframe(df_pol.rename(columns={
            "comune": "Comune", "provincia": "Provincia", 
            "max_prezzo": "Zona più cara", "min_prezzo": "Zona più economica",
            "forbice_assoluta": "Differenza (€)", "forbice_relativa": "Rapporto (Moltiplicatore)"
        }))
else:
    st.info("Nessuna forbice trovata (forse i Comuni selezionati hanno una sola zona o mancano dati).")


# ---------------------------------------------------------
# SEZIONE 4: RESILIENZA E CRESCITA STORICA
# ---------------------------------------------------------
st.markdown("---")
st.header("4. Resilienza dei Mercati (Comuni)")
st.markdown("""
Analizziamo lo storico dei prezzi (tutti i semestri disponibili) per scoprire quali Comuni hanno registrato il maggior numero di **semestri in crescita**.  
*Un alto "Tasso di Resilienza" indica un mercato in ascesa costante e meno volatile.*
""")

if st.button("Calcola Analisi Resilienza"):
    with st.spinner("Analisi di tutto lo storico in corso..."):
        # We need all semesters for the selected utilizzo and optionally filtered by prov
        where_clause_res = ["utilizzo_id = ?"]
        params_res = [sel_utilizzo]
        if provincia_id != "TUTTI":
            where_clause_res.append("provincia_id = ?")
            params_res.append(provincia_id)
            
        where_sql_res = "WHERE " + " AND ".join(where_clause_res)
        
        query_res = f"""
        SELECT id, nome, sub, semestre_id, prezzo_compra
        FROM agg_comune
        {where_sql_res} AND prezzo_compra > 0
        ORDER BY id, semestre_id ASC
        """
        df_hist = run_query(query_res, tuple(params_res))
        
        if not df_hist.empty:
            # Calcoli pandas
            df_hist.sort_values(by=['id', 'semestre_id'], inplace=True)
            df_hist['prev_prezzo'] = df_hist.groupby('id')['prezzo_compra'].shift(1)
            # Consideriamo crescita solo se aumenta di >1% per evitare micro-fluttuazioni
            df_hist['is_growth'] = df_hist['prezzo_compra'] > (df_hist['prev_prezzo'] * 1.01)
            
            # Count 
            df_resilience = df_hist.groupby(['id', 'nome', 'sub']).agg(
                total_semesters=('semestre_id', 'count'),
                growth_semesters=('is_growth', 'sum'),
                latest_price=('prezzo_compra', 'last')
            ).reset_index()
            
            # Filtra solo i comuni con almeno 4 semestri di storico
            df_resilience = df_resilience[df_resilience['total_semesters'] > 4]
            
            if not df_resilience.empty:
                df_resilience['tasso_resilienza_perc'] = (df_resilience['growth_semesters'] / (df_resilience['total_semesters'] - 1)) * 100
                
                df_resilience = df_resilience.sort_values(by=['tasso_resilienza_perc', 'growth_semesters'], ascending=[False, False]).head(20)
                
                df_resilience_plot = df_resilience.sort_values('tasso_resilienza_perc', ascending=True)
                fig_res = px.bar(
                    df_resilience_plot, x='tasso_resilienza_perc', y='nome', text_auto='.0f', orientation='h',
                    hover_data=['sub', 'growth_semesters', 'total_semesters'], 
                    labels={'nome': '', 'tasso_resilienza_perc': '% di semestri in crescita'},
                    color='tasso_resilienza_perc', color_continuous_scale='Blues'
                )
                fig_res.update_layout(margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False)
                fig_res.update_traces(texttemplate='%{x:.0f}%')
                st.plotly_chart(fig_res, use_container_width=True)
            else:
                st.info("Nessun comune ha storico sufficiente (>4 semestri).")
        else:
            st.info("Nessuno storico trovato per i filtri selezionati.")
