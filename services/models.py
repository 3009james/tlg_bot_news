from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExtractedContent:
    url: str
    link_type: str
    title: str
    text: str
    language: str
    source_media_url: str | None = None
    source_media_type: str | None = None


@dataclass(slots=True)
class DraftResult:
    draft_id: str
    duplicate: bool
    duplicate_reason: str | None = None
    title: str | None = None
    body: str | None = None
    source_media_url: str | None = None
    generated_image_url: str | None = None
