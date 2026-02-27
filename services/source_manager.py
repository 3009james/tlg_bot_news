from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from services.models import ExtractedContent
from storage.repository import Repository


class SourceManager:
    def __init__(self, repo: Repository, timeout_seconds: int = 20) -> None:
        self._repo = repo
        self._timeout_seconds = timeout_seconds

    async def fetch_content_from_api(self, target_url: str, domain: str, link_type: str) -> ExtractedContent | None:
        for source in await self._get_candidates(domain, source_type="api", link_type=link_type):
            credential = await self._repo.get_active_credential(source["id"])
            try:
                content = await self._call_content_source(source, credential, target_url)
                if content and content.text.strip():
                    return content
            except Exception:
                continue
        return None

    async def rewrite_to_russian(self, title: str, text: str, source_language: str) -> str | None:
        for source in await self._get_candidates(domain="", source_type="llm"):
            credential = await self._repo.get_active_credential(source["id"])
            if not credential:
                continue
            try:
                rewritten = await self._call_llm_rewrite(source, credential["secret_value"], title, text, source_language)
                if rewritten:
                    return rewritten
            except Exception:
                continue
        return None

    async def generate_image(self, prompt: str) -> str | None:
        for source in await self._get_candidates(domain="", source_type="image"):
            credential = await self._repo.get_active_credential(source["id"])
            if not credential:
                continue
            try:
                generated = await self._call_image_generation(source, credential["secret_value"], prompt)
                if generated:
                    return generated
            except Exception:
                continue
        return None

    async def test_source(self, source_id: int) -> tuple[bool, str]:
        source = await self._repo.get_source(source_id)
        if not source:
            return False, "Источник не найден"
        if not source.get("base_url"):
            return False, "У источника нет base_url"

        credential = await self._repo.get_active_credential(source_id)
        headers = {}
        if credential:
            secret_name = credential.get("secret_name", "Authorization")
            secret_value = credential.get("secret_value", "")
            if secret_name.lower() == "authorization" and not secret_value.lower().startswith("bearer "):
                secret_value = f"Bearer {secret_value}"
            headers[secret_name] = secret_value

        async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True) as client:
            try:
                response = await client.get(source["base_url"], headers=headers)
                return (200 <= response.status_code < 400), f"HTTP {response.status_code}"
            except Exception as exc:
                return False, str(exc)

    async def _get_candidates(self, domain: str, source_type: str, link_type: str | None = None) -> list[dict[str, Any]]:
        sources = await self._repo.list_enabled_sources(source_type=source_type)
        if not domain:
            return [source for source in sources if _matches_link_type(source, link_type)]

        domain_specific: list[dict[str, Any]] = []
        generic: list[dict[str, Any]] = []
        for source in sources:
            if not _matches_link_type(source, link_type):
                continue
            domains = [d.lower() for d in source.get("domains", [])]
            if domains and domain.lower() in domains:
                domain_specific.append(source)
            elif not domains:
                generic.append(source)
        return domain_specific + generic

    async def _call_content_source(
        self,
        source: dict[str, Any],
        credential: dict[str, Any] | None,
        target_url: str,
    ) -> ExtractedContent | None:
        base_url = source.get("base_url")
        if not base_url:
            return None
        settings = source.get("settings", {})
        method = str(settings.get("method", "GET")).upper()
        url_param = str(settings.get("url_param", "url"))
        endpoint = str(settings.get("endpoint", ""))
        request_url = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/")) if endpoint else base_url

        headers: dict[str, str] = {}
        if credential:
            secret_name = credential.get("secret_name", "Authorization")
            secret_value = credential.get("secret_value", "")
            if secret_name.lower() == "authorization" and not secret_value.lower().startswith("bearer "):
                secret_value = f"Bearer {secret_value}"
            headers[secret_name] = secret_value
        for key, value in settings.get("extra_headers", {}).items():
            headers[str(key)] = str(value)

        payload: dict[str, Any] = dict(settings.get("extra_params", {}))
        payload[url_param] = target_url

        async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True) as client:
            if method == "POST":
                response = await client.post(request_url, json=payload, headers=headers)
            else:
                response = await client.get(request_url, params=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        title = str(data.get("title") or data.get("headline") or "Без заголовка")
        text = str(data.get("text") or data.get("content") or "")
        image_url = data.get("image_url") or data.get("image")
        media_url = data.get("media_url") or image_url
        media_type = data.get("media_type") or ("photo" if media_url else None)
        language = str(data.get("language") or "unknown")
        if not text.strip():
            return None

        return ExtractedContent(
            url=target_url,
            link_type="api",
            title=title,
            text=text,
            language=language,
            source_media_url=str(media_url) if media_url else None,
            source_media_type=str(media_type) if media_type else None,
        )

    async def _call_llm_rewrite(
        self,
        source: dict[str, Any],
        api_key: str,
        title: str,
        text: str,
        source_language: str,
    ) -> str | None:
        base_url = source.get("base_url")
        if not base_url:
            return None
        settings = source.get("settings", {})
        endpoint = str(settings.get("chat_endpoint", "/v1/chat/completions"))
        model = str(settings.get("model", "gpt-4o-mini"))
        temperature = float(settings.get("temperature", 0.7))
        request_url = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        system_prompt = (
            "Ты редактор русскоязычного Telegram-канала. "
            "Сделай новый пост на русском языке по исходному тексту. "
            "Не копируй дословно, сохраняй смысл, добавь понятную структуру: "
            "заголовок, 2-5 абзацев и короткий вывод/призыв к действию."
        )
        user_prompt = (
            f"Язык исходника: {source_language}\n"
            f"Заголовок: {title}\n\n"
            f"Исходный текст:\n{text}\n\n"
            "Верни только готовый текст поста на русском языке."
        )

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True) as client:
            response = await client.post(request_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        return str(content).strip() if content else None

    async def _call_image_generation(self, source: dict[str, Any], api_key: str, prompt: str) -> str | None:
        base_url = source.get("base_url")
        if not base_url:
            return None
        settings = source.get("settings", {})
        endpoint = str(settings.get("image_endpoint", "/v1/images/generations"))
        model = str(settings.get("model", "gpt-image-1"))
        size = str(settings.get("size", "1024x1024"))
        request_url = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=True) as client:
            response = await client.post(request_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items = data.get("data") or []
        if not items:
            return None
        image_url = items[0].get("url")
        return str(image_url).strip() if image_url else None


def _matches_link_type(source: dict[str, Any], link_type: str | None) -> bool:
    if not link_type:
        return True
    settings = source.get("settings", {})
    allowed = settings.get("link_types")
    if not allowed:
        return True
    if isinstance(allowed, str):
        allowed = [allowed]
    return link_type in {str(item).strip() for item in allowed}
