import re
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict


def normalize_hashtag(tag: str) -> str:
    return tag.lstrip("#").strip().lower()


def extract_hashtags_from_text(text: Optional[str]) -> list:
    if not text:
        return []
    raw = re.findall(r"#([\w\u0E00-\u0E7F]+)", text)
    return [normalize_hashtag(t) for t in raw if t]


def _safe_int(value) -> Optional[int]:
    try:
        v = int(value)
        return v
    except (TypeError, ValueError):
        return None


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_author_from_item(item: dict) -> Optional[dict]:
    """
    Raw JSON from this Apify actor has authorMeta with these fields:
      name, nickName, fans, following, heart, signature, profileUrl
    """
    author = item.get("authorMeta") or item.get("author") or {}

    if not author:
        return None

    username = (
        author.get("name")
        or author.get("uniqueId")
        or author.get("username")
    )

    if not username:
        return None

    # fans = followers in Apify's naming
    followers_raw = author.get("fans")
    followers = _safe_int(followers_raw) if followers_raw is not None else None

    following_raw = author.get("following")
    following = _safe_int(following_raw) if following_raw is not None else None

    heart_raw = author.get("heart")
    total_likes = _safe_int(heart_raw) if heart_raw is not None else None

    return {
        "username":     str(username).lower().strip(),
        "display_name": author.get("nickName") or author.get("nickname"),
        "followers":    followers,
        "following":    following,
        "total_likes":  total_likes,
        "bio":          author.get("signature") or author.get("bio"),
        "profile_url":  author.get("profileUrl") or f"https://www.tiktok.com/@{username}",
    }


def extract_video_metrics(item: dict) -> Optional[dict]:
    """
    In this Apify actor, video stats are at the TOP LEVEL of the item:
      diggCount, playCount, commentCount, shareCount
    NOT inside a nested stats object.
    """
    plays    = _safe_int(item.get("playCount"))
    likes    = _safe_int(item.get("diggCount"))
    comments = _safe_int(item.get("commentCount"))
    shares   = _safe_int(item.get("shareCount"))

    if plays is None and likes is None:
        return None

    created_ts = item.get("createTime")
    created_dt = None
    if created_ts:
        try:
            created_dt = datetime.fromtimestamp(int(created_ts), tz=timezone.utc)
        except Exception:
            pass

    description = item.get("text") or item.get("desc") or ""

    return {
        "plays":       plays,
        "likes":       likes,
        "comments":    comments,
        "shares":      shares,
        "created_at":  created_dt,
        "description": description,
    }


def calculate_creator_metrics(video_metrics: list) -> dict:
    if not video_metrics:
        return {}

    plays    = [v["plays"]    for v in video_metrics if v.get("plays")    is not None]
    likes    = [v["likes"]    for v in video_metrics if v.get("likes")    is not None]
    comments = [v["comments"] for v in video_metrics if v.get("comments") is not None]

    avg_view    = sum(plays)    / len(plays)    if plays    else None
    avg_like    = sum(likes)    / len(likes)    if likes    else None
    avg_comment = sum(comments) / len(comments) if comments else None

    engagement_rate = None
    if avg_like is not None and avg_comment is not None and avg_view:
        engagement_rate = round((avg_like + avg_comment) / avg_view * 100, 2)

    videos_per_month = None
    dates = sorted(
        [v["created_at"] for v in video_metrics if v.get("created_at") is not None]
    )
    if len(dates) >= 2:
        span_days = (dates[-1] - dates[0]).days
        if span_days > 0:
            videos_per_month = round(len(dates) / (span_days / 30), 2)

    return {
        "avg_view":         round(avg_view, 2)    if avg_view    is not None else None,
        "avg_like":         round(avg_like, 2)    if avg_like    is not None else None,
        "avg_comment":      round(avg_comment, 2) if avg_comment is not None else None,
        "engagement_rate":  engagement_rate,
        "videos_per_month": videos_per_month,
    }


def discover_hashtags_from_items(items: list) -> list:
    found = set()
    for item in items:
        for ht in item.get("hashtags", []) or []:
            name = ht.get("name") or ht.get("title") or ""
            if name:
                found.add(normalize_hashtag(name))
        desc = item.get("text") or item.get("desc") or ""
        found.update(extract_hashtags_from_text(desc))
        for extra in item.get("textExtra", []) or []:
            ht = extra.get("hashtagName") or extra.get("title") or ""
            if ht:
                found.add(normalize_hashtag(ht))
    return [h for h in found if h]


def group_items_by_author(items: list) -> dict:
    grouped = defaultdict(list)
    for item in items:
        author = extract_author_from_item(item)
        if author and author.get("username"):
            grouped[author["username"]].append(item)
    return dict(grouped)