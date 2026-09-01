import sqlite3
import time

print("Creating indexes...")
start = time.time()
conn = sqlite3.connect('db/quotazioni_clean.db')
c = conn.cursor()

c.execute("CREATE INDEX IF NOT EXISTS idx_quotazioni_zona ON quotazioni(zona_id);")
print("1/5")
c.execute("CREATE INDEX IF NOT EXISTS idx_quotazioni_semestre ON quotazioni(semestre_id);")
print("2/5")
c.execute("CREATE INDEX IF NOT EXISTS idx_quotazioni_utilizzo ON quotazioni(utilizzo_id);")
print("3/5")
c.execute("CREATE INDEX IF NOT EXISTS idx_zona_comune ON zona(comune_id);")
print("4/5")
c.execute("CREATE INDEX IF NOT EXISTS idx_comune_provincia ON comune(provincia_id);")
print("5/5")

conn.commit()
conn.close()
print(f"Done in {time.time()-start:.2f} seconds!")
