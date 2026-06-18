"""
db.py - SQLite handler for scan records.
"""
import sqlite3
import os
from config_loader import cfg


def _get_path():
    if getattr(__import__("sys"), "frozen", False):
        base = os.path.dirname(__import__("sys").executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, cfg.DB_PATH)


def init_db():
    conn = sqlite3.connect(_get_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_code     TEXT NOT NULL,
            filename    TEXT NOT NULL,
            saved_to    TEXT NOT NULL,
            timestamp   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def insert_scan(qr_code: str, filename: str, saved_to: str, timestamp: str):
    conn = sqlite3.connect(_get_path())
    conn.execute(
        "INSERT INTO scans (qr_code, filename, saved_to, timestamp) VALUES (?, ?, ?, ?)",
        (qr_code, filename, saved_to, timestamp)
    )
    conn.commit()
    conn.close()


def get_recent(limit: int = 50):
    conn = sqlite3.connect(_get_path())
    cur  = conn.execute(
        "SELECT qr_code, filename, saved_to, timestamp FROM scans ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows
