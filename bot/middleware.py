from __future__ import annotations

from typing import Any, Awaitable, Callable, Set

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class OwnerOnlyMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: Set[int]) -> None:
        super().__init__()
        self._allowed_user_ids = allowed_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user and from_user.id in self._allowed_user_ids:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("Доступ запрещен. Бот доступен только для владельца.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещен", show_alert=True)
        return None
