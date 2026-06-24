import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_URL", "sqlite:///./storage/skillbridge.db").replace("sqlite:///", ""))
if not DB_PATH.is_absolute():
    DB_PATH = Path(__file__).resolve().parents[2] / DB_PATH


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS roles(
  role_id TEXT PRIMARY KEY,
  role_title TEXT NOT NULL,
  sector TEXT,
  track TEXT,
  description TEXT
);
CREATE TABLE IF NOT EXISTS role_key_tasks(
  role_id TEXT,
  critical_work_function TEXT,
  key_task TEXT
);
CREATE TABLE IF NOT EXISTS role_skills(
  role_id TEXT,
  skill_code TEXT,
  skill_title TEXT NOT NULL,
  skill_type TEXT NOT NULL,
  proficiency_level INTEGER
);
CREATE TABLE IF NOT EXISTS unique_skills(
  unique_skill_id TEXT PRIMARY KEY,
  skill_title TEXT NOT NULL,
  skill_description TEXT,
  skill_type TEXT NOT NULL,
  is_emerging INTEGER DEFAULT 0,
  is_casl INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tsc_to_unique(
  skill_code TEXT,
  skill_title TEXT,
  skill_pl INTEGER,
  unique_skill_title TEXT,
  unique_skill_desc TEXT,
  unique_skill_type TEXT,
  sector_tagging TEXT
);
CREATE TABLE IF NOT EXISTS skill_ka(
  skill_code TEXT,
  proficiency_level INTEGER,
  proficiency_description TEXT,
  knowledge_items TEXT,
  ability_items TEXT
);
CREATE TABLE IF NOT EXISTS unique_skill_role_frequency(
  unique_skill_title TEXT PRIMARY KEY,
  role_count INTEGER NOT NULL
);
"""


def ensure_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM roles").fetchone()["c"]
    if count == 0:
        from app.data.demo_seed import seed_demo_data

        seed_demo_data()

