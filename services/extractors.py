from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from langdetect import LangDetectException, detect

from services.models import ExtractedContent


class LinkExtractor:
    def __init__(self, timeout_seconds: int = 20) -> None:
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def detect_link_type(url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in {"t.me", "telegram.me"}:
            return "telegram_post"
        return "website"

    async def extract(self, url: str) -> ExtractedContent:
        link_type = self.detect_link_type(url)
        if link_type == "telegram_post":
            return await self._extract_telegram_post(url)
        return await self._extract_website(url)

    async def _extract_website(self, url: str) -> ExtractedContent:
        html = await self._download(url)
        soup = BeautifulSoup(html, "html.parser")

        extracted_text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)
        if not extracted_text:
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            extracted_text = "\n\n".join([p for p in paragraphs if p][:25])
        if not extracted_text:
            raise ValueError("Не удалось извлечь текст со страницы")

        title = ""
        title_meta = soup.find("meta", attrs={"property": "og:title"})
        if title_meta and title_meta.get("content"):
            title = title_meta["content"].strip()
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            title = "Без заголовка"

        media_url = None
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            media_url = og_image["content"].strip()
        if not media_url:
            tw_image = soup.find("meta", attrs={"name": "twitter:image"})
            if tw_image and tw_image.get("content"):
                media_url = tw_image["content"].strip()

        language = _safe_detect_language(extracted_text)
        return ExtractedContent(
            url=url,
            link_type="website",
            title=title,
            text=extracted_text.strip(),
            language=language,
            source_media_url=media_url,
            source_media_type="photo" if media_url else None,
        )

    async def _extract_telegram_post(self, url: str) -> ExtractedContent:
        canonical_url = _to_telegram_s_url(url)
        html = await self._download(canonical_url)
        soup = BeautifulSoup(html, "html.parser")

        text_block = soup.select_one("div.tgme_widget_message_text")
        text = text_block.get_text("\n", strip=True) if text_block else ""
        if not text:
            raise ValueError("Не удалось извлечь текст Telegram-поста (возможно, пост недоступен публично)")

        title = "Пост из Telegram"
        author_block = soup.select_one("a.tgme_widget_message_owner_name")
        if author_block:
            title = author_block.get_text(" ", strip=True)

        media_url = None
        media_type = None

        photo_wrap = soup.select_one("a.tgme_widget_message_photo_wrap")
        if photo_wrap and photo_wrap.get("style"):
            media_url = _extract_url_from_style(photo_wrap["style"])
            if media_url:
                media_type = "photo"

        if not media_url:
            video_tag = soup.select_one("video")
            if video_tag and video_tag.get("src"):
                media_url = video_tag.get("src")
                media_type = "video"
            elif video_tag:
                source_tag = video_tag.select_one("source")
                if source_tag and source_tag.get("src"):
                    media_url = source_tag.get("src")
                    media_type = "video"

        language = _safe_detect_language(text)
        return ExtractedContent(
            url=canonical_url,
            link_type="telegram_post",
            title=title,
            text=text,
            language=language,
            source_media_url=media_url,
            source_media_type=media_type,
        )

    async def _download(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


def _extract_url_from_style(style: str) -> str | None:
    match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
    if not match:
        return None
    return match.group(1)


def _to_telegram_s_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("Некорректная ссылка Telegram")
    if parts[0] == "s":
        return url
    if len(parts) < 2:
        raise ValueError("Ожидалась ссылка на конкретный пост Telegram: https://t.me/<channel>/<post_id>")
    channel = parts[0]
    message_id = parts[1]
    return f"https://t.me/s/{channel}/{message_id}"


def _safe_detect_language(text: str) -> str:
    sample = text[:2000]
    try:
        return detect(sample)
    except LangDetectException:
        return "unknown"
