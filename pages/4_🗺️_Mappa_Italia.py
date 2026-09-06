import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from db_utils import get_db_connection

st.set_page_config(page_title="Mappa Italia - OMI", layout="wide", page_icon="🗺️")

# ============================================================
# SESSION STATE — traccia il livello di drill-down
# ============================================================
for key in ['drill_prov', 'drill_com']:
    if key not in st.session_state:
        st.session_state[key] = None

# ============================================================
# HELPERS
# ============================================================
@st.cache_data(show_spinner=False)
def run_query(query, params=()):
    try:
        conn = get_db_connection()
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Errore SQL: {e}")
        return pd.DataFrame()

@st.cache_resource(show_spinner="📥 Caricamento GeoJSON province italiane...")
def load_geojson_province():
    import json
    import os
    try:
        path = os.path.join("data", "geojson", "limits_IT_provinces.geojson")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Errore caricamento GeoJSON province: {e}")
        return None

@st.cache_resource(show_spinner="📥 Caricamento GeoJSON comuni in RAM...")
def load_geojson_comuni():
    """Carica il GeoJSON di tutti i comuni italiani e normalizza gli ID per il matching."""
    import json
    import os
    try:
        path = os.path.join("data", "geojson", "limits_IT_municipalities.geojson")
        with open(path, "r", encoding="utf-8") as f:
            gj = json.load(f)
            
        # Imposta feature['id'] = nome comune in maiuscolo per il matching con il DB
        for f in gj.get('features', []):
            props = f.get('properties', {})
            name = props.get('com_name', props.get('name', ''))
            f['id'] = name.upper().strip()
        return gj
    except Exception as e:
        st.error(f"Errore caricamento GeoJSON comuni: {e}")
        return None

@st.cache_resource(show_spinner="🔍 Filtraggio GeoJSON comuni per provincia...")
def get_geojson_provincia(prov_acr):
    """Restituisce il GeoJSON filtrato con solo i comuni della provincia selezionata.
    @st.cache_resource: il dict filtrato rimane in RAM per ogni provincia già visitata.
    """
    full_gj = load_geojson_comuni()
    if full_gj is None:
        return None
    features = [
        f for f in full_gj.get('features', [])
        if f.get('properties', {}).get('prov_acr', '').upper() == prov_acr.upper()
    ]
    if not features:
        return None
    return {'type': 'FeatureCollection', 'features': features}

def fmt_sem(s):
    s = str(s)
    return s[:4] + " (" + ('Gen-Giu' if s[4:] == '1' else 'Lug-Dic') + ")"

def make_choropleth(df, geojson, locations_col, feature_id_key, color_col, hover_name, color_label, height=560):
    fig = px.choropleth(
        df, geojson=geojson,
        locations=locations_col, featureidkey=feature_id_key,
        color=color_col, hover_name=hover_name,
        hover_data={locations_col: False, color_col: ":.0f"},
        color_continuous_scale="RdYlGn_r",
        labels={color_col: color_label},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0), dragmode=False,
        coloraxis_colorbar=dict(title=color_label.split("(")[0].strip(), thickness=14, len=0.65)
    )
    return fig

# ============================================================
# SIDEBAR — filtri sempre visibili
# ============================================================
st.sidebar.header("Filtri")

df_utilizzi = run_query("SELECT id FROM utilizzo")
utilizzi_opts = df_utilizzi['id'].tolist()
sel_utilizzo = st.sidebar.selectbox("Destinazione d'Uso", utilizzi_opts, index=1 if len(utilizzi_opts) > 1 else 0)

df_sems = run_query("SELECT id FROM semestre ORDER BY id DESC")
tutti_sems = df_sems['id'].tolist() if not df_sems.empty else []
sem_labels = [fmt_sem(s) for s in tutti_sems]
sel_sem_label = st.sidebar.selectbox("Semestre", sem_labels)
sel_semestre = tutti_sems[sem_labels.index(sel_sem_label)]

metrica = st.sidebar.radio("Metrica", ["Compravendita (€/mq)", "Locazione (€/mq x mese)"])
col_prezzo = "prezzo_compra" if "Compravendita" in metrica else "prezzo_loca"

# Navigazione rapida nella sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("**Navigazione**")
if st.session_state.drill_prov:
    if st.sidebar.button("🌍 ⬅ Torna all'Italia"):
        st.session_state.drill_prov = None
        st.session_state.drill_com = None
        st.rerun()
