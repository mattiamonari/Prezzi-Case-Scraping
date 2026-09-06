import streamlit as st
import pandas as pd
import plotly.express as px
from db_utils import get_db_connection

st.set_page_config(page_title="Analisi Avanzata", layout="wide", page_icon="📊")

st.title("📊 Analisi Avanzata & Rendimenti")
st.markdown("""
Esplora i dati immobiliari sotto nuove lenti: prezzi assoluti, rendimento da locazione (ROI), 
polarizzazione interna dei comuni e resilienza storica. Infine, un indice composito **Best Value** 
per identificare le opportunità di investimento più interessanti.
""")

# --- HELPER ---
@st.cache_data(show_spinner=False)
def run_query(query, params=()):
    try:
        conn = get_db_connection()
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Errore SQL:\n{e}\n\nQuery:\n{query}\n\nParams:\n{params}")
        return pd.DataFrame()

def fmt_sem(s):
    s = str(s)
    return s[:4] + " (" + ('Gen-Giu' if s[4:] == '1' else 'Lug-Dic') + ")"

def normalize_series(s):
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - mn) / (mx - mn)

def csv_download(df, filename, label="⬇️ Scarica CSV"):
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filtri Globali")

df_utilizzi = run_query("SELECT id FROM utilizzo")
utilizzi_opts = df_utilizzi['id'].tolist()
sel_utilizzo = st.sidebar.selectbox("Destinazione d'Uso", options=utilizzi_opts, index=1 if len(utilizzi_opts) > 1 else 0)

# Semestre con label leggibile
df_sems = run_query("SELECT id FROM semestre ORDER BY id ASC")
tutti_sems = df_sems['id'].tolist() if not df_sems.empty else []
sem_labels = [fmt_sem(s) for s in tutti_sems]
sel_sem_label = st.sidebar.selectbox("Semestre di Riferimento", options=sem_labels[::-1])
sel_semestre = tutti_sems[sem_labels.index(sel_sem_label)]

df_province = run_query("SELECT id, nome FROM provincia ORDER BY nome")
prov_opts = {"Tutta Italia": "TUTTI"}
prov_opts.update(dict(zip(df_province['nome'], df_province['id'])))
sel_prov_nome = st.sidebar.selectbox("Provincia", options=list(prov_opts.keys()))
provincia_id = prov_opts[sel_prov_nome]

livello = st.sidebar.radio("Livello di Dettaglio (per Top & Flop)", options=["Comune", "Zona"])
table_name = "agg_comune" if livello == "Comune" else "agg_zona"

# --- BASE WHERE ---
where_clause = ["semestre_id = ?", "utilizzo_id = ?"]
params_base = [sel_semestre, sel_utilizzo]
if provincia_id != "TUTTI":
    where_clause.append("provincia_id = ?")
    params_base.append(provincia_id)
where_sql = "WHERE " + " AND ".join(where_clause)


# ====================================================================
# SEZIONE 1: TOP & FLOP PREZZI ASSOLUTI
# ====================================================================
st.markdown("---")
st.header("1. Top & Flop Prezzi Assoluti")
st.markdown(f"Scopri le/i **{livello.lower()}i** più costose/i e più economiche/i nel semestre selezionato.")

col_m, col_s = st.columns([2, 1])
with col_m:
    metrica_tf = st.radio(
        "Metrica per la classifica:",
        ["Compravendita (€/mq)", "Locazione (€/mq x mese)"],
        horizontal=True
    )
with col_s:
    num_top_flop = st.slider("Risultati da mostrare", min_value=10, max_value=100, value=10, step=10)

col_prezzo = "prezzo_compra" if metrica_tf == "Compravendita (€/mq)" else "prezzo_loca"

query_base_tf = f"""
SELECT nome, sub, {col_prezzo} as prezzo
FROM {table_name}
{where_sql} AND {col_prezzo} > 0
"""

df_top = run_query(query_base_tf + f" ORDER BY prezzo DESC LIMIT {num_top_flop}", tuple(params_base))
df_flop = run_query(query_base_tf + f" ORDER BY prezzo ASC LIMIT {num_top_flop}", tuple(params_base))

