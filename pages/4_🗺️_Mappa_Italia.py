import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from db_utils import get_db_connection

st.set_page_config(page_title="Mappa Italia - OMI", layout="wide", page_icon="🗺️")

st.title("🗺️ Mappa dei Prezzi — Italia per Provincia")
st.markdown("""
Visualizza il **prezzo medio per provincia** su mappa. Ogni provincia è colorata in base al prezzo medio 
di compravendita o locazione nel semestre selezionato. Passa il cursore su una provincia per i dettagli.
""")

# --- HELPER ---
@st.cache_data(show_spinner=False)
def run_query(query, params=()):
    try:
        conn = get_db_connection()
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Errore SQL: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner="📥 Caricamento GeoJSON province italiane...")
def load_geojson():
    url = "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_IT_provinces.geojson"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Impossibile caricare la mappa geografica: {e}")
        return None

def fmt_sem(s):
    s = str(s)
    return s[:4] + " (" + ('Gen-Giu' if s[4:] == '1' else 'Lug-Dic') + ")"

# --- SIDEBAR ---
st.sidebar.header("Filtri Mappa")

df_utilizzi = run_query("SELECT id FROM utilizzo")
utilizzi_opts = df_utilizzi['id'].tolist()
sel_utilizzo = st.sidebar.selectbox("Destinazione d'Uso", options=utilizzi_opts, index=1 if len(utilizzi_opts) > 1 else 0)

df_sems = run_query("SELECT id FROM semestre ORDER BY id DESC")
tutti_sems = df_sems['id'].tolist() if not df_sems.empty else []
sem_labels = [fmt_sem(s) for s in tutti_sems]
sel_sem_label = st.sidebar.selectbox("Semestre", options=sem_labels)
sel_semestre = tutti_sems[sem_labels.index(sel_sem_label)]

metrica = st.sidebar.radio("Metrica", ["Compravendita (€/mq)", "Locazione (€/mq x mese)"])
col_prezzo = "prezzo_compra" if metrica == "Compravendita (€/mq)" else "prezzo_loca"

# --- DATA ---
query_map = f"""
SELECT ap.id as provincia_id, p.nome as provincia_nome,
       AVG(ap.{col_prezzo}) as prezzo_medio,
       COUNT(DISTINCT ac.id) as n_comuni
FROM agg_provincia ap
JOIN provincia p ON ap.id = p.id
LEFT JOIN agg_comune ac ON ac.provincia_id = ap.id 
    AND ac.semestre_id = ap.semestre_id 
    AND ac.utilizzo_id = ap.utilizzo_id
WHERE ap.semestre_id = ? AND ap.utilizzo_id = ? AND ap.{col_prezzo} > 0
GROUP BY ap.id, p.nome
"""
df_map = run_query(query_map, (sel_semestre, sel_utilizzo))

geojson = load_geojson()

if not df_map.empty and geojson is not None:
    # --- KPI RAPIDI ---
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Province con dati", len(df_map))
    kpi2.metric("Prezzo Medio Nazionale", f"€ {df_map['prezzo_medio'].mean():.0f}")
    top_prov = df_map.nlargest(1, 'prezzo_medio').iloc[0]
    bot_prov = df_map.nsmallest(1, 'prezzo_medio').iloc[0]
    kpi3.metric("Provincia più cara", f"{top_prov['provincia_nome']} (€{top_prov['prezzo_medio']:.0f})")
    kpi4.metric("Provincia più economica", f"{bot_prov['provincia_nome']} (€{bot_prov['prezzo_medio']:.0f})")

    st.markdown("---")

    # --- MAPPA CHOROPLETH ---
    fig = px.choropleth(
        df_map,
        geojson=geojson,
        locations="provincia_id",
        featureidkey="properties.prov_acr",
        color="prezzo_medio",
        hover_name="provincia_nome",
        hover_data={"provincia_id": False, "prezzo_medio": ":.0f"},
        color_continuous_scale="RdYlGn_r",
        labels={"prezzo_medio": metrica, "provincia_nome": "Provincia"},
        title=f"{metrica} — {sel_sem_label} — {sel_utilizzo}"
    )
    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=True,
        countrycolor="white"
    )
    fig.update_layout(
        height=680,
        margin=dict(l=0, r=0, t=50, b=0),
        coloraxis_colorbar=dict(title=metrica, thickness=15, len=0.6)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- GRAFICI DI SUPPORTO ---
    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🏆 Top 10 Province Più Care")
        df_top10 = df_map.nlargest(10, 'prezzo_medio').sort_values('prezzo_medio', ascending=True)
        fig_top = px.bar(
            df_top10, x='prezzo_medio', y='provincia_nome',
            orientation='h', text_auto='.0f',
            color='prezzo_medio', color_continuous_scale='Reds',
            labels={'prezzo_medio': metrica, 'provincia_nome': ''}
        )
        fig_top.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0), height=380)
        st.plotly_chart(fig_top, use_container_width=True)

    with col_b:
        st.subheader("📉 Top 10 Province Più Economiche")
        df_bot10 = df_map.nsmallest(10, 'prezzo_medio').sort_values('prezzo_medio', ascending=False)
        fig_bot = px.bar(
            df_bot10, x='prezzo_medio', y='provincia_nome',
            orientation='h', text_auto='.0f',
            color='prezzo_medio', color_continuous_scale='Greens_r',
            labels={'prezzo_medio': metrica, 'provincia_nome': ''}
        )
        fig_bot.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=0, t=10, b=0), height=380)
        st.plotly_chart(fig_bot, use_container_width=True)

    # --- TABELLA + DOWNLOAD ---
    st.markdown("---")
    with st.expander("📋 Classifica completa per Provincia"):
        df_table = df_map.sort_values('prezzo_medio', ascending=False).copy()
        df_table['Rank'] = range(1, len(df_table) + 1)
        df_table['prezzo_medio'] = df_table['prezzo_medio'].round(0).astype(int)
        df_table = df_table.rename(columns={
            'Rank': '#', 'provincia_id': 'Sigla',
            'provincia_nome': 'Provincia', 'prezzo_medio': f'{metrica}', 'n_comuni': 'N. Comuni'
        })[['#', 'Sigla', 'Provincia', f'{metrica}', 'N. Comuni']]
        st.dataframe(df_table, use_container_width=True, hide_index=True)

        csv = df_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Scarica classifica Province (CSV)",
            data=csv,
            file_name=f"province_{sel_semestre}_{sel_utilizzo}.csv",
            mime="text/csv"
        )

elif df_map.empty:
    st.info("Nessun dato disponibile per i filtri selezionati.")
else:
    st.warning("GeoJSON non disponibile. Verifica la connessione internet.")
