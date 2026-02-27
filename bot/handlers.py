from __future__ import annotations

import json
import shlex
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import build_publish_keyboard
from bot.states import CredentialInputState
from services.pipeline import ContentPipeline
from services.source_manager import SourceManager
from services.utils import looks_like_url
from storage.repository import Repository


def build_router(repo: Repository, pipeline: ContentPipeline, source_manager: SourceManager) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(_help_text())

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(_help_text())

    @router.message(Command("sources"))
    async def cmd_sources(message: Message) -> None:
        sources = await repo.list_sources()
        if not sources:
            await message.answer("Источники пока не добавлены.")
            return
        lines = ["Источники:"]
        for src in sources:
            status = "ON" if src["enabled"] else "OFF"
            selected = " [selected]" if src["is_selected"] else ""
            domains = ", ".join(src.get("domains") or []) or "-"
            lines.append(
                f"#{src['id']} {src['name']} ({src['source_type']}) {status}{selected}\n"
                f"priority={src['priority']} domains={domains}\n"
                f"base_url={src.get('base_url') or '-'}"
            )
        await message.answer("\n\n".join(lines))

    @router.message(Command("source_add"))
    async def cmd_source_add(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer(
                "Использование:\n"
                "/source_add <name> <type:api|llm|image> <base_url|-> <priority:int> <domains_csv|-> [settings_json]\n\n"
                "Пример:\n"
                "/source_add openai_llm llm https://api.openai.com 10 - '{\"model\":\"gpt-4o-mini\"}'"
            )
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
            if len(parts) >= 6:
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
            await message.answer(f"Источник создан: id={source_id}")
        except Exception as exc:
            await message.answer(f"Ошибка добавления источника: {exc}")

    @router.message(Command("source_select"))
    async def cmd_source_select(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /source_select <source_id>")
            return
        try:
            source_id = int(command.args.strip())
            source = await repo.get_source(source_id)
            if not source:
                await message.answer("Источник не найден")
                return
            await repo.set_source_selected(source_id)
            await repo.log_action(message.from_user.id, "source_select", {"source_id": source_id})
            await message.answer(f"Выбран источник #{source_id}")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("source_enable"))
    async def cmd_source_enable(message: Message, command: CommandObject) -> None:
        await _set_source_enabled(repo, message, command, True)

    @router.message(Command("source_disable"))
    async def cmd_source_disable(message: Message, command: CommandObject) -> None:
        await _set_source_enabled(repo, message, command, False)

    @router.message(Command("source_priority"))
    async def cmd_source_priority(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /source_priority <source_id> <priority>")
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            priority = int(parts[1])
            await repo.update_source_priority(source_id, priority)
            await repo.log_action(
                message.from_user.id,
                "source_priority",
                {"source_id": source_id, "priority": priority},
            )
            await message.answer("Приоритет обновлен")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("source_domains"))
    async def cmd_source_domains(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /source_domains <source_id> <domain1,domain2|->")
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            domains = [] if parts[1] == "-" else [d.strip().lower() for d in parts[1].split(",") if d.strip()]
            await repo.update_source_domains(source_id, domains)
            await repo.log_action(
                message.from_user.id,
                "source_domains",
                {"source_id": source_id, "domains": domains},
            )
            await message.answer("Доменные правила обновлены")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("source_update"))
    async def cmd_source_update(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer(
                "Использование: /source_update <source_id> <base_url|-> [settings_json|->]\n"
                "Пример: /source_update 1 https://api.openai.com '{\"model\":\"gpt-4o-mini\"}'"
            )
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
            await message.answer("Конфиг источника обновлен")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("source_test"))
    async def cmd_source_test(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /source_test <source_id>")
            return
        try:
            source_id = int(command.args.strip())
            ok, details = await source_manager.test_source(source_id)
            await repo.log_action(
                message.from_user.id,
                "source_test",
                {"source_id": source_id, "ok": ok, "details": details},
            )
            await message.answer(f"Тест источника #{source_id}: {'OK' if ok else 'FAIL'} ({details})")
        except Exception as exc:
            await message.answer(f"Ошибка теста: {exc}")

    @router.message(Command("cred_add"))
    async def cmd_cred_add(message: Message, command: CommandObject, state: FSMContext) -> None:
        if not command.args:
            await message.answer("Использование: /cred_add <source_id> <label> <secret_name>")
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            label = parts[1]
            secret_name = parts[2]
        except Exception:
            await message.answer("Неверный формат. Пример: /cred_add 1 primary Authorization")
            return

        prompt = await message.answer(
            "Отправьте значение секрета следующим сообщением.\n"
            "После сохранения я удалю это сообщение из чата."
        )
        await state.set_state(CredentialInputState.waiting_value)
        await state.update_data(
            source_id=source_id,
            label=label,
            secret_name=secret_name,
            prompt_chat_id=prompt.chat.id,
            prompt_message_id=prompt.message_id,
        )

    @router.message(CredentialInputState.waiting_value, F.text)
    async def handle_credential_value(message: Message, state: FSMContext) -> None:
        state_data = await state.get_data()
        await state.clear()

        source_id = int(state_data["source_id"])
        label = state_data["label"]
        secret_name = state_data["secret_name"]
        secret_value = message.text.strip()
        if not secret_value:
            await message.answer("Пустое значение секрета не сохранено.")
            return

        try:
            cred_id = await repo.add_credential(
                source_id=source_id,
                label=label,
                secret_name=secret_name,
                secret_value=secret_value,
                make_active=True,
            )
            await repo.log_action(
                message.from_user.id,
                "cred_add",
                {"source_id": source_id, "credential_id": cred_id, "label": label, "secret_name": secret_name},
            )
            await message.answer(f"Ключ добавлен и активирован (id={cred_id})")
        finally:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.bot.delete_message(
                    chat_id=state_data["prompt_chat_id"],
                    message_id=state_data["prompt_message_id"],
                )
            except Exception:
                pass

    @router.message(Command("cred_list"))
    async def cmd_cred_list(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /cred_list <source_id>")
            return
        try:
            source_id = int(command.args.strip())
            credentials = await repo.list_credentials(source_id)
            if not credentials:
                await message.answer("Ключи для источника не найдены")
                return
            lines = [f"Ключи источника #{source_id}:"]
            for cred in credentials:
                active = " [active]" if cred["is_active"] else ""
                lines.append(
                    f"#{cred['id']} {cred['label']} ({cred['secret_name']}) "
                    f"{cred['masked_value']}{active}"
                )
            await message.answer("\n".join(lines))
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("cred_use"))
    async def cmd_cred_use(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Использование: /cred_use <source_id> <credential_id>")
            return
        try:
            parts = shlex.split(command.args)
            source_id = int(parts[0])
            credential_id = int(parts[1])
            await repo.set_active_credential(source_id, credential_id)
            await repo.log_action(
                message.from_user.id,
                "cred_use",
                {"source_id": source_id, "credential_id": credential_id},
            )
            await message.answer("Активный ключ переключен")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @router.message(Command("logs"))
    async def cmd_logs(message: Message, command: CommandObject) -> None:
        limit = 20
        if command.args:
            try:
                limit = max(1, min(int(command.args.strip()), 100))
            except Exception:
                limit = 20
        logs = await repo.list_logs(limit=limit)
        if not logs:
            await message.answer("Лог пока пуст")
            return
        lines = ["Последние действия:"]
        for entry in logs:
            details = json.dumps(entry["details"], ensure_ascii=False)
            lines.append(
                f"{entry['id']}. {entry['created_at']} user={entry['actor_user_id']} "
                f"action={entry['action']} details={details}"
            )
        await message.answer("\n".join(lines))

    @router.message(StateFilter(None), F.text)
    async def handle_possible_url(message: Message) -> None:
        text = (message.text or "").strip()
        if not looks_like_url(text):
            return

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
        except Exception as exc:
            await message.answer(f"Ошибка обработки ссылки: {exc}")

    @router.callback_query(F.data.startswith("pub|"))
    async def handle_publish_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if not callback.data:
            return
        _, draft_id, action = callback.data.split("|", 2)

        if action == "cancel":
            await pipeline.cancel_draft(draft_id)
            await repo.log_action(callback.from_user.id, "draft_cancel", {"draft_id": draft_id})
            await callback.message.answer("Черновик отменен")
            return

        ok, result_text = await pipeline.publish_draft(callback.bot, draft_id=draft_id, image_choice=action)
        await repo.log_action(
            callback.from_user.id,
            "draft_publish",
            {"draft_id": draft_id, "choice": action, "ok": ok, "details": result_text},
        )
        await callback.message.answer(result_text)

    return router


def _help_text() -> str:
    return (
        "Я бот-контент менеджер.\n\n"
        "Как использовать:\n"
        "1) Отправьте ссылку (сайт или Telegram-пост)\n"
        "2) Я подготовлю черновик\n"
        "3) Выберите публикацию: исходное медиа / сгенерированное / без медиа\n\n"
        "Команды источников:\n"
        "/sources - список источников\n"
        "/source_add <name> <type> <base_url|-> <priority> <domains_csv|-> [settings_json]\n"
        "/source_update <source_id> <base_url|-> [settings_json|->]\n"
        "/source_select <id>\n"
        "/source_enable <id>\n"
        "/source_disable <id>\n"
        "/source_priority <id> <priority>\n"
        "/source_domains <id> <domain1,domain2|->\n"
        "/source_test <id>\n\n"
        "Команды ключей:\n"
        "/cred_add <source_id> <label> <secret_name>\n"
        "/cred_list <source_id>\n"
        "/cred_use <source_id> <credential_id>\n\n"
        "Журнал:\n"
        "/logs [limit]"
    )


async def _set_source_enabled(repo: Repository, message: Message, command: CommandObject, enabled: bool) -> None:
    if not command.args:
        await message.answer(f"Использование: /{'source_enable' if enabled else 'source_disable'} <source_id>")
        return
    try:
        source_id = int(command.args.strip())
        source = await repo.get_source(source_id)
        if not source:
            await message.answer("Источник не найден")
            return
        await repo.set_source_enabled(source_id, enabled=enabled)
        await repo.log_action(
            message.from_user.id,
            "source_enable" if enabled else "source_disable",
            {"source_id": source_id},
        )
        await message.answer(f"Источник #{source_id} {'включен' if enabled else 'выключен'}")
    except Exception as exc:
        await message.answer(f"Ошибка: {exc}")
