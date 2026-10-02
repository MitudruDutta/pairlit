import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


class Store:
    def __init__(self, path=None):
        self.path = path or os.getenv("PAIRLIT_DATABASE", "data/private/pairlit.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            for table in ["profiles", "dates", "jobs"]:
                c.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS profile_linkedin_unique ON profiles(json_extract(data, '$.linkedin_url'))"
            )
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS profile_instagram_unique ON profiles(json_extract(data, '$.instagram_url'))"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS runs (fingerprint TEXT PRIMARY KEY, data TEXT NOT NULL, cap REAL NOT NULL)"
            )
        Path(self.path).chmod(0o600)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        try:
            with c:
                yield c
        finally:
            c.close()

    def all(self, table):
        assert table in ["profiles", "dates", "jobs"]
        with self.db() as c:
            return [json.loads(r[0]) for r in c.execute(f"SELECT data FROM {table} ORDER BY rowid")]

    def get(self, table, id):
        assert table in ["profiles", "dates", "jobs"]
        with self.db() as c:
            r = c.execute(f"SELECT data FROM {table} WHERE id=?", (id,)).fetchone()
        if not r:
            raise ValueError("Record not found")
        return json.loads(r[0])

    def put(self, table, record):
        assert table in ["profiles", "dates", "jobs"]
        try:
            with self.db() as c:
                c.execute(
                    f"INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (record["id"], json.dumps(record, ensure_ascii=False)),
                )
        except sqlite3.IntegrityError:
            raise ValueError("This source account already belongs to an agent; reuse its existing profile") from None
        return record

    def patch(self, table, id, **fields):
        assert table in ["profiles", "dates", "jobs"]
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(f"SELECT data FROM {table} WHERE id=?", (id,)).fetchone()
            if not row:
                raise ValueError("Record not found")
            record = json.loads(row[0])
            record.update(fields)
            record["updated_at"] = now()
            c.execute(f"UPDATE {table} SET data=? WHERE id=?", (json.dumps(record, ensure_ascii=False), id))
        return record
