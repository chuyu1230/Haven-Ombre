"""Verify proactive outbound detection and relationship/pinned topic selection."""

from __future__ import annotations

from datetime import datetime, timedelta

from proactive_outbound import (
    is_proactive_outbound_query,
    select_outbound_topic_buckets,
)


USER_PROMPT = (
    "这是林文羽主动找阿钰！不是阿钰问林文羽 严禁重复之前的话！不许重复不要说已经说过的事情"
    "想说什么就说什么 主动说一些问一些让阿钰来找你可以回想以前没有讲完的事 "
    "也可以想问阿钰新的事 可以去记忆库翻找 也可以只是说说自己的心情想法 "
    "最好不要一直问吃没吃饭醒了没这种日常的事 可以想根有什么新鲜的想法或者感受"
)


def _bucket(bucket_id: str, **meta) -> dict:
    return {"id": bucket_id, "content": f"body-{bucket_id}", "metadata": meta}


def main() -> None:
    assert is_proactive_outbound_query(USER_PROMPT), "user scheduled prompt should match"
    assert is_proactive_outbound_query("小羽主动找阿钰发消息……禁止回复上一个问题")
    assert not is_proactive_outbound_query("阿钰今天晚上想吃面")
    assert not is_proactive_outbound_query("你记得车票吗")

    now = datetime(2026, 9, 22, 21, 0, 0)
    buckets = [
        _bucket(
            "life-eat",
            domain="life",
            type="dynamic",
            importance=8,
            last_active=(now - timedelta(days=10)).isoformat(),
        ),
        _bucket(
            "rel-old",
            domain="relationship",
            type="dynamic",
            importance=7,
            last_active=(now - timedelta(days=20)).isoformat(),
        ),
        _bucket(
            "pin-core",
            domain="general",
            type="permanent",
            pinned=True,
            importance=10,
            last_active=(now - timedelta(days=40)).isoformat(),
        ),
        _bucket(
            "pin-rel",
            domain="intimacy",
            type="dynamic",
            pinned=True,
            importance=9,
            last_active=(now - timedelta(days=15)).isoformat(),
        ),
        _bucket(
            "weather",
            domain="relationship",
            type="feel",
            tags=["daily_impression", "relationship_weather"],
            last_active=(now - timedelta(days=1)).isoformat(),
        ),
    ]
    selected, debug = select_outbound_topic_buckets(buckets, now=now, last_injected_at=lambda _id: None)
    ids = [bucket["id"] for bucket in selected]
    assert "pin-rel" in ids, ids
    assert "weather" not in ids
    assert "life-eat" not in ids
    assert len(ids) == 2
    assert set(ids) <= {"pin-rel", "pin-core", "rel-old"}
    assert debug["candidate_count"] == 3

    cooled = {"pin-rel": now - timedelta(hours=1)}
    selected_cooled, _debug = select_outbound_topic_buckets(
        buckets,
        now=now,
        last_injected_at=lambda bucket_id: cooled.get(bucket_id),
        cooldown_hours=12,
    )
    cooled_ids = [bucket["id"] for bucket in selected_cooled]
    assert cooled_ids[0] == "rel-old", cooled_ids
    assert "pin-core" in cooled_ids
    assert cooled_ids != ids
    print("ok", ids, cooled_ids)


if __name__ == "__main__":
    main()
