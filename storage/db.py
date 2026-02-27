from __future__ import annotations

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    base_url TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',
    domains_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    is_selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    secret_name TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    masked_value TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    url_hash TEXT NOT NULL UNIQUE,
    draft_id TEXT,
    published_message_ids TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    origin_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    language TEXT NOT NULL,
    source_media_url TEXT,
    source_media_type TEXT,
    generated_image_url TEXT,
    status TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sources_type_enabled_priority
ON sources(source_type, enabled, priority, is_selected);

CREATE INDEX IF NOT EXISTS idx_creds_source_active
ON source_credentials(source_id, is_active);

CREATE INDEX IF NOT EXISTS idx_drafts_user_status
ON drafts(user_id, status);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA foreign_keys=ON;")
        await self.conn.executescript(SCHEMA_SQL)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None
