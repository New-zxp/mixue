import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data' / 'research.sqlite3'

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, created TEXT, meta TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS pois(dataset TEXT, id TEXT, payload TEXT, PRIMARY KEY(dataset,id));
    CREATE TABLE IF NOT EXISTS queries(dataset TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, dataset TEXT, created TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, payload TEXT);
    CREATE TABLE IF NOT EXISTS sensitivity(id TEXT PRIMARY KEY, dataset TEXT, created TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS exclusions(dataset TEXT, id TEXT, payload TEXT, PRIMARY KEY(dataset,id));
    ''')
    return con

def datasets():
    with connect() as c:
        return [dict(r) | {'meta':json.loads(r['meta'])} for r in c.execute('SELECT * FROM datasets ORDER BY created DESC')]

def get_dataset(dataset):
    with connect() as c:
        row=c.execute('SELECT * FROM datasets WHERE id=?',(dataset,)).fetchone()
        if not row: raise ValueError('数据集不存在')
        pois=[json.loads(r[0]) for r in c.execute('SELECT payload FROM pois WHERE dataset=? ORDER BY id',(dataset,))]
        queries=[json.loads(r[0]) for r in c.execute('SELECT payload FROM queries WHERE dataset=?',(dataset,))]
    return dict(row) | {'meta':json.loads(row['meta']), 'pois':pois, 'queries':queries}

def save_dataset(dataset,status,meta):
    with connect() as c:c.execute('UPDATE datasets SET status=?,meta=? WHERE id=?',(status,json.dumps(meta,ensure_ascii=False),dataset))

def list_exclusions(dataset):
    with connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT payload FROM exclusions WHERE dataset=?',(dataset,))]
