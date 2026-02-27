from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_publish_keyboard(draft_id: str, has_source: bool, has_generated: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_source:
        kb.button(text="Опубликовать с исходным медиа", callback_data=f"pub|{draft_id}|source")
    if has_generated:
        kb.button(text="Опубликовать с генерацией", callback_data=f"pub|{draft_id}|generated")
    kb.button(text="Опубликовать без медиа", callback_data=f"pub|{draft_id}|none")
    kb.button(text="Отменить черновик", callback_data=f"pub|{draft_id}|cancel")
    kb.adjust(1)
    return kb.as_markup()