if not df_top.empty and not df_flop.empty:
    col1, col2 = st.columns(2)
    plot_height = max(400, num_top_flop * 25)

    with col1:
        st.subheader(f"🏆 I {num_top_flop} {livello}i Più Costosi")
        df_top_plot = df_top.sort_values('prezzo', ascending=True)
        fig_top = px.bar(
            df_top_plot, x='prezzo', y='nome', text_auto='.0f', orientation='h',
            hover_data=['sub'], labels={'nome': '', 'prezzo': metrica_tf},
            color='prezzo', color_continuous_scale='Reds'
        )
        fig_top.update_layout(height=plot_height, margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False)
        with st.container(height=500):
            st.plotly_chart(fig_top, use_container_width=True)
        csv_download(df_top, f"top_{num_top_flop}_{livello.lower()}_piu_cari.csv", f"⬇️ Scarica Top {num_top_flop}")

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
        csv_download(df_flop, f"flop_{num_top_flop}_{livello.lower()}_piu_economici.csv", f"⬇️ Scarica Flop {num_top_flop}")
else:
    st.info("Nessun dato disponibile per i filtri selezionati.")


# ====================================================================
# SEZIONE 2: RENDIMENTO DA LOCAZIONE (ROI)
# ====================================================================
st.markdown("---")
st.header("2. Rendimento da Locazione (ROI Lordo)")
st.markdown(f"""
Il rendimento percentuale annuo indica quanto rende affittare un immobile rispetto al prezzo d'acquisto.  
*(Calcolato a livello di **{livello}** come: Affitto mensile × 12 / Prezzo compravendita)*
""")

col_roi_a, col_roi_b = st.columns([3, 1])
with col_roi_a:
    min_prezzo_roi = st.slider(
        "Filtra: Prezzo compravendita minimo (€/mq) — esclude outlier con prezzi anomali",
        min_value=0, max_value=3000, value=300, step=100,
        help="Impostare un minimo (es. 300 €/mq) evita che comuni con prezzi d'acquisto bassissimi o errati gonfiino il ROI in modo irrealistico."
    )
with col_roi_b:
    num_roi = st.slider("Risultati ROI", min_value=5, max_value=30, value=15, step=5)

query_roi = f"""
SELECT nome, sub, prezzo_compra, prezzo_loca, 
       ((prezzo_loca * 12.0) / prezzo_compra) * 100 AS roi
FROM {table_name}
{where_sql} AND prezzo_compra >= ? AND prezzo_loca > 0
ORDER BY roi DESC
LIMIT {num_roi}
"""
df_roi = run_query(query_roi, tuple(params_base + [min_prezzo_roi]))

if not df_roi.empty:
    df_roi_plot = df_roi.sort_values('roi', ascending=True)
    fig_roi = px.bar(
        df_roi_plot, x='roi', y='nome', text_auto='.1f', orientation='h',
        hover_data={
            'sub': True, 
            'prezzo_compra': ':.0f', 
            'prezzo_loca': ':.1f', 
            'roi': ':.2f',
            'nome': False
        },
        labels={'nome': '', 'roi': 'ROI Lordo Annuo (%)', 'prezzo_compra': 'Compravendita (€/mq)', 'prezzo_loca': 'Locazione (€/mq/mese)'},
        color='roi', color_continuous_scale='Viridis'
    )
    fig_roi.update_layout(margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False, height=max(400, num_roi * 30))
    fig_roi.update_traces(texttemplate='%{x:.1f}%')
    st.plotly_chart(fig_roi, use_container_width=True)
    csv_download(df_roi, f"roi_{livello.lower()}_{sel_semestre}.csv", "⬇️ Scarica dati ROI (CSV)")
else:
    st.info("Dati insufficienti per calcolare il ROI. Prova ad abbassare il filtro prezzo minimo.")


# ====================================================================
# SEZIONE 3: POLARIZZAZIONE (Forbice Prezzi nei Comuni)
# ====================================================================
st.markdown("---")
st.header("3. Analisi della Polarizzazione (Forbice di Prezzo)")
st.markdown("""
In quali Comuni c'è la maggiore differenza di prezzo tra la zona più cara e quella più economica?  
*N.B. L'analisi è basata sulle "Fasce/Zone" OMI all'interno dello stesso Comune.*
""")

where_clause_pol = ["z.semestre_id = ?", "z.utilizzo_id = ?"]
params_pol = [sel_semestre, sel_utilizzo]
if provincia_id != "TUTTI":
    where_clause_pol.append("z.provincia_id = ?")
    params_pol.append(provincia_id)
where_sql_pol = "WHERE " + " AND ".join(where_clause_pol)

