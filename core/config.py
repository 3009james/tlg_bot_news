from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    bot_token: str
    channel_id: str
    allowed_user_ids: Set[int]
    db_path: Path
    encryption_key: str
    request_timeout_seconds: int


def _parse_user_ids(raw_value: str) -> Set[int]:
    result: Set[int] = set()
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        result.add(int(part))
    return result


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    channel_id = os.getenv("CHANNEL_ID", "").strip()
    user_ids_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
    db_path_raw = os.getenv("DB_PATH", "./data/bot.db").strip()
    encryption_key = os.getenv("ENCRYPTION_KEY", "").strip()
    timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "20").strip()

    missing = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if not channel_id:
        missing.append("CHANNEL_ID")
    if not user_ids_raw:
        missing.append("ALLOWED_USER_IDS")
    if not encryption_key:
        missing.append("ENCRYPTION_KEY")

    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Missing required env vars: {missing_text}")

    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=bot_token,
        channel_id=channel_id,
        allowed_user_ids=_parse_user_ids(user_ids_raw),
        db_path=db_path,
        encryption_key=encryption_key,
        request_timeout_seconds=int(timeout_raw),
    )
