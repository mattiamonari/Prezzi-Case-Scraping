import sqlite3
import time

conn = sqlite3.connect('db/quotazioni_clean.db')
c = conn.cursor()

print("1/3 Creazione tabella aggregata Province...")
start = time.time()
c.execute("DROP TABLE IF EXISTS agg_provincia")
c.execute("""
CREATE TABLE agg_provincia AS
SELECT 
    p.id as id, 
    p.nome as nome,
    'Nazionale' as sub,
    q.semestre_id,
    q.utilizzo_id,
    AVG(val_compravendita_min + val_compravendita_max)/2.0 as prezzo_compra,
    AVG(val_locazione_min + val_locazione_max)/2.0 as prezzo_loca
FROM quotazioni q
JOIN zona z ON q.zona_id = z.id
JOIN comune c ON z.comune_id = c.id
JOIN provincia p ON c.provincia_id = p.id
WHERE val_compravendita_max > 0 OR val_locazione_max > 0
GROUP BY p.id, p.nome, q.semestre_id, q.utilizzo_id
""")
c.execute("CREATE INDEX idx_agg_prov_sem_util ON agg_provincia(semestre_id, utilizzo_id)")
print(f"Completato in {time.time()-start:.2f}s")

print("2/3 Creazione tabella aggregata Comuni...")
start = time.time()
c.execute("DROP TABLE IF EXISTS agg_comune")
c.execute("""
CREATE TABLE agg_comune AS
SELECT 
    c.id as id, 
    c.nome as nome,
    p.nome || ' (' || p.id || ')' as sub,
    p.id as provincia_id,
    q.semestre_id,
    q.utilizzo_id,
    AVG(val_compravendita_min + val_compravendita_max)/2.0 as prezzo_compra,
    AVG(val_locazione_min + val_locazione_max)/2.0 as prezzo_loca
FROM quotazioni q
JOIN zona z ON q.zona_id = z.id
JOIN comune c ON z.comune_id = c.id
JOIN provincia p ON c.provincia_id = p.id
WHERE val_compravendita_max > 0 OR val_locazione_max > 0
GROUP BY c.id, c.nome, p.id, p.nome, q.semestre_id, q.utilizzo_id
""")
c.execute("CREATE INDEX idx_agg_comune_sem_util ON agg_comune(semestre_id, utilizzo_id)")
c.execute("CREATE INDEX idx_agg_comune_prov ON agg_comune(provincia_id)")
print(f"Completato in {time.time()-start:.2f}s")

print("3/3 Creazione tabella aggregata Zone...")
start = time.time()
c.execute("DROP TABLE IF EXISTS agg_zona")
c.execute("""
CREATE TABLE agg_zona AS
SELECT 
    z.id as id, 
    z.fascia_descrizione as nome,
    c.nome || ' (' || p.id || ')' as sub,
    c.id as comune_id,
    p.id as provincia_id,
    q.semestre_id,
    q.utilizzo_id,
    AVG(val_compravendita_min + val_compravendita_max)/2.0 as prezzo_compra,
    AVG(val_locazione_min + val_locazione_max)/2.0 as prezzo_loca
FROM quotazioni q
JOIN zona z ON q.zona_id = z.id
JOIN comune c ON z.comune_id = c.id
JOIN provincia p ON c.provincia_id = p.id
WHERE val_compravendita_max > 0 OR val_locazione_max > 0
GROUP BY z.id, z.fascia_descrizione, c.id, c.nome, p.id, q.semestre_id, q.utilizzo_id
""")
c.execute("CREATE INDEX idx_agg_zona_sem_util ON agg_zona(semestre_id, utilizzo_id)")
c.execute("CREATE INDEX idx_agg_zona_comune ON agg_zona(comune_id)")
print(f"Completato in {time.time()-start:.2f}s")

conn.commit()
conn.close()
print("Finito!")