query_pol = f"""
SELECT 
    c.nome AS comune, 
    p.nome AS provincia,
    MAX(z.prezzo_compra) AS max_prezzo, 
    MIN(z.prezzo_compra) AS min_prezzo,
    (MAX(z.prezzo_compra) - MIN(z.prezzo_compra)) AS forbice_assoluta,
    (MAX(z.prezzo_compra) / MIN(z.prezzo_compra)) AS forbice_relativa,
    COUNT(z.id) AS n_zone
FROM agg_zona z
JOIN comune c ON z.comune_id = c.id
JOIN provincia p ON z.provincia_id = p.id
{where_sql_pol} AND z.prezzo_compra > 0
GROUP BY c.id, c.nome, p.nome
HAVING COUNT(z.id) > 1
ORDER BY forbice_relativa DESC
LIMIT 20
"""
df_pol = run_query(query_pol, tuple(params_pol))

if not df_pol.empty:
    fig_pol = px.scatter(
        df_pol, x="min_prezzo", y="max_prezzo",
        size="forbice_relativa", color="forbice_assoluta",
        hover_name="comune",
        hover_data={
            "provincia": True,
            "forbice_assoluta": ":.0f",
            "forbice_relativa": ":.2f",
            "n_zone": True,
            "min_prezzo": ":.0f",
            "max_prezzo": ":.0f"
        },
        labels={
            "min_prezzo": "Prezzo Minimo in Comune (€/mq)",
            "max_prezzo": "Prezzo Massimo in Comune (€/mq)",
            "forbice_assoluta": "Diff. Assoluta (€)",
            "forbice_relativa": "Rapporto Max/Min",
            "n_zone": "N. Zone"
        },
        title="Disuguaglianza intra-comunale (bolla = rapporto Max/Min, colore = differenza assoluta €)",
        color_continuous_scale="Turbo"
    )
    max_val = max(df_pol['max_prezzo'].max(), df_pol['min_prezzo'].max())
    fig_pol.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color="grey", dash="dash", width=1))
    fig_pol.add_annotation(x=max_val * 0.7, y=max_val * 0.72, text="Nessuna forbice", showarrow=False, font=dict(color="grey", size=11))
    fig_pol.update_layout(margin=dict(l=0, r=0, t=60, b=0))
    st.plotly_chart(fig_pol, use_container_width=True)

    with st.expander("📋 Tabella dati Polarizzazione"):
        df_pol_disp = df_pol.rename(columns={
            "comune": "Comune", "provincia": "Provincia",
            "max_prezzo": "Zona più cara (€/mq)", "min_prezzo": "Zona più economica (€/mq)",
            "forbice_assoluta": "Differenza (€)", "forbice_relativa": "Rapporto (x volte)", "n_zone": "N. Zone"
        }).round({"Differenza (€)": 0, "Rapporto (x volte)": 2})
        st.dataframe(df_pol_disp, use_container_width=True, hide_index=True)
        csv_download(df_pol, f"polarizzazione_{sel_semestre}_{sel_utilizzo}.csv", "⬇️ Scarica dati Polarizzazione (CSV)")
else:
    st.info("Nessuna forbice trovata. I Comuni selezionati potrebbero avere una sola zona censita.")


# ====================================================================
# SEZIONE 4: RESILIENZA E CRESCITA STORICA
# ====================================================================
st.markdown("---")
st.header("4. Resilienza dei Mercati (Comuni)")
st.markdown("""
Analizziamo l'**intero storico** per scoprire quali Comuni hanno registrato il maggior numero di semestri in crescita.  
*Un alto "Tasso di Resilienza" indica un mercato in ascesa costante, meno volatile.*
""")

