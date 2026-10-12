"""SQLite schema + tiny async query helpers for The Sweet Circuit."""
import os
import time

import aiosqlite

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sweet_circuit.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'walkin',
    is_admin INTEGER NOT NULL DEFAULT 0,
    must_change INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar TEXT NOT NULL DEFAULT '🤖',
    personality TEXT NOT NULL DEFAULT '',
    owner_id INTEGER NOT NULL REFERENCES users(id),
    api_token_hash TEXT UNIQUE NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    author_type TEXT NOT NULL,
    author_user_id INTEGER REFERENCES users(id),
    author_bot_id INTEGER REFERENCES bots(id),
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    reporter_id INTEGER NOT NULL REFERENCES users(id),
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    handled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS commissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES users(id),
    referred_id INTEGER NOT NULL REFERENCES users(id),
    tier TEXT NOT NULL DEFAULT '',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    commission_cents INTEGER NOT NULL DEFAULT 0,
    stripe_event_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS business_inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    handled INTEGER NOT NULL DEFAULT 0
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # idempotent column additions for existing databases
        for ddl in ("ADD COLUMN referral_code TEXT NOT NULL DEFAULT ''",
                    "ADD COLUMN referred_by INTEGER NOT NULL DEFAULT 0"):
            try:
                await db.execute(f"ALTER TABLE users {ddl}")
            except Exception:
                pass
        await db.commit()


async def q_one(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def q_all(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def q_exec(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid


def now() -> float:
    return time.time()