if st.session_state.drill_com:
    if st.sidebar.button(f"📍 ⬅ Torna a {st.session_state.drill_prov['nome']}"):
        st.session_state.drill_com = None
        st.rerun()

# Alias per leggibilità
drill_prov = st.session_state.drill_prov
drill_com  = st.session_state.drill_com

# ============================================================
# LIVELLO 1 — Mappa Province
# ============================================================
if drill_prov is None:
    st.title("🗺️ Mappa Prezzi Immobiliari — Italia")
    st.caption("💡 **Clicca su una provincia** sulla mappa per espanderla e vedere i Comuni al suo interno.")

    query_prov = f"""
    SELECT ap.id AS prov_id, p.nome AS prov_nome, AVG(ap.{col_prezzo}) AS prezzo_medio
    FROM agg_provincia ap
    JOIN provincia p ON ap.id = p.id
    WHERE ap.semestre_id = ? AND ap.utilizzo_id = ? AND ap.{col_prezzo} > 0
    GROUP BY ap.id, p.nome
    """
    df_prov = run_query(query_prov, (sel_semestre, sel_utilizzo))
    gj_prov = load_geojson_province()

    if not df_prov.empty and gj_prov:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Province con dati", len(df_prov))
        k2.metric("Media Nazionale", f"€ {df_prov['prezzo_medio'].mean():.0f}/mq")
        top_r = df_prov.nlargest(1, 'prezzo_medio').iloc[0]
        bot_r = df_prov.nsmallest(1, 'prezzo_medio').iloc[0]
        k3.metric("🔴 Più cara", f"{top_r['prov_nome']}  —  €{top_r['prezzo_medio']:.0f}")
        k4.metric("🟢 Più economica", f"{bot_r['prov_nome']}  —  €{bot_r['prezzo_medio']:.0f}")

        fig = make_choropleth(df_prov, gj_prov, "prov_id", "properties.prov_acr", "prezzo_medio", "prov_nome", metrica)
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="map_l1", selection_mode="points")

        # Gestione click sulla mappa
        if event and getattr(event, 'selection', None) and event.selection.points:
            pt = event.selection.points[0]
            prov_id = pt.get('location')
            if prov_id:
                row = df_prov[df_prov['prov_id'] == prov_id]
                if not row.empty:
                    st.session_state.drill_prov = {'id': prov_id, 'nome': row.iloc[0]['prov_nome']}
                    st.session_state.drill_com = None
                    st.rerun()

        # Grafici di supporto Top/Flop
        st.markdown("---")
        ca, cb = st.columns(2)
        with ca:
            df_t = df_prov.nlargest(10, 'prezzo_medio').sort_values('prezzo_medio', ascending=True)
            ft = px.bar(df_t, x='prezzo_medio', y='prov_nome', orientation='h', text_auto='.0f',
                        color='prezzo_medio', color_continuous_scale='Reds',
                        labels={'prezzo_medio': metrica, 'prov_nome': ''},
                        title="🏆 Top 10 Province più care")
            ft.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=40,b=0), height=360)
            st.plotly_chart(ft, use_container_width=True)
        with cb:
            df_b = df_prov.nsmallest(10, 'prezzo_medio').sort_values('prezzo_medio', ascending=False)
            fb = px.bar(df_b, x='prezzo_medio', y='prov_nome', orientation='h', text_auto='.0f',
                        color='prezzo_medio', color_continuous_scale='Greens_r',
                        labels={'prezzo_medio': metrica, 'prov_nome': ''},
                        title="📉 Flop 10 Province più economiche")
            fb.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=40,b=0), height=360)
            st.plotly_chart(fb, use_container_width=True)

        with st.expander("📋 Classifica completa Province"):
            df_tbl = df_prov.sort_values('prezzo_medio', ascending=False).copy()
            df_tbl['#'] = range(1, len(df_tbl)+1)
            df_tbl['prezzo_medio'] = df_tbl['prezzo_medio'].round(0).astype(int)
            df_tbl = df_tbl.rename(columns={'prov_id': 'Sigla', 'prov_nome': 'Provincia', 'prezzo_medio': metrica})[['#', 'Sigla', 'Provincia', metrica]]
            st.dataframe(df_tbl, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Scarica CSV", df_tbl.to_csv(index=False).encode(), f"province_{sel_semestre}.csv", "text/csv")
    elif df_prov.empty:
        st.info("Nessun dato per i filtri selezionati.")
    else:
        st.warning("GeoJSON non disponibile. Verifica la connessione internet.")

# ============================================================
# LIVELLO 2 — Mappa Comuni della Provincia selezionata
# ============================================================
elif drill_com is None:
    prov = drill_prov
    st.title(f"🗺️ Provincia di {prov['nome']} — Comuni")
    st.markdown(f"📍 **Italia** › **{prov['nome']}** &nbsp; | &nbsp; 💡 **Clicca su un comune** per vedere le zone, oppure sceglilo dal menu qui sotto.")

    query_comuni = f"""
    SELECT id, nome, {col_prezzo} AS prezzo_medio
    FROM agg_comune
    WHERE provincia_id = ? AND semestre_id = ? AND utilizzo_id = ? AND {col_prezzo} > 0
    ORDER BY {col_prezzo} DESC
    """
    df_com = run_query(query_comuni, (prov['id'], sel_semestre, sel_utilizzo))

    if df_com.empty:
        st.info("Nessun dato per i Comuni di questa Provincia con i filtri selezionati.")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Comuni con dati", len(df_com))
        k2.metric("Media Provincia", f"€ {df_com['prezzo_medio'].mean():.0f}/mq")
        top_c = df_com.iloc[0]
        bot_c = df_com.iloc[-1]
        k3.metric("🔴 Più caro", f"{top_c['nome']}  —  €{top_c['prezzo_medio']:.0f}")
        k4.metric("🟢 Più economico", f"{bot_c['nome']}  —  €{bot_c['prezzo_medio']:.0f}")

        # Carica GeoJSON comuni filtrato per provincia
        gj_com = get_geojson_provincia(prov['id'])

        if gj_com and len(gj_com['features']) > 0:
            fig_com = make_choropleth(df_com, gj_com, "nome", "id", "prezzo_medio", "nome", metrica)
            event_com = st.plotly_chart(fig_com, use_container_width=True, on_select="rerun", key="map_l2", selection_mode="points")

            if event_com and getattr(event_com, 'selection', None) and event_com.selection.points:
                pt = event_com.selection.points[0]
                com_nome = pt.get('location')
                if com_nome:
                    row = df_com[df_com['nome'] == com_nome]
                    if not row.empty:
                        st.session_state.drill_com = {'id': row.iloc[0]['id'], 'nome': com_nome}
                        st.rerun()
        else:
            st.info("ℹ️ GeoJSON comuni non caricato o non disponibile — usa il grafico e il menu sotto per navigare.")

        # Grafico a barre (complemento visivo o fallback)
        st.markdown("---")
        st.subheader("Classifica Comuni per Prezzo")
        n_bar = st.slider("Comuni da mostrare nel grafico", 10, min(len(df_com), 100), min(30, len(df_com)), step=10, key="sl_com")
        df_bar = df_com.head(n_bar).sort_values('prezzo_medio', ascending=True)
        fig_bar = px.bar(
            df_bar, x='prezzo_medio', y='nome', orientation='h', text_auto='.0f',
            color='prezzo_medio', color_continuous_scale='RdYlGn_r',
            labels={'prezzo_medio': metrica, 'nome': ''}
        )
        fig_bar.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=10,b=0),
                              height=max(400, n_bar * 22))
        with st.container(height=500):
            st.plotly_chart(fig_bar, use_container_width=True)

        # Selezione alternativa via menu a discesa
        st.markdown("---")
        st.subheader("Seleziona un Comune")
        com_opts = ["— scegli —"] + df_com['nome'].tolist()
        sel_com = st.selectbox("Comune", com_opts, label_visibility="collapsed", key="sel_com_dd")
        if sel_com != "— scegli —":
            row = df_com[df_com['nome'] == sel_com]
            if not row.empty:
                st.session_state.drill_com = {'id': row.iloc[0]['id'], 'nome': sel_com}
                st.rerun()

