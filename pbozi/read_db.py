import sqlite3
conn = sqlite3.connect('backend/jgpti.db')
cursor = conn.cursor()
cursor.execute("SELECT id, title, trigger_phrases_json FROM telegram_groups")
rows = cursor.fetchall()
for r in rows:
    print(f"ID: {r[0]}, Title: {r[1]}, Triggers: {r[2]}")
conn.close()
