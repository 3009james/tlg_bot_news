from __future__ import annotations

import json
from typing import Any, Iterable

from storage.crypto import SecretBox, mask_secret
from storage.db import Database


class Repository:
    def __init__(self, db: Database, secret_box: SecretBox) -> None:
        if db.conn is None:
            raise RuntimeError("Database is not connected")
        self._db = db
        self._conn = db.conn
        self._secret_box = secret_box

    async def log_action(self, actor_user_id: int, action: str, details: dict[str, Any] | None = None) -> None:
        await self._conn.execute(
            """
            INSERT INTO audit_log(actor_user_id, action, details_json)
            VALUES (?, ?, ?)
            """,
            (actor_user_id, action, json.dumps(details or {}, ensure_ascii=False)),
        )
        await self._conn.commit()

    async def add_source(
        self,
        name: str,
        source_type: str,
        base_url: str | None,
        priority: int = 100,
        domains: Iterable[str] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> int:
        cursor = await self._conn.execute(
            """
            INSERT INTO sources(name, source_type, base_url, priority, domains_json, settings_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                source_type,
                base_url,
                priority,
                json.dumps(list(domains or []), ensure_ascii=False),
                json.dumps(settings or {}, ensure_ascii=False),
            ),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def get_source(self, source_id: int) -> dict[str, Any] | None:
        cursor = await self._conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = await cursor.fetchone()
        return self._source_row_to_dict(row) if row else None

    async def list_sources(self) -> list[dict[str, Any]]:
        cursor = await self._conn.execute("SELECT * FROM sources ORDER BY is_selected DESC, priority ASC, id ASC")
        rows = await cursor.fetchall()
        return [self._source_row_to_dict(row) for row in rows]

    async def list_enabled_sources(self, source_type: str | None = None) -> list[dict[str, Any]]:
        if source_type:
            cursor = await self._conn.execute(
                """
                SELECT * FROM sources
                WHERE enabled = 1 AND source_type = ?
                ORDER BY is_selected DESC, priority ASC, id ASC
                """,
                (source_type,),
            )
        else:
            cursor = await self._conn.execute(
                """
                SELECT * FROM sources
                WHERE enabled = 1
                ORDER BY is_selected DESC, priority ASC, id ASC
                """
            )
        rows = await cursor.fetchall()
        return [self._source_row_to_dict(row) for row in rows]

    async def set_source_enabled(self, source_id: int, enabled: bool) -> None:
        await self._conn.execute(
            """
            UPDATE sources
            SET enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (1 if enabled else 0, source_id),
        )
        await self._conn.commit()

    async def set_source_selected(self, source_id: int) -> None:
        await self._conn.execute("UPDATE sources SET is_selected = 0, updated_at = CURRENT_TIMESTAMP")
        await self._conn.execute(
            "UPDATE sources SET is_selected = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (source_id,),
        )
        await self._conn.commit()

    async def update_source_priority(self, source_id: int, priority: int) -> None:
        await self._conn.execute(
            """
            UPDATE sources
            SET priority = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (priority, source_id),
        )
        await self._conn.commit()

    async def update_source_domains(self, source_id: int, domains: Iterable[str]) -> None:
        await self._conn.execute(
            """
            UPDATE sources
            SET domains_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(list(domains), ensure_ascii=False), source_id),
        )
        await self._conn.commit()

    async def update_source_config(
        self,
        source_id: int,
        base_url: str | None,
        settings: dict[str, Any] | None,
    ) -> None:
        source = await self.get_source(source_id)
        if not source:
            raise ValueError("Источник не найден")
        new_base_url = source.get("base_url") if base_url is None else base_url
        new_settings = source.get("settings") if settings is None else settings
        await self._conn.execute(
            """
            UPDATE sources
            SET base_url = ?, settings_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_base_url, json.dumps(new_settings or {}, ensure_ascii=False), source_id),
        )
        await self._conn.commit()

    async def add_credential(
        self,
        source_id: int,
        label: str,
        secret_name: str,
        secret_value: str,
        make_active: bool = True,
    ) -> int:
        encrypted = self._secret_box.encrypt(secret_value)
        masked = mask_secret(secret_value)

        if make_active:
            await self._conn.execute(
                """
                UPDATE source_credentials
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE source_id = ?
                """,
                (source_id,),
            )

        cursor = await self._conn.execute(
            """
            INSERT INTO source_credentials(source_id, label, secret_name, encrypted_value, masked_value, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source_id, label, secret_name, encrypted, masked, 1 if make_active else 0),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def list_credentials(self, source_id: int) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT id, source_id, label, secret_name, masked_value, is_active, created_at, updated_at
            FROM source_credentials
            WHERE source_id = ?
            ORDER BY is_active DESC, id DESC
            """,
            (source_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def set_active_credential(self, source_id: int, credential_id: int) -> None:
        await self._conn.execute(
            """
            UPDATE source_credentials
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE source_id = ?
            """,
            (source_id,),
        )
        await self._conn.execute(
            """
            UPDATE source_credentials
            SET is_active = 1, updated_at = CURRENT_TIMESTAMP
            WHERE source_id = ? AND id = ?
            """,
            (source_id, credential_id),
        )
        await self._conn.commit()

    async def get_active_credential(self, source_id: int) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            """
            SELECT * FROM source_credentials
            WHERE source_id = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["secret_value"] = self._secret_box.decrypt(data["encrypted_value"])
        return data

    async def create_draft(
        self,
        draft_id: str,
        user_id: int,
        origin_url: str,
        canonical_url: str,
        url_hash: str,
        title: str,
        body: str,
        language: str,
        source_media_url: str | None,
        source_media_type: str | None,
        generated_image_url: str | None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO drafts(
                id, user_id, origin_url, canonical_url, url_hash, title, body, language,
                source_media_url, source_media_type, generated_image_url, status, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)
            """,
            (
                draft_id,
                user_id,
                origin_url,
                canonical_url,
                url_hash,
                title,
                body,
                language,
                source_media_url,
                source_media_type,
                generated_image_url,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        await self._conn.commit()

    async def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        cursor = await self._conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["meta"] = json.loads(data.get("meta_json") or "{}")
        return data

    async def set_draft_status(self, draft_id: str, status: str) -> None:
        await self._conn.execute(
            """
            UPDATE drafts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, draft_id),
        )
        await self._conn.commit()

    async def is_processed_hash(self, url_hash: str) -> bool:
        cursor = await self._conn.execute("SELECT 1 FROM processed_links WHERE url_hash = ? LIMIT 1", (url_hash,))
        row = await cursor.fetchone()
        return bool(row)

    async def add_processed_link(
        self,
        original_url: str,
        canonical_url: str,
        url_hash: str,
        draft_id: str,
        published_message_ids: list[int],
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO processed_links(original_url, canonical_url, url_hash, draft_id, published_message_ids)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                original_url,
                canonical_url,
                url_hash,
                draft_id,
                json.dumps(published_message_ids),
            ),
        )
        await self._conn.commit()

    async def list_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT * FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["details"] = json.loads(data.get("details_json") or "{}")
            result.append(data)
        return result

    @staticmethod
    def _source_row_to_dict(row: Any) -> dict[str, Any]:
        data = dict(row)
        data["domains"] = json.loads(data.get("domains_json") or "[]")
        data["settings"] = json.loads(data.get("settings_json") or "{}")
        return data
