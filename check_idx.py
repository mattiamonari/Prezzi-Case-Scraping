import sqlite3
c=sqlite3.connect('db/quotazioni.db')
print("Indexes:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()])
