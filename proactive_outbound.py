"""Topic-seed selection for scheduled / proactive outbound turns."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from memory_layers import LAYER_ARCHIVE, LAYER_DREAM, LAYER_SOURCE_RECORD, infer_bucket_layer
from memory_metadata import domain_parent, normalize_domain_key
from original_quotes import is_original_quote_bucket
from query_understanding import query_intent_terms

RELATIONSHIP_PARENTS = frozenset({"relationship", "intimacy", "inner"})
RELATIONSHIP_TAGS = frozenset(
    {
        "relationship_event",
        "relationship_anchor",
        "relationship_signal",
        "intimacy",
        "inner",
        "情感",
        "感情",
        "关系",
        "亲密",
        "内心",
    }
)
WEATHER_TAGS = frozenset({"relationship_weather", "daily_impression", "weekly_impression"})
DEFAULT_OUTBOUND_LIMIT = 2
DEFAULT_OUTBOUND_COOLDOWN_HOURS = 12.0


def is_proactive_outbound_query(query: str) -> bool:
    text = str(query or "")
    if not text.strip():
        return False
    required = query_intent_terms("proactive_outbound.required_markers")
    if len(required) >= 2 and all(marker in text for marker in required):
        return True
    any_markers = query_intent_terms("proactive_outbound.any_markers")
    support_markers = query_intent_terms("proactive_outbound.support_markers")
    if not any_markers or not support_markers:
        return False
    return any(marker in text for marker in any_markers) and any(
        marker in text for marker in support_markers
    )


def _metadata(bucket: dict[str, Any]) -> dict[str, Any]:
    meta = bucket.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _tag_set(bucket: dict[str, Any]) -> set[str]:
    tags = _metadata(bucket).get("tags") or []
    if not isinstance(tags, list):
        return set()
    return {str(tag).strip().lower() for tag in tags if str(tag or "").strip()}


def _raw_domains(bucket: dict[str, Any]) -> list[Any]:
    meta = _metadata(bucket)
    domain = meta.get("domain")
    if isinstance(domain, list):
        return list(domain)
    if domain:
        return [domain]
    return []


def bucket_parent_domains(bucket: dict[str, Any]) -> set[str]:
    parents: set[str] = set()
    for item in _raw_domains(bucket):
        key = domain_parent(normalize_domain_key(item))
        if key:
            parents.add(key)
    path = str(_metadata(bucket).get("path") or bucket.get("path") or "")
    for part in path.replace("\\", "/").split("/"):
        key = domain_parent(normalize_domain_key(part))
        if key and key != "general":
            parents.add(key)
    return parents


def bucket_is_relationship_inner(bucket: dict[str, Any]) -> bool:
    if bucket_parent_domains(bucket) & RELATIONSHIP_PARENTS:
        return True
    tags = _tag_set(bucket)
    return bool(tags & {item.lower() for item in RELATIONSHIP_TAGS})


def bucket_is_pinned_core(bucket: dict[str, Any]) -> bool:
    meta = _metadata(bucket)
    if meta.get("pinned") or meta.get("protected") or meta.get("anchor"):
        return True
    return str(meta.get("type") or "").strip().lower() == "permanent"


def bucket_is_eligible_outbound_topic(bucket: dict[str, Any]) -> bool:
    if not isinstance(bucket, dict) or not str(bucket.get("id") or "").strip():
        return False
    layer = infer_bucket_layer(bucket)
    if layer in {LAYER_ARCHIVE, LAYER_SOURCE_RECORD, LAYER_DREAM}:
        return False
    meta = _metadata(bucket)
    if str(meta.get("type") or "").strip().lower() == "archived":
        return False
    if is_original_quote_bucket(bucket):
        return False
    tags = _tag_set(bucket)
    if tags & WEATHER_TAGS:
        return False
    if meta.get("resolved") and not bucket_is_pinned_core(bucket):
        return False
    return bucket_is_pinned_core(bucket) or bucket_is_relationship_inner(bucket)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None


def _importance(bucket: dict[str, Any]) -> int:
    try:
        return int(_metadata(bucket).get("importance", 5) or 5)
    except (TypeError, ValueError):
        return 5


def score_outbound_topic_bucket(
    bucket: dict[str, Any],
    *,
    now: datetime,
    last_injected_at: datetime | None,
    cooldown_hours: float = DEFAULT_OUTBOUND_COOLDOWN_HOURS,
) -> tuple[float, bool]:
    """Return (score, on_cooldown). Higher score is better."""
    relationship = bucket_is_relationship_inner(bucket)
    pinned = bucket_is_pinned_core(bucket)
    score = 0.0
    if relationship and pinned:
        score += 90
    elif relationship:
        score += 55
    if pinned:
        score += 35
    if not _metadata(bucket).get("resolved"):
        score += 8
    score += min(10, max(0, _importance(bucket)))
    last_active = _parse_time(_metadata(bucket).get("last_active") or _metadata(bucket).get("created"))
    if last_active:
        try:
            if last_active.tzinfo and now.tzinfo is None:
                last_active = last_active.replace(tzinfo=None)
            elif now.tzinfo and last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=now.tzinfo)
            age_hours = max(0.0, (now - last_active).total_seconds() / 3600)
        except TypeError:
            age_hours = 0.0
        if age_hours >= 72:
            score += 8
        elif age_hours >= 24:
            score += 4
        elif age_hours < 2:
            score -= 12
    on_cooldown = False
    if last_injected_at and cooldown_hours > 0:
        try:
            injected = last_injected_at
            if injected.tzinfo and now.tzinfo is None:
                injected = injected.replace(tzinfo=None)
            elif now.tzinfo and injected.tzinfo is None:
                injected = injected.replace(tzinfo=now.tzinfo)
            on_cooldown = (now - injected) < timedelta(hours=cooldown_hours)
        except TypeError:
            on_cooldown = False
    if on_cooldown:
        score -= 40
    return score, on_cooldown


def select_outbound_topic_buckets(
    buckets: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    last_injected_at: Callable[[str], datetime | None] | None = None,
    limit: int = DEFAULT_OUTBOUND_LIMIT,
    cooldown_hours: float = DEFAULT_OUTBOUND_COOLDOWN_HOURS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = now or datetime.now()
    limit = max(1, min(int(limit or DEFAULT_OUTBOUND_LIMIT), 3))
    scored: list[tuple[float, bool, dict[str, Any]]] = []
    for bucket in buckets or []:
        if not bucket_is_eligible_outbound_topic(bucket):
            continue
        bucket_id = str(bucket.get("id") or "")
        injected_at = last_injected_at(bucket_id) if last_injected_at else None
        score, cooled = score_outbound_topic_bucket(
            bucket,
            now=now,
            last_injected_at=injected_at,
            cooldown_hours=cooldown_hours,
        )
        scored.append((score, cooled, bucket))
    scored.sort(key=lambda item: item[0], reverse=True)
    fresh = [item for item in scored if not item[1]]
    pool = fresh or scored
    picked: list[dict[str, Any]] = []
    picked_ids: set[str] = set()

    def take(predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
        for _score, _cooled, bucket in pool:
            bucket_id = str(bucket.get("id") or "")
            if bucket_id in picked_ids:
                continue
            if predicate(bucket):
                picked_ids.add(bucket_id)
                picked.append(bucket)
                return bucket
        return None

    take(lambda bucket: bucket_is_relationship_inner(bucket) and bucket_is_pinned_core(bucket))
    if len(picked) < limit:
        take(bucket_is_relationship_inner)
    if len(picked) < limit:
        take(bucket_is_pinned_core)
    if len(picked) < limit:
        take(lambda _bucket: True)

    debug = {
        "candidate_count": len(scored),
        "fresh_count": len(fresh),
        "selected_ids": [str(bucket.get("id") or "") for bucket in picked],
        "selected_kinds": [
            {
                "id": str(bucket.get("id") or ""),
                "relationship": bucket_is_relationship_inner(bucket),
                "pinned": bucket_is_pinned_core(bucket),
            }
            for bucket in picked
        ],
        "used_cooldown_fallback": not bool(fresh) and bool(scored),
    }
    return picked[:limit], debug
