"""Dedicated original-line memories. Partial quotes only; Gateway recalls them verbatim."""

from __future__ import annotations

import re
from typing import Any

ORIGINAL_QUOTE_KIND = "original_quote"
ORIGINAL_QUOTE_TAG = "original_quote"
ORIGINAL_QUOTE_SOURCE = "original_quote"
_ORIGINAL_HEADING_RE = re.compile(r"(?im)^\s*#{1,6}\s*original\b")


def format_original_quote_content(
    user_line: str,
    assistant_line: str,
    *,
    user_name: str = "阿钰",
    ai_name: str = "小羽",
    note: str = "",
) -> str:
    user_text = " ".join(str(user_line or "").split())
    assistant_text = " ".join(str(assistant_line or "").split())
    parts = [
        "### original",
        f"{user_name}：{user_text}",
        f"{ai_name}：{assistant_text}",
    ]
    cleaned_note = " ".join(str(note or "").split())
    if cleaned_note:
        parts.extend(["", "### moment", cleaned_note])
    return "\n".join(parts).strip()


def looks_like_original_quote_text(*parts: str) -> bool:
    blob = "\n".join(str(part or "") for part in parts)
    if "原话" in blob or ORIGINAL_QUOTE_TAG in blob.lower():
        return True
    return bool(_ORIGINAL_HEADING_RE.search(blob))


def is_original_quote_bucket(bucket: dict[str, Any] | None) -> bool:
    if not isinstance(bucket, dict):
        return False
    meta = bucket.get("metadata") if isinstance(bucket.get("metadata"), dict) else {}
    kind = str(meta.get("kind") or "").strip().lower()
    source = str(meta.get("source") or "").strip().lower()
    tags = {
        str(tag or "").strip().lower()
        for tag in (meta.get("tags") or [])
        if str(tag or "").strip()
    }
    name = str(meta.get("name") or bucket.get("name") or "")
    content = str(bucket.get("content") or "")
    return (
        kind == ORIGINAL_QUOTE_KIND
        or source == ORIGINAL_QUOTE_SOURCE
        or ORIGINAL_QUOTE_TAG in tags
        or "原话" in tags
        or looks_like_original_quote_text(name, content, " ".join(sorted(tags)))
    )
