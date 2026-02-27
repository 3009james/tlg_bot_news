from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlparse, urlunparse, urlencode


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "yclid",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in TRACKING_PARAMS]
    query_pairs.sort(key=lambda x: (x[0], x[1]))
    normalized = parsed._replace(
        scheme=(parsed.scheme or "https").lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(query_pairs, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def looks_like_url(text: str) -> bool:
    text = (text or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def split_text_for_telegram(text: str, chunk_size: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        border = remaining.rfind("\n", 0, chunk_size)
        if border < 200:
            border = remaining.rfind(" ", 0, chunk_size)
        if border < 100:
            border = chunk_size
        chunks.append(remaining[:border].strip())
        remaining = remaining[border:].strip()
    return [chunk for chunk in chunks if chunk]
