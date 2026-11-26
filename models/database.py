"""SQLite 数据库初始化"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aiana.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    ingredient_type TEXT NOT NULL DEFAULT 'additive',
    category TEXT NOT NULL,
    safety_level TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    safe_limits TEXT,
    e_number TEXT,
    potential_risks TEXT NOT NULL DEFAULT '[]',
    common_products TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingredient_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_name TEXT NOT NULL,
    alias TEXT UNIQUE NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'alias',
    FOREIGN KEY (ingredient_name) REFERENCES ingredients(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scan_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'text',
    raw_text TEXT,
    ingredient_section TEXT,
    matched_json TEXT NOT NULL DEFAULT '[]',
    unknown_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ocr_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ocr_text TEXT UNIQUE NOT NULL,
    canonical_name TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'manual',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canonical_name) REFERENCES ingredients(name)
);

CREATE INDEX IF NOT EXISTS idx_aliases_alias ON ingredient_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_scan_user ON scan_history(user_id);
CREATE INDEX IF NOT EXISTS idx_scan_created ON scan_history(created_at);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def ingredient_count(db_path: Path = DB_PATH) -> int:
    if not db_path.exists():
        return 0
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM ingredients").fetchone()
        return int(row["c"])
    finally:
        conn.close()