if st.button("▶ Calcola Analisi Resilienza", key="btn_resilienza"):
    with st.spinner("Analisi dell'intero storico in corso..."):
        where_res = ["utilizzo_id = ?"]
        params_res = [sel_utilizzo]
        if provincia_id != "TUTTI":
            where_res.append("provincia_id = ?")
            params_res.append(provincia_id)
        where_sql_res = "WHERE " + " AND ".join(where_res)

        df_hist = run_query(
            f"SELECT id, nome, sub, semestre_id, prezzo_compra FROM agg_comune {where_sql_res} AND prezzo_compra > 0 ORDER BY id, semestre_id ASC",
            tuple(params_res)
        )

        if not df_hist.empty:
            df_hist = df_hist.sort_values(['id', 'semestre_id'])
            df_hist['prev_prezzo'] = df_hist.groupby('id')['prezzo_compra'].shift(1)
            df_hist['is_growth'] = df_hist['prezzo_compra'] > (df_hist['prev_prezzo'] * 1.01)

            df_resilience = df_hist.groupby(['id', 'nome', 'sub']).agg(
                total_semesters=('semestre_id', 'count'),
                growth_semesters=('is_growth', 'sum'),
                latest_price=('prezzo_compra', 'last')
            ).reset_index()
            df_resilience = df_resilience[df_resilience['total_semesters'] > 4]

            if not df_resilience.empty:
                df_resilience['tasso_resilienza_perc'] = (
                    df_resilience['growth_semesters'] / (df_resilience['total_semesters'] - 1)
                ) * 100
                df_resilience = df_resilience.sort_values(
                    by=['tasso_resilienza_perc', 'growth_semesters'], ascending=[False, False]
                ).head(20)

                df_res_plot = df_resilience.sort_values('tasso_resilienza_perc', ascending=True)
                fig_res = px.bar(
                    df_res_plot, x='tasso_resilienza_perc', y='nome', text_auto='.0f', orientation='h',
                    hover_data={
                        'sub': True,
                        'growth_semesters': True,
                        'total_semesters': True,
                        'latest_price': ':.0f',
                        'nome': False
                    },
                    labels={
                        'nome': '', 'tasso_resilienza_perc': '% di semestri in crescita',
                        'growth_semesters': 'Semestri in crescita', 'total_semesters': 'Semestri totali',
                        'latest_price': 'Prezzo attuale (€/mq)'
                    },
                    color='tasso_resilienza_perc', color_continuous_scale='Blues'
                )
                fig_res.update_layout(margin=dict(l=0, r=0, t=30, b=0), coloraxis_showscale=False)
                fig_res.update_traces(texttemplate='%{x:.0f}%')
                st.plotly_chart(fig_res, use_container_width=True)
                csv_download(df_resilience, f"resilienza_{sel_utilizzo}.csv", "⬇️ Scarica dati Resilienza (CSV)")
            else:
                st.info("Nessun comune ha storico sufficiente (>4 semestri) con i filtri selezionati.")
        else:
            st.info("Nessuno storico trovato per i filtri selezionati.")


# ====================================================================
# SEZIONE 5: BEST VALUE — INDICE COMPOSITO DI OPPORTUNITÀ
# ====================================================================
st.markdown("---")
st.header("5. 💎 Best Value — Opportunità di Investimento")
st.markdown("""
Un **indice composito** che combina tre fattori per identificare i Comuni con il maggior **potenziale di investimento**:

| Fattore | Peso | Logica |
|---|---|---|
| 🏷️ **Prezzo basso** | 40% | Più il comune è economico rispetto alla media, più punteggio guadagna |
| 💰 **ROI alto** | 35% | Miglior rendimento netto da affitto |
| 📈 **Resilienza alta** | 25% | Crescita storica costante nel tempo |

*Più alto è il punteggio finale (0–1), maggiore è il potenziale di investimento combinato.*
""")

col_bv_a, col_bv_b = st.columns([3, 1])
with col_bv_a:
    min_prezzo_bv = st.slider(
        "Prezzo compravendita minimo per escludere outlier (€/mq)",
        min_value=0, max_value=2000, value=300, step=100, key="bv_min_prezzo"
    )
with col_bv_b:
    top_bv = st.slider("Top N da mostrare", min_value=10, max_value=50, value=20, step=5, key="bv_top_n")

if st.button("▶ Calcola Best Value", key="btn_best_value"):
    with st.spinner("Calcolo indice composito in corso..."):
        # 1. Prezzi correnti + ROI
        where_bv = ["semestre_id = ?", "utilizzo_id = ?"]
        params_bv = [sel_semestre, sel_utilizzo]
        if provincia_id != "TUTTI":
            where_bv.append("provincia_id = ?")
            params_bv.append(provincia_id)

        df_bv_curr = run_query(f"""
            SELECT id, nome, sub, prezzo_compra, prezzo_loca,
                   CASE WHEN prezzo_compra > 0 AND prezzo_loca > 0 
                        THEN (prezzo_loca * 12.0 / prezzo_compra) * 100 
                        ELSE NULL END AS roi
            FROM agg_comune
            WHERE {" AND ".join(where_bv)} AND prezzo_compra >= ? AND prezzo_loca > 0
        """, tuple(params_bv + [min_prezzo_bv]))

        # 2. Storico per resilienza
        where_hist = ["utilizzo_id = ?"]
        params_hist = [sel_utilizzo]
        if provincia_id != "TUTTI":
            where_hist.append("provincia_id = ?")
            params_hist.append(provincia_id)

        df_hist_bv = run_query(f"""
            SELECT id, semestre_id, prezzo_compra
            FROM agg_comune
            WHERE {" AND ".join(where_hist)} AND prezzo_compra > 0
            ORDER BY id, semestre_id ASC
        """, tuple(params_hist))

        if not df_bv_curr.empty and not df_hist_bv.empty:
            df_hist_bv = df_hist_bv.sort_values(['id', 'semestre_id'])
            df_hist_bv['prev'] = df_hist_bv.groupby('id')['prezzo_compra'].shift(1)
            df_hist_bv['is_growth'] = df_hist_bv['prezzo_compra'] > (df_hist_bv['prev'] * 1.01)

            df_res_bv = df_hist_bv.groupby('id').agg(
                total_sems=('semestre_id', 'count'),
                growth_sems=('is_growth', 'sum')
            ).reset_index()
            df_res_bv = df_res_bv[df_res_bv['total_sems'] > 4]
            df_res_bv['resilienza'] = (df_res_bv['growth_sems'] / (df_res_bv['total_sems'] - 1)) * 100

            # Join
            df_score = df_bv_curr.merge(df_res_bv[['id', 'resilienza']], on='id', how='inner').dropna(subset=['roi', 'resilienza'])

            if not df_score.empty:
                df_score['prezzo_norm'] = normalize_series(df_score['prezzo_compra'])
                df_score['roi_norm'] = normalize_series(df_score['roi'])
                df_score['res_norm'] = normalize_series(df_score['resilienza'])

                # Score: prezzo basso = buono → (1 - prezzo_norm)
                df_score['score'] = (
                    (1 - df_score['prezzo_norm']) * 0.40 +
                    df_score['roi_norm'] * 0.35 +
                    df_score['res_norm'] * 0.25
                )

                df_score = df_score.sort_values('score', ascending=False).head(top_bv)

                # Scatter plot: x=prezzo, y=roi, size=resilienza, color=score
                fig_bv = px.scatter(
                    df_score,
                    x='prezzo_compra', y='roi',
                    size='resilienza', color='score',
                    hover_name='nome',
                    hover_data={
                        'sub': True,
                        'prezzo_compra': ':.0f',
                        'roi': ':.1f',
                        'resilienza': ':.0f',
                        'score': ':.3f'
                    },
                    labels={
                        'prezzo_compra': 'Prezzo Compravendita (€/mq)',
                        'roi': 'ROI Lordo Annuo (%)',
                        'score': 'Score Composito',
                        'resilienza': 'Resilienza (%)',
                        'sub': 'Provincia'
                    },
                    color_continuous_scale='Viridis',
                    title=f'Top {top_bv} Comuni Best Value — bolla = resilienza, colore = score composito'
                )
                fig_bv.update_layout(margin=dict(l=0, r=0, t=60, b=0), height=520)
                st.plotly_chart(fig_bv, use_container_width=True)

                # Tabella
                df_display = df_score[['nome', 'sub', 'prezzo_compra', 'roi', 'resilienza', 'score']].copy()
                df_display.columns = ['Comune', 'Provincia', 'Prezzo (€/mq)', 'ROI (%)', 'Resilienza (%)', 'Score']
                df_display = df_display.round({'Prezzo (€/mq)': 0, 'ROI (%)': 1, 'Resilienza (%)': 0, 'Score': 3})
                df_display['Rank'] = range(1, len(df_display) + 1)
                df_display = df_display[['Rank', 'Comune', 'Provincia', 'Prezzo (€/mq)', 'ROI (%)', 'Resilienza (%)', 'Score']]
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                csv_download(df_display, f"best_value_{sel_semestre}_{sel_utilizzo}.csv", "⬇️ Scarica classifica Best Value (CSV)")
            else:
                st.info("Dati insufficienti per calcolare il Best Value. Prova ad abbassare il prezzo minimo o scegliere 'Tutta Italia'.")
        elif df_bv_curr.empty:
            st.info("Nessun comune trovato con i filtri attuali (controlla il prezzo minimo).")
        else:
            st.info("Nessuno storico sufficiente per calcolare la resilienza.")
