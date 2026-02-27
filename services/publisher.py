from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from services.utils import split_text_for_telegram


class ChannelPublisher:
    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id

    async def publish(
        self,
        bot: Bot,
        text: str,
        media_url: str | None = None,
        media_type: str | None = None,
    ) -> list[int]:
        message_ids: list[int] = []
        if media_url:
            posted = await self._send_with_media(bot, text=text, media_url=media_url, media_type=media_type or "photo")
            message_ids.extend(posted)
            return message_ids

        for chunk in split_text_for_telegram(text, chunk_size=4096):
            msg = await bot.send_message(chat_id=self.channel_id, text=chunk)
            message_ids.append(msg.message_id)
        return message_ids

    async def _send_with_media(self, bot: Bot, text: str, media_url: str, media_type: str) -> list[int]:
        message_ids: list[int] = []
        caption_chunks = split_text_for_telegram(text, chunk_size=1024)
        first_caption = caption_chunks[0] if caption_chunks else ""

        media_message: Message
        if media_type == "video":
            media_message = await bot.send_video(chat_id=self.channel_id, video=media_url, caption=first_caption)
        else:
            media_message = await bot.send_photo(chat_id=self.channel_id, photo=media_url, caption=first_caption)
        message_ids.append(media_message.message_id)

        tail_chunks = caption_chunks[1:]
        for chunk in tail_chunks:
            msg = await bot.send_message(chat_id=self.channel_id, text=chunk)
            message_ids.append(msg.message_id)
        return message_ids
