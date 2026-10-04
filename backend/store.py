import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.getenv('OBS_DB', 'data/observabilidade.sqlite3'))

@contextmanager
def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def save(event):
    with connection() as conn:
        conn.execute('INSERT INTO events(payload) VALUES (?)', (json.dumps(event, allow_nan=False),))

def read(limit=1000):
    with connection() as conn:
        return [dict(id=row[0], **json.loads(row[1])) for row in conn.execute(
            'SELECT id,payload FROM events ORDER BY id DESC LIMIT ?', (limit,))]
