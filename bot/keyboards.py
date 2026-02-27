from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


MAIN_MENU_NEW_POST = "Новый пост"
MAIN_MENU_SOURCES = "Источники"
MAIN_MENU_CREDENTIALS = "API-ключи"
MAIN_MENU_GUIDE = "Инструкция"
MAIN_MENU_LOGS = "Логи"
MAIN_MENU_CANCEL = "Отмена"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MAIN_MENU_NEW_POST), KeyboardButton(text=MAIN_MENU_SOURCES)],
            [KeyboardButton(text=MAIN_MENU_CREDENTIALS), KeyboardButton(text=MAIN_MENU_GUIDE)],
            [KeyboardButton(text=MAIN_MENU_LOGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Вставьте ссылку или выберите действие",
    )


def build_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MAIN_MENU_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder="Нажмите Отмена, чтобы выйти из мастера",
    )


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


def build_instruction_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Как публиковать", callback_data="guide|publish")
    kb.button(text="Как добавить источник", callback_data="guide|source_add")
    kb.button(text="Как добавить API-ключ", callback_data="guide|key_add")
    kb.button(text="Как управлять источниками", callback_data="guide|source_manage")
    kb.button(text="Вернуться в меню", callback_data="guide|menu")
    kb.adjust(1)
    return kb.as_markup()


def build_sources_keyboard(sources: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for source in sources:
        status = "ON" if source["enabled"] else "OFF"
        kb.button(text=f"#{source['id']} {source['name']} [{status}]", callback_data=f"src|open|{source['id']}")
    kb.button(text="Добавить источник", callback_data="src|add")
    kb.button(text="Обновить список", callback_data="src|list")
    kb.button(text="В меню", callback_data="src|menu")
    kb.adjust(1)
    return kb.as_markup()


def build_source_actions_keyboard(source_id: int, enabled: bool, is_selected: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_selected:
        kb.button(text="Источник уже выбран", callback_data=f"src|open|{source_id}")
    else:
        kb.button(text="Выбрать активным", callback_data=f"src|select|{source_id}")
    toggle_text = "Выключить" if enabled else "Включить"
    kb.button(text=toggle_text, callback_data=f"src|toggle|{source_id}")
    kb.button(text="Проверить подключение", callback_data=f"src|test|{source_id}")
    kb.button(text="Ключи источника", callback_data=f"src|keys|{source_id}")
    kb.button(text="Назад к списку", callback_data="src|list")
    kb.button(text="В меню", callback_data="src|menu")
    kb.adjust(1)
    return kb.as_markup()


def build_source_type_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="API", callback_data="src_type|api")
    kb.button(text="LLM", callback_data="src_type|llm")
    kb.button(text="Image", callback_data="src_type|image")
    kb.button(text="Отмена", callback_data="src_type|cancel")
    kb.adjust(2)
    return kb.as_markup()


def build_credentials_sources_keyboard(sources: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for source in sources:
        kb.button(text=f"#{source['id']} {source['name']}", callback_data=f"credsrc|open|{source['id']}")
    kb.button(text="В меню", callback_data="credsrc|menu")
    kb.adjust(1)
    return kb.as_markup()


def build_credentials_actions_keyboard(source_id: int, credentials: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить ключ", callback_data=f"cred|add|{source_id}")
    for cred in credentials:
        active = " (active)" if cred["is_active"] else ""
        kb.button(text=f"#{cred['id']} {cred['label']}{active}", callback_data=f"cred|use|{source_id}|{cred['id']}")
    kb.button(text="Назад к источникам", callback_data="credsrc|list")
    kb.button(text="В меню", callback_data="credsrc|menu")
    kb.adjust(1)
    return kb.as_markup()
