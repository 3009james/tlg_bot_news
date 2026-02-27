from __future__ import annotations

from typing import Any

from storage.repository import Repository


DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "name": "groq_llm",
        "source_type": "llm",
        "base_url": "https://api.groq.com",
        "priority": 20,
        "domains": [],
        "settings": {
            "chat_endpoint": "/openai/v1/chat/completions",
            "model": "llama-3.1-8b-instant",
            "temperature": 0.6,
        },
    }
]


async def ensure_default_sources(repo: Repository) -> None:
    existing = await repo.list_sources()
    existing_names = {source["name"] for source in existing}

    for source in DEFAULT_SOURCES:
        if source["name"] in existing_names:
            continue
        source_id = await repo.add_source(
            name=source["name"],
            source_type=source["source_type"],
            base_url=source["base_url"],
            priority=int(source["priority"]),
            domains=source["domains"],
            settings=source["settings"],
        )
        await repo.log_action(
            actor_user_id=0,
            action="source_auto_seed",
            details={"source_id": source_id, "name": source["name"]},
        )