# ============================================================
# LIVELLO 3 — Dettaglio Zone del Comune selezionato
# ============================================================
else:
    prov = drill_prov
    com  = drill_com
    st.title(f"📍 {com['nome']} — Zone")
    st.markdown(f"**Italia** › **{prov['nome']}** › **{com['nome']}**")
    st.info("ℹ️ I poligoni geografici delle zone OMI non sono pubblici — vengono mostrati i dati numerici di ciascuna zona.")

    # Zone del semestre corrente
    query_zone_curr = f"""
    SELECT nome, {col_prezzo} AS prezzo_medio, prezzo_compra, prezzo_loca,
           CASE WHEN prezzo_compra > 0 AND prezzo_loca > 0
                THEN (prezzo_loca * 12.0 / prezzo_compra) * 100
                ELSE NULL END AS roi
    FROM agg_zona
    WHERE comune_id = ? AND semestre_id = ? AND utilizzo_id = ? AND {col_prezzo} > 0
    ORDER BY {col_prezzo} DESC
    """
    df_zone = run_query(query_zone_curr, (com['id'], sel_semestre, sel_utilizzo))

    # Storico del comune (tutti i semestri)
    query_trend_com = f"""
    SELECT semestre_id, AVG({col_prezzo}) AS prezzo_medio
    FROM agg_comune
    WHERE id = ? AND utilizzo_id = ? AND {col_prezzo} > 0
    ORDER BY semestre_id ASC
    """
    df_trend = run_query(query_trend_com, (com['id'], sel_utilizzo))
    if not df_trend.empty:
        df_trend['sem_label'] = df_trend['semestre_id'].apply(fmt_sem)

    # KPI
    if not df_zone.empty:
        k1, k2, k3 = st.columns(3)
        k1.metric("Zone censite", len(df_zone))
        k2.metric("Zona più cara", f"{df_zone.iloc[0]['nome']}  —  €{df_zone.iloc[0]['prezzo_medio']:.0f}/mq")
        k3.metric("Zona più economica", f"{df_zone.iloc[-1]['nome']}  —  €{df_zone.iloc[-1]['prezzo_medio']:.0f}/mq")

    st.markdown("---")
    col_z1, col_z2 = st.columns([1, 1])

    with col_z1:
        st.subheader(f"Prezzi Zone — {sel_sem_label}")
        if not df_zone.empty:
            fig_zone = px.bar(
                df_zone.sort_values('prezzo_medio', ascending=True),
                x='prezzo_medio', y='nome', orientation='h', text_auto='.0f',
                color='prezzo_medio', color_continuous_scale='RdYlGn_r',
                labels={'prezzo_medio': metrica, 'nome': 'Zona OMI'}
            )
            fig_zone.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=10,b=0),
                                   height=max(300, len(df_zone) * 44))
            st.plotly_chart(fig_zone, use_container_width=True)
        else:
            st.info("Nessun dato zone per questo comune.")

    with col_z2:
        st.subheader(f"Andamento Storico — {com['nome']}")
        if not df_trend.empty:
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=df_trend['sem_label'], y=df_trend['prezzo_medio'],
                mode='lines+markers', line=dict(color='royalblue', width=2.5),
                marker=dict(size=5), name='Media Comune'
            ))
            fig_trend.update_layout(
                xaxis_title="Semestre", yaxis_title=metrica,
                margin=dict(l=0,r=0,t=10,b=0), height=max(300, len(df_zone) * 44),
                hovermode="x unified"
            )
            fig_trend.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Nessun dato storico per questo comune.")

    # ROI per zona
    if not df_zone.empty and df_zone['roi'].notna().any():
        st.markdown("---")
        st.subheader("Rendimento da Locazione (ROI) per Zona")
        df_roi_z = df_zone.dropna(subset=['roi']).sort_values('roi', ascending=True)
        fig_roi_z = px.bar(
            df_roi_z, x='roi', y='nome', orientation='h', text_auto='.1f',
            color='roi', color_continuous_scale='Viridis',
            labels={'roi': 'ROI Lordo Annuo (%)', 'nome': 'Zona OMI'}
        )
        fig_roi_z.update_traces(texttemplate='%{x:.1f}%')
        fig_roi_z.update_layout(coloraxis_showscale=False, margin=dict(l=0,r=0,t=10,b=0),
                                height=max(250, len(df_roi_z) * 44))
        st.plotly_chart(fig_roi_z, use_container_width=True)

    # Tabella dettaglio zone + download
    if not df_zone.empty:
        st.markdown("---")
        with st.expander("📋 Tabella dettagliata Zone"):
            df_disp = df_zone[['nome', 'prezzo_compra', 'prezzo_loca', 'roi']].rename(columns={
                'nome': 'Zona OMI',
                'prezzo_compra': 'Compravendita (€/mq)',
                'prezzo_loca': 'Locazione (€/mq/mese)',
                'roi': 'ROI Lordo (%)'
            }).round(1)
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Scarica CSV zone",
                df_disp.to_csv(index=False).encode(),
                f"zone_{com['nome'].replace(' ','_')}_{sel_semestre}.csv",
                "text/csv"
            )
