from __future__ import annotations

import uuid
from urllib.parse import urlparse

from aiogram import Bot

from services.extractors import LinkExtractor
from services.models import DraftResult, ExtractedContent
from services.publisher import ChannelPublisher
from services.source_manager import SourceManager
from services.utils import normalize_url, url_hash
from storage.repository import Repository


class ContentPipeline:
    def __init__(
        self,
        repo: Repository,
        source_manager: SourceManager,
        extractor: LinkExtractor,
        publisher: ChannelPublisher,
    ) -> None:
        self._repo = repo
        self._source_manager = source_manager
        self._extractor = extractor
        self._publisher = publisher

    async def process_url(self, user_id: int, incoming_url: str) -> DraftResult:
        canonical_url = normalize_url(incoming_url)
        hash_value = url_hash(canonical_url)

        if await self._repo.is_processed_hash(hash_value):
            return DraftResult(
                draft_id="",
                duplicate=True,
                duplicate_reason="Эта ссылка уже публиковалась ранее.",
            )

        domain = urlparse(canonical_url).netloc.lower()
        link_type = self._extractor.detect_link_type(canonical_url)
        extracted = await self._source_manager.fetch_content_from_api(canonical_url, domain, link_type)
        if extracted is None:
            extracted = await self._extractor.extract(canonical_url)

        adapted_text = await self._source_manager.rewrite_to_russian(
            title=extracted.title,
            text=extracted.text,
            source_language=extracted.language,
        )
        if not adapted_text:
            adapted_text = self._local_fallback_rewrite(extracted)

        image_prompt = self._build_image_prompt(extracted.title, adapted_text)
        generated_image_url = await self._source_manager.generate_image(image_prompt)

        draft_id = uuid.uuid4().hex
        await self._repo.create_draft(
            draft_id=draft_id,
            user_id=user_id,
            origin_url=incoming_url,
            canonical_url=canonical_url,
            url_hash=hash_value,
            title=extracted.title,
            body=adapted_text,
            language=extracted.language,
            source_media_url=extracted.source_media_url,
            source_media_type=extracted.source_media_type,
            generated_image_url=generated_image_url,
            meta={"link_type": extracted.link_type},
        )

        return DraftResult(
            draft_id=draft_id,
            duplicate=False,
            title=extracted.title,
            body=adapted_text,
            source_media_url=extracted.source_media_url,
            generated_image_url=generated_image_url,
        )

    async def publish_draft(self, bot: Bot, draft_id: str, image_choice: str) -> tuple[bool, str]:
        draft = await self._repo.get_draft(draft_id)
        if not draft:
            return False, "Черновик не найден"
        if draft["status"] in {"published", "cancelled"}:
            return False, f"Черновик уже в статусе {draft['status']}"

        media_url = None
        media_type = None
        if image_choice == "source" and draft.get("source_media_url"):
            media_url = draft.get("source_media_url")
            media_type = draft.get("source_media_type") or "photo"
        elif image_choice == "generated" and draft.get("generated_image_url"):
            media_url = draft.get("generated_image_url")
            media_type = "photo"

        try:
            message_ids = await self._publisher.publish(bot=bot, text=draft["body"], media_url=media_url, media_type=media_type)
        except Exception as exc:
            return False, f"Ошибка публикации: {exc}"

        try:
            await self._repo.add_processed_link(
                original_url=draft["origin_url"],
                canonical_url=draft["canonical_url"],
                url_hash=draft["url_hash"],
                draft_id=draft["id"],
                published_message_ids=message_ids,
            )
            await self._repo.set_draft_status(draft_id, "published")
        except Exception as exc:
            return False, f"Публикация ушла в канал, но не удалось зафиксировать в БД: {exc}"

        return True, "Опубликовано в канал"

    async def cancel_draft(self, draft_id: str) -> None:
        await self._repo.set_draft_status(draft_id, "cancelled")

    @staticmethod
    def _build_image_prompt(title: str, text: str) -> str:
        body = text[:800]
        return (
            "Создай реалистичную и выразительную иллюстрацию для Telegram-поста.\n"
            f"Тема: {title}\n"
            f"Контекст: {body}\n"
            "Без текста на изображении."
        )

    @staticmethod
    def _local_fallback_rewrite(extracted: ExtractedContent) -> str:
        text = extracted.text.strip()
        compact = text[:2400]
        return (
            f"{extracted.title}\n\n"
            f"{compact}\n\n"
            "Источник обработан в fallback-режиме. Для полноценного перевода/рерайта подключите LLM-источник."
        )
