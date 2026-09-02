import sqlite3
import pandas as pd
conn = sqlite3.connect('db/quotazioni_clean.db')

print("Comuni trovati:")
print(pd.read_sql_query("SELECT id, nome, provincia_id FROM comune WHERE nome LIKE '%MODENA%'", conn))

print("\nLog di scraping per Modena (F257):")
print(pd.read_sql_query("SELECT count(*) as semestri_completati FROM scraping_log WHERE comune_id = 'F257'", conn))

print("\nQuotazioni trovate per Modena (F257):")
query = """
SELECT count(*) as totale_quotazioni 
FROM quotazioni q 
JOIN zona z ON q.zona_id = z.id 
WHERE z.comune_id = 'F257'
"""
print(pd.read_sql_query(query, conn))
