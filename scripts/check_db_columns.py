from utils.database import execute_query
cols = execute_query("PRAGMA table_info(chat_settings)", fetch_all=True)
print('columns:', [c[1] for c in cols] if cols else None)
