from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.handlers import build_router
from bot.middleware import OwnerOnlyMiddleware
from core.config import load_config
from core.default_sources import ensure_default_sources
from services.extractors import LinkExtractor
from services.pipeline import ContentPipeline
from services.publisher import ChannelPublisher
from services.source_manager import SourceManager
from storage.crypto import SecretBox
from storage.db import Database
from storage.repository import Repository


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()

    db = Database(str(config.db_path))
    await db.connect()
    repo = Repository(db=db, secret_box=SecretBox(config.encryption_key))
    await ensure_default_sources(repo)

    source_manager = SourceManager(repo=repo, timeout_seconds=config.request_timeout_seconds)
    extractor = LinkExtractor(timeout_seconds=config.request_timeout_seconds)
    publisher = ChannelPublisher(channel_id=config.channel_id)
    pipeline = ContentPipeline(repo=repo, source_manager=source_manager, extractor=extractor, publisher=publisher)

    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    dp.message.middleware(OwnerOnlyMiddleware(config.allowed_user_ids))
    dp.callback_query.middleware(OwnerOnlyMiddleware(config.allowed_user_ids))
    dp.include_router(build_router(repo=repo, pipeline=pipeline, source_manager=source_manager))

    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
