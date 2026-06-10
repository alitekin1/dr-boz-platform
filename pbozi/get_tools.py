import sqlite3

conn = sqlite3.connect('backend/jgpti.db')
cursor = conn.cursor()

cursor.execute("SELECT id, tool_id, arguments, result, status, error FROM tool_calls ORDER BY id DESC LIMIT 2;")
rows = cursor.fetchall()
for row in rows:
    print(row)
