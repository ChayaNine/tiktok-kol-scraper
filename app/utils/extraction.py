"""
Extraction and normalization utilities.

Apify actor GdWCkxBtKWOsKjdch returns items that can be either:
  - A video item  (has authorMeta, videoMeta, etc.)
  - A profile/user item (has userInfo / profileData etc.)

We normalise everything here so the rest of the app does not care
about the raw Apify shape.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict


# ── Hashtag normalisation ────────────────────────────────────────────────────

def normalize_hashtag(tag: str) -> str:
    """Remove leading #, strip spaces, lowercase."""
    return tag.lstrip("#").strip().lower()


def extract_hashtags_from_text(text: Optional[str]) -> list[str]:
    """Pull all #hashtags from any text string."""
    if not text:
        return []
    raw = re.findall(r"#([\w\u0E00-\u0E7F]+)", text)
    return [normalize_hashtag(t) for t in raw if t]


# ── Author / profile extraction ──────────────────────────────────────────────

def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_author_from_item(item: dict) -> Optional[dict]:
    """
    Given one Apify item, return a normalised author dict or None.

    Apify can return:
      item["authorMeta"]  — nested author object inside a video item
      item["author"]      — flat author object
      item["userInfo"]    — profile scrape item
    """
    author = (
        item.get("authorMeta")
        or item.get("author")
        or item.get("userInfo", {}).get("user")
        or item.get("userInfo")
        or None
    )

    if author is None:
        return None

    # Flatten: different Apify versions use different keys
    username = (
        author.get("uniqueId")
        or author.get("name")
        or author.get("username")
        or author.get("id")            # fallback — not ideal but better than None
    )

    if not username:
        return None

    stats = (
        author.get("stats")
        or author.get("authorStats")
        or item.get("authorStats")
        or {}
    )

    followers = _safe_int(
        author.get("fans")
        or author.get("followers")
        or author.get("followerCount")
        or stats.get("followerCount")
        or stats.get("fans")
    )

    following = _safe_int(
        author.get("following")
        or author.get("followingCount")
        or stats.get("followingCount")
    )

    total_likes = _safe_int(
        author.get("heart")
        or author.get("heartCount")
        or author.get("digg")
        or stats.get("heartCount")
        or stats.get("diggCount")
    )

    return {
        "username":     str(username).lower().strip(),
        "display_name": author.get("nickName") or author.get("nickname") or author.get("name"),
        "followers":    followers,
        "following":    following,
        "total_likes":  total_likes,
        "bio":          author.get("signature") or author.get("bio"),
        "profile_url":  f"https://www.tiktok.com/@{username}",
    }


# ── Video/post metrics ───────────────────────────────────────────────────────

def extract_video_metrics(item: dict) -> Optional[dict]:
    """
    Extract per-video stats from an Apify video item.
    Returns None if the item does not look like a video.
    """
    # Check it has some video-like stats
    stats = (
        item.get("statsV2")
        or item.get("stats")
        or {}
    )

    plays    = _safe_int(stats.get("playCount")    or stats.get("plays"))
    likes    = _safe_int(stats.get("diggCount")    or stats.get("likes"))
    comments = _safe_int(stats.get("commentCount") or stats.get("comments"))
    shares   = _safe_int(stats.get("shareCount")   or stats.get("shares"))

    if plays is None and likes is None:
        return None

    # Create time — Apify usually gives a Unix timestamp
    created_ts = item.get("createTime") or item.get("createTimeISO")
    created_dt = None
    if created_ts:
        try:
            created_dt = datetime.fromtimestamp(int(created_ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            try:
                created_dt = datetime.fromisoformat(str(created_ts))
            except Exception:
                pass

    description = item.get("desc") or item.get("text") or item.get("description") or ""

    return {
        "plays":       plays,
        "likes":       likes,
        "comments":    comments,
        "shares":      shares,
        "created_at":  created_dt,
        "description": description,
    }


# ── Aggregate metrics from multiple videos ───────────────────────────────────

def calculate_creator_metrics(video_metrics: list[dict]) -> dict:
    """
    Given a list of extract_video_metrics() results for one creator,
    return aggregated numbers.
    """
    if not video_metrics:
        return {}

    plays    = [v["plays"]    for v in video_metrics if v.get("plays")    is not None]
    likes    = [v["likes"]    for v in video_metrics if v.get("likes")    is not None]
    comments = [v["comments"] for v in video_metrics if v.get("comments") is not None]

    avg_view    = sum(plays)    / len(plays)    if plays    else None
    avg_like    = sum(likes)    / len(likes)    if likes    else None
    avg_comment = sum(comments) / len(comments) if comments else None

    # Engagement rate = (avg_like + avg_comment) / avg_view  × 100
    engagement_rate = None
    if avg_like is not None and avg_comment is not None and avg_view:
        engagement_rate = round((avg_like + avg_comment) / avg_view * 100, 2)

    # Videos per month — needs at least 2 videos with timestamps
    videos_per_month = None
    dates = sorted(
        [v["created_at"] for v in video_metrics if v.get("created_at") is not None]
    )
    if len(dates) >= 2:
        span_days = (dates[-1] - dates[0]).days
        if span_days > 0:
            videos_per_month = round(len(dates) / (span_days / 30), 2)

    return {
        "avg_view":        round(avg_view, 2)    if avg_view    is not None else None,
        "avg_like":        round(avg_like, 2)    if avg_like    is not None else None,
        "avg_comment":     round(avg_comment, 2) if avg_comment is not None else None,
        "engagement_rate": engagement_rate,
        "videos_per_month": videos_per_month,
    }


# ── Hashtag discovery from a batch of items ─────────────────────────────────

def discover_hashtags_from_items(items: list[dict]) -> list[str]:
    """
    Walk every item, pull hashtags from descriptions, challenges, etc.
    Returns a deduplicated list of normalised hashtags.
    """
    found: set[str] = set()

    for item in items:
        # From challenges / hashtag objects on the video
        for challenge in item.get("challenges", []) or []:
            title = challenge.get("title") or challenge.get("name") or ""
            if title:
                found.add(normalize_hashtag(title))

        # From text/description
        desc = item.get("desc") or item.get("text") or item.get("description") or ""
        found.update(extract_hashtags_from_text(desc))

        # From textExtra (TikTok API sometimes includes this)
        for extra in item.get("textExtra", []) or []:
            ht = extra.get("hashtagName") or extra.get("title") or ""
            if ht:
                found.add(normalize_hashtag(ht))

    # Remove empty strings
    return [h for h in found if h]


# ── Group items by author ────────────────────────────────────────────────────

def group_items_by_author(items: list[dict]) -> dict[str, list[dict]]:
    """
    Return { username: [item, item, ...] }
    Only includes items that have a recognisable author.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        author = extract_author_from_item(item)
        if author and author.get("username"):
            grouped[author["username"]].append(item)
    return dict(grouped)
