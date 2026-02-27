from __future__ import annotations

import json
import shlex
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    MAIN_MENU_CANCEL,
    MAIN_MENU_CREDENTIALS,
    MAIN_MENU_GUIDE,
    MAIN_MENU_LOGS,
    MAIN_MENU_NEW_POST,
    MAIN_MENU_SOURCES,
    build_cancel_keyboard,
    build_credentials_actions_keyboard,
    build_credentials_sources_keyboard,
    build_instruction_keyboard,
    build_main_menu_keyboard,
    build_publish_keyboard,
    build_source_actions_keyboard,
    build_source_type_keyboard,
    build_sources_keyboard,
)
from bot.states import CredentialWizardState, SourceWizardState
from services.pipeline import ContentPipeline
from services.source_manager import SourceManager
from services.utils import looks_like_url
from storage.repository import Repository


def build_router(repo: Repository, pipeline: ContentPipeline, source_manager: SourceManager) -> Router:
    router = Router()

    async def show_main_menu(message: Message, text: str | None = None) -> None:
        await message.answer(text or _welcome_text(), reply_markup=build_main_menu_keyboard())

    async def show_sources_panel(message: Message) -> None:
        sources = await repo.list_sources()
        if not sources:
            await message.answer(
                "Источники пока не добавлены. Нажмите 'Добавить источник'.",
                reply_markup=build_sources_keyboard([]),
            )
            return
        await message.answer(_format_sources_list(sources), reply_markup=build_sources_keyboard(sources))

    async def show_credentials_sources_panel(message: Message) -> None:
        sources = await repo.list_sources()
        if not sources:
            await message.answer("Сначала добавьте источник в разделе 'Источники'.")
            return
        await message.answer(
            "Выберите источник, чтобы посмотреть или добавить ключ:",
            reply_markup=build_credentials_sources_keyboard(sources),
        )

    async def show_source_card(message: Message, source_id: int) -> None:
        source = await repo.get_source(source_id)
        if not source:
            await message.answer("Источник не найден")
            return
        await message.answer(
            _format_source_card(source),
            reply_markup=build_source_actions_keyboard(
                source_id=source_id,
                enabled=bool(source["enabled"]),
                is_selected=bool(source["is_selected"]),
            ),
        )

    async def show_credentials_for_source(message: Message, source_id: int) -> None:
        source = await repo.get_source(source_id)
        if not source:
            await message.answer("Источник не найден")
            return
        credentials = await repo.list_credentials(source_id)
        await message.answer(
            _format_credentials_block(source, credentials),
            reply_markup=build_credentials_actions_keyboard(source_id, credentials),
        )

    async def start_source_wizard(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(SourceWizardState.waiting_name)
        await message.answer(
            "Мастер источника: введите название нового источника.",
            reply_markup=build_cancel_keyboard(),
        )

    async def start_credential_wizard(message: Message, state: FSMContext, source_id: int) -> None:
        source = await repo.get_source(source_id)
        if not source:
            await message.answer("Источник не найден")
            return
        await state.clear()
        await state.set_state(CredentialWizardState.waiting_label)
        await state.update_data(source_id=source_id)
        await message.answer(
            f"Источник #{source_id} ({source['name']}). Введите label ключа (например primary).",
            reply_markup=build_cancel_keyboard(),
        )

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await show_main_menu(message)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await show_main_menu(message, _help_text())

    @router.message(Command("menu"))
    async def cmd_menu(message: Message, state: FSMContext) -> None:
        await state.clear()
        await show_main_menu(message)

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await show_main_menu(message, "Действие отменено.")

    @router.message(Command("sources"))
    async def cmd_sources(message: Message) -> None:
        await show_sources_panel(message)

    @router.message(Command("logs"))
    async def cmd_logs(message: Message, command: CommandObject) -> None:
        limit = 20
        if command.args:
            try:
                limit = max(1, min(int(command.args.strip()), 100))
            except ValueError:
                limit = 20
        logs = await repo.list_logs(limit=limit)
        if not logs:
            await message.answer("Лог пока пуст", reply_markup=build_main_menu_keyboard())
            return
        lines = ["Последние действия:"]
        for entry in logs:
            details = json.dumps(entry["details"], ensure_ascii=False)
            lines.append(
                f"{entry['id']}. {entry['created_at']} user={entry['actor_user_id']} "
                f"action={entry['action']} details={details}"
            )
        await message.answer("\n".join(lines), reply_markup=build_main_menu_keyboard())

    @router.message(Command("source_add"))
    async def cmd_source_add(message: Message, command: CommandObject, state: FSMContext) -> None:
        if not command.args:
            await start_source_wizard(message, state)
            return

        try:
            parts = shlex.split(command.args)
            if len(parts) < 5:
                raise ValueError("Недостаточно аргументов")
            name = parts[0]
            source_type = parts[1].lower()
            base_url = None if parts[2] == "-" else parts[2]
            priority = int(parts[3])
            domains = [] if parts[4] == "-" else [d.strip().lower() for d in parts[4].split(",") if d.strip()]
            settings: dict[str, Any] = {}
            if len(parts) >= 6 and parts[5] != "-":
                settings = json.loads(parts[5])
            if source_type not in {"api", "llm", "image"}:
                raise ValueError("type должен быть api|llm|image")

            source_id = await repo.add_source(
                name=name,
                source_type=source_type,
                base_url=base_url,
                priority=priority,
                domains=domains,
                settings=settings,
            )
            await repo.log_action(message.from_user.id, "source_add", {"source_id": source_id, "name": name})
            await message.answer(f"Источник создан: #{source_id}", reply_markup=build_main_menu_keyboard())
        except Exception as exc:
            await message.answer(f"Ошибка добавления источника: {exc}")

    @router.message(Command("source_update"))
    async def cmd_source_update(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /source_update <source_id> <base_url|-> [settings_json|->]")
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            base_url = None if parts[1] == "-" else parts[1]
            settings = None
            if len(parts) >= 3 and parts[2] != "-":
                settings = json.loads(parts[2])
            await repo.update_source_config(source_id, base_url=base_url, settings=settings)
            await repo.log_action(
                message.from_user.id,
                "source_update",
                {"source_id": source_id, "base_url": base_url, "settings_keys": list((settings or {}).keys())},
            )
            await message.answer("Конфиг источника обновлен", reply_markup=build_main_menu_keyboard())
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("cred_add"))
    async def cmd_cred_add(message: Message, command: CommandObject, state: FSMContext) -> None:
        if not command.args:
            await show_credentials_sources_panel(message)
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            label = parts[1]
            secret_name = parts[2]
            await state.clear()
            await state.set_state(CredentialWizardState.waiting_value)
            await state.update_data(source_id=source_id, label=label, secret_name=secret_name)
            await message.answer(
                "Отправьте значение ключа следующим сообщением. Сообщение будет удалено после сохранения.",
                reply_markup=build_cancel_keyboard(),
            )
        except Exception:
            await message.answer("Неверный формат. Пример: /cred_add 1 primary Authorization")

    @router.message(F.text == MAIN_MENU_NEW_POST)
    async def menu_new_post(message: Message) -> None:
        await message.answer(
            "Отправьте ссылку на сайт или Telegram-пост. Я подготовлю черновик и покажу кнопки публикации.",
            reply_markup=build_main_menu_keyboard(),
        )

    @router.message(F.text == MAIN_MENU_SOURCES)
    async def menu_sources(message: Message) -> None:
        await show_sources_panel(message)

    @router.message(F.text == MAIN_MENU_CREDENTIALS)
    async def menu_credentials(message: Message) -> None:
        await show_credentials_sources_panel(message)

    @router.message(F.text == MAIN_MENU_GUIDE)
    async def menu_guide(message: Message) -> None:
        await message.answer(_guide_intro_text(), reply_markup=build_instruction_keyboard())

    @router.message(F.text == MAIN_MENU_LOGS)
    async def menu_logs(message: Message) -> None:
        logs = await repo.list_logs(limit=20)
        if not logs:
            await message.answer("Лог пока пуст", reply_markup=build_main_menu_keyboard())
            return
        lines = ["Последние действия:"]
        for entry in logs:
            details = json.dumps(entry["details"], ensure_ascii=False)
            lines.append(
                f"{entry['id']}. {entry['created_at']} user={entry['actor_user_id']} "
                f"action={entry['action']} details={details}"
            )
        await message.answer("\n".join(lines), reply_markup=build_main_menu_keyboard())

    @router.message(F.text == MAIN_MENU_CANCEL)
    async def menu_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await show_main_menu(message, "Действие отменено.")

    @router.callback_query(F.data.startswith("guide|"))
    async def cb_guide(callback: CallbackQuery) -> None:
        await callback.answer()
        if not callback.data:
            return
        section = callback.data.split("|", 1)[1]
        if section == "menu":
            await callback.message.answer(_welcome_text(), reply_markup=build_main_menu_keyboard())
            return
        await callback.message.answer(_guide_section_text(section), reply_markup=build_instruction_keyboard())

    @router.callback_query(F.data.startswith("src|"))
    async def cb_sources(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if not callback.data:
            return
        parts = callback.data.split("|")
        action = parts[1]

        if action == "list":
            await show_sources_panel(callback.message)
            return

        if action == "menu":
            await show_main_menu(callback.message)
            return

        if action == "add":
            await start_source_wizard(callback.message, state)
            return

        if len(parts) < 3:
            await callback.message.answer("Некорректное действие")
            return

        source_id = int(parts[2])

        if action == "open":
            await show_source_card(callback.message, source_id)
            return

        source = await repo.get_source(source_id)
        if not source:
            await callback.message.answer("Источник не найден")
            return

        if action == "toggle":
            new_state = not bool(source["enabled"])
            await repo.set_source_enabled(source_id, new_state)
            await repo.log_action(
                callback.from_user.id,
                "source_enable" if new_state else "source_disable",
                {"source_id": source_id},
            )
            await show_source_card(callback.message, source_id)
            return

        if action == "select":
            await repo.set_source_selected(source_id)
            await repo.log_action(callback.from_user.id, "source_select", {"source_id": source_id})
            await show_source_card(callback.message, source_id)
            return

        if action == "test":
            ok, details = await source_manager.test_source(source_id)
            await repo.log_action(
                callback.from_user.id,
                "source_test",
                {"source_id": source_id, "ok": ok, "details": details},
            )
            await callback.message.answer(f"Тест источника #{source_id}: {'OK' if ok else 'FAIL'} ({details})")
            return

        if action == "keys":
            await show_credentials_for_source(callback.message, source_id)
            return

    @router.callback_query(F.data.startswith("credsrc|"))
    async def cb_cred_sources(callback: CallbackQuery) -> None:
        await callback.answer()
        if not callback.data:
            return
        parts = callback.data.split("|")
        action = parts[1]

        if action == "list":
            await show_credentials_sources_panel(callback.message)
            return

        if action == "menu":
            await show_main_menu(callback.message)
            return

        if action == "open" and len(parts) >= 3:
            source_id = int(parts[2])
            await show_credentials_for_source(callback.message, source_id)
            return

    @router.callback_query(F.data.startswith("cred|"))
    async def cb_credentials(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if not callback.data:
            return
        parts = callback.data.split("|")
        action = parts[1]

        if action == "add" and len(parts) >= 3:
            source_id = int(parts[2])
            await start_credential_wizard(callback.message, state, source_id)
            return

        if action == "use" and len(parts) >= 4:
            source_id = int(parts[2])
            credential_id = int(parts[3])
            await repo.set_active_credential(source_id, credential_id)
            await repo.log_action(
                callback.from_user.id,
                "cred_use",
                {"source_id": source_id, "credential_id": credential_id},
            )
            await show_credentials_for_source(callback.message, source_id)

    @router.message(SourceWizardState.waiting_name, F.text)
    async def source_wizard_name(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Создание источника отменено.")
            return
        await state.update_data(name=text)
        await state.set_state(SourceWizardState.waiting_type)
        await message.answer("Выберите тип источника:", reply_markup=build_source_type_keyboard())

    @router.callback_query(StateFilter(SourceWizardState.waiting_type), F.data.startswith("src_type|"))
    async def source_wizard_type(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if not callback.data:
            return
        source_type = callback.data.split("|", 1)[1]
        if source_type == "cancel":
            await state.clear()
            await callback.message.answer("Создание источника отменено.", reply_markup=build_main_menu_keyboard())
            return
        await state.update_data(source_type=source_type)
        await state.set_state(SourceWizardState.waiting_base_url)
        await callback.message.answer("Введите base_url источника или '-' если не нужен.")

    @router.message(SourceWizardState.waiting_base_url, F.text)
    async def source_wizard_base_url(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Создание источника отменено.")
            return
        await state.update_data(base_url=None if text == "-" else text)
        await state.set_state(SourceWizardState.waiting_priority)
        await message.answer("Введите приоритет (целое число, например 10).")

    @router.message(SourceWizardState.waiting_priority, F.text)
    async def source_wizard_priority(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Создание источника отменено.")
            return
        try:
            priority = int(text)
        except ValueError:
            await message.answer("Приоритет должен быть числом. Попробуйте еще раз.")
            return
        await state.update_data(priority=priority)
        await state.set_state(SourceWizardState.waiting_domains)
        await message.answer("Введите домены через запятую или '-' для всех доменов.")

    @router.message(SourceWizardState.waiting_domains, F.text)
    async def source_wizard_domains(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Создание источника отменено.")
            return
        domains = [] if text == "-" else [d.strip().lower() for d in text.split(",") if d.strip()]
        await state.update_data(domains=domains)
        await state.set_state(SourceWizardState.waiting_settings)
        await message.answer(
            "Введите settings_json или '-' для пустого объекта. "
            "Пример: {\"model\":\"gpt-4o-mini\",\"chat_endpoint\":\"/v1/chat/completions\"}"
        )

    @router.message(SourceWizardState.waiting_settings, F.text)
    async def source_wizard_settings(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Создание источника отменено.")
            return

        settings: dict[str, Any] = {}
        if text != "-":
            try:
                settings = json.loads(text)
                if not isinstance(settings, dict):
                    raise ValueError("settings_json должен быть JSON-объектом")
            except Exception as exc:
                await message.answer(f"Некорректный JSON: {exc}. Попробуйте снова.")
                return

        data = await state.get_data()
        await state.clear()

        source_id = await repo.add_source(
            name=data["name"],
            source_type=data["source_type"],
            base_url=data["base_url"],
            priority=data["priority"],
            domains=data["domains"],
            settings=settings,
        )
        await repo.log_action(
            message.from_user.id,
            "source_add",
            {"source_id": source_id, "name": data["name"], "via": "wizard"},
        )

        await message.answer(f"Источник создан: #{source_id}", reply_markup=build_main_menu_keyboard())
        await show_source_card(message, source_id)

    @router.message(CredentialWizardState.waiting_label, F.text)
    async def cred_wizard_label(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Добавление ключа отменено.")
            return
        await state.update_data(label=text)
        await state.set_state(CredentialWizardState.waiting_secret_name)
        await message.answer("Введите название поля секрета (обычно Authorization или X-API-Key).")

    @router.message(CredentialWizardState.waiting_secret_name, F.text)
    async def cred_wizard_secret_name(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if _is_cancel(text):
            await state.clear()
            await show_main_menu(message, "Добавление ключа отменено.")
            return
        await state.update_data(secret_name=text)
        await state.set_state(CredentialWizardState.waiting_value)
        await message.answer("Отправьте значение ключа. После сохранения сообщение будет удалено.")

    @router.message(CredentialWizardState.waiting_value, F.text)
    async def cred_wizard_value(message: Message, state: FSMContext) -> None:
        secret_value = (message.text or "").strip()
        if _is_cancel(secret_value):
            await state.clear()
            await show_main_menu(message, "Добавление ключа отменено.")
            return
        if not secret_value:
            await message.answer("Пустое значение не сохранено. Попробуйте снова.")
            return

        data = await state.get_data()
        await state.clear()

        cred_id = await repo.add_credential(
            source_id=int(data["source_id"]),
            label=str(data["label"]),
            secret_name=str(data["secret_name"]),
            secret_value=secret_value,
            make_active=True,
        )
        await repo.log_action(
            message.from_user.id,
            "cred_add",
            {
                "source_id": int(data["source_id"]),
                "credential_id": cred_id,
                "label": str(data["label"]),
                "secret_name": str(data["secret_name"]),
                "via": "wizard",
            },
        )

        try:
            await message.delete()
        except Exception:
            pass

        await message.answer(
            f"Ключ добавлен и активирован (id={cred_id}).",
            reply_markup=build_main_menu_keyboard(),
        )
        await show_credentials_for_source(message, int(data["source_id"]))

    @router.message(StateFilter(None), F.text)
    async def handle_text(message: Message) -> None:
        text = (message.text or "").strip()

        if looks_like_url(text):
            try:
                draft = await pipeline.process_url(user_id=message.from_user.id, incoming_url=text)
                if draft.duplicate:
                    await message.answer(draft.duplicate_reason or "Ссылка уже публиковалась")
                    return

                preview = draft.body or ""
                if len(preview) > 1200:
                    preview = preview[:1200] + "..."
                await message.answer(
                    "Черновик подготовлен:\n\n"
                    f"{preview}\n\n"
                    "Выберите вариант публикации:",
                    reply_markup=build_publish_keyboard(
                        draft_id=draft.draft_id,
                        has_source=bool(draft.source_media_url),
                        has_generated=bool(draft.generated_image_url),
                    ),
                )
                await repo.log_action(
                    message.from_user.id,
                    "draft_created",
                    {"draft_id": draft.draft_id, "url": text},
                )
                return
            except Exception as exc:
                await message.answer(f"Ошибка обработки ссылки: {exc}")
                return

        await message.answer(
            "Не понял сообщение. Нажмите кнопку раздела или отправьте ссылку.",
            reply_markup=build_main_menu_keyboard(),
        )

    @router.callback_query(F.data.startswith("pub|"))
    async def handle_publish_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if not callback.data:
            return
        _, draft_id, action = callback.data.split("|", 2)

        if action == "cancel":
            await pipeline.cancel_draft(draft_id)
            await repo.log_action(callback.from_user.id, "draft_cancel", {"draft_id": draft_id})
            await callback.message.answer("Черновик отменен", reply_markup=build_main_menu_keyboard())
            return

        ok, result_text = await pipeline.publish_draft(callback.bot, draft_id=draft_id, image_choice=action)
        await repo.log_action(
            callback.from_user.id,
            "draft_publish",
            {"draft_id": draft_id, "choice": action, "ok": ok, "details": result_text},
        )
        await callback.message.answer(result_text, reply_markup=build_main_menu_keyboard())

    return router


def _is_cancel(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered in {"отмена", "cancel", "/cancel"}


def _welcome_text() -> str:
    return (
        "Контент-менеджер готов к работе.\n\n"
        "Главный сценарий:\n"
        "1. Нажмите 'Новый пост' и отправьте ссылку.\n"
        "2. Получите черновик.\n"
        "3. Выберите вариант публикации.\n\n"
        "Для администрирования используйте кнопки 'Источники' и 'API-ключи'."
    )


def _help_text() -> str:
    return (
        "Работайте через кнопки главного меню.\n\n"
        "Разделы:\n"
        f"- {MAIN_MENU_NEW_POST}: обработка и публикация ссылок\n"
        f"- {MAIN_MENU_SOURCES}: просмотр/включение/проверка источников\n"
        f"- {MAIN_MENU_CREDENTIALS}: добавление и переключение ключей\n"
        f"- {MAIN_MENU_GUIDE}: инструкции по разделам\n"
        f"- {MAIN_MENU_LOGS}: последние действия\n\n"
        "Команды доступны как резерв: /sources, /source_add, /source_update, /cred_add, /logs"
    )


def _guide_intro_text() -> str:
    return "Инструкция по разделам. Выберите тему ниже:"


def _guide_section_text(section: str) -> str:
    if section == "publish":
        return (
            "Публикация поста:\n"
            "1. Нажмите 'Новый пост'.\n"
            "2. Отправьте URL сайта или Telegram-поста.\n"
            "3. Проверьте черновик и нажмите кнопку публикации.\n"
            "4. Если текст длинный, бот отправит медиа и текст отдельными сообщениями."
        )
    if section == "source_add":
        return (
            "Добавление источника:\n"
            "1. Нажмите 'Источники'.\n"
            "2. Нажмите 'Добавить источник'.\n"
            "3. Пройдите мастер: имя -> тип -> base_url -> приоритет -> домены -> settings_json.\n"
            "4. После сохранения откроется карточка источника."
        )
    if section == "key_add":
        return (
            "Добавление API-ключа:\n"
            "1. Нажмите 'API-ключи'.\n"
            "2. Выберите источник.\n"
            "3. Нажмите 'Добавить ключ' и пройдите мастер.\n"
            "4. Ключ сохраняется зашифрованно, в интерфейсе отображается маска."
        )
    if section == "source_manage":
        return (
            "Управление источниками:\n"
            "1. В разделе 'Источники' откройте карточку нужного источника.\n"
            "2. Кнопки в карточке: выбрать активным, включить/выключить, тест подключения, ключи.\n"
            "3. Для расширенной правки параметров можно использовать /source_update."
        )
    return "Раздел не найден."


def _format_sources_list(sources: list[dict[str, Any]]) -> str:
    lines = ["Источники:"]
    for src in sources:
        status = "ON" if src["enabled"] else "OFF"
        selected = " [selected]" if src["is_selected"] else ""
        domains = ", ".join(src.get("domains") or []) or "-"
        lines.append(
            f"#{src['id']} {src['name']} ({src['source_type']}) {status}{selected}\n"
            f"priority={src['priority']} domains={domains}"
        )
    return "\n\n".join(lines)


def _format_source_card(source: dict[str, Any]) -> str:
    domains = ", ".join(source.get("domains") or []) or "-"
    settings = json.dumps(source.get("settings") or {}, ensure_ascii=False)
    status = "включен" if source["enabled"] else "выключен"
    selected = "да" if source["is_selected"] else "нет"
    return (
        f"Источник #{source['id']}\n"
        f"name={source['name']}\n"
        f"type={source['source_type']}\n"
        f"status={status}\n"
        f"selected={selected}\n"
        f"priority={source['priority']}\n"
        f"domains={domains}\n"
        f"base_url={source.get('base_url') or '-'}\n"
        f"settings={settings}"
    )


def _format_credentials_block(source: dict[str, Any], credentials: list[dict[str, Any]]) -> str:
    lines = [f"Ключи источника #{source['id']} ({source['name']}):"]
    if not credentials:
        lines.append("Ключей пока нет.")
        return "\n".join(lines)

    for cred in credentials:
        active = " [active]" if cred["is_active"] else ""
        lines.append(
            f"#{cred['id']} {cred['label']} ({cred['secret_name']}) {cred['masked_value']}{active}"
        )
    return "\n".join(lines)
