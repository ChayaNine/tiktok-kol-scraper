"""
Scraper service — main orchestration.

Flow for one hashtag:
  1. Check if already processed → skip if so.
  2. Mark as "processing".
  3. Call Apify.
  4. Save raw items to raw_data table.
  5. For each unique author: upsert Creator row with calculated metrics.
  6. Discover related hashtags → add to queue at depth+1.
  7. Mark hashtag as "done".
  8. Recurse if depth > 0 and there are pending hashtags.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Creator, RawData, Hashtag, HashtagStatus
from app.services.apify_service import run_tiktok_scrape
from app.utils.extraction import (
    normalize_hashtag,
    extract_author_from_item,
    extract_video_metrics,
    calculate_creator_metrics,
    discover_hashtags_from_items,
    group_items_by_author,
)
from app.utils.classification import (
    classify_influencer_size,
    classify_creator_type,
    classify_category,
)

logger = logging.getLogger(__name__)


# ── Hashtag queue helpers ────────────────────────────────────────────────────

def enqueue_hashtag(
    db: Session,
    hashtag: str,
    depth: int,
    source_hashtag: Optional[str] = None,
    discovered_from: Optional[str] = None,
) -> Hashtag:
    """
    Add a hashtag to the queue only if it doesn't already exist.
    Returns the existing or new Hashtag row.
    """
    tag = normalize_hashtag(hashtag)
    existing = db.query(Hashtag).filter(Hashtag.hashtag == tag).first()
    if existing:
        return existing  # already known — don't touch it

    ht = Hashtag(
        hashtag=tag,
        status=HashtagStatus.pending,
        depth=depth,
        source_hashtag=source_hashtag,
        discovered_from=discovered_from,
    )
    db.add(ht)
    db.commit()
    db.refresh(ht)
    return ht


def get_pending_hashtag(db: Session, max_depth: int) -> Optional[Hashtag]:
    """Return the next pending hashtag within allowed depth, or None."""
    return (
        db.query(Hashtag)
        .filter(
            Hashtag.status == HashtagStatus.pending,
            Hashtag.depth <= max_depth,
        )
        .order_by(Hashtag.depth, Hashtag.id)  # breadth-first
        .first()
    )


# ── Creator upsert ───────────────────────────────────────────────────────────

def upsert_creator(
    db: Session,
    author_data: dict,
    video_metrics_list: list[dict],
    source_hashtag: str,
    apify_run_id: str,
    raw_items: list[dict],
) -> Creator:
    """
    Insert or update a Creator row.
    Always saves raw items to raw_data table.
    """
    username = author_data["username"]

    # ── metrics ──
    metrics = calculate_creator_metrics(video_metrics_list)

    # ── classification ──
    descriptions = [
        v.get("description", "") for v in video_metrics_list if v.get("description")
    ]
    category      = classify_category(author_data.get("bio"), descriptions, source_hashtag)
    inf_size      = classify_influencer_size(author_data.get("followers"))
    creator_type  = classify_creator_type(
        bio=author_data.get("bio"),
        video_descriptions=descriptions,
        avg_view=metrics.get("avg_view"),
        followers=author_data.get("followers"),
    )

    creator = db.query(Creator).filter(Creator.username == username).first()

    if creator:
        # Update — prefer non-null new values over existing nulls
        if author_data.get("followers")    is not None: creator.followers    = author_data["followers"]
        if author_data.get("following")    is not None: creator.following    = author_data["following"]
        if author_data.get("total_likes")  is not None: creator.total_likes  = author_data["total_likes"]
        if author_data.get("display_name") is not None: creator.display_name = author_data["display_name"]
        if author_data.get("bio")          is not None: creator.bio          = author_data["bio"]
        if metrics.get("avg_view")         is not None: creator.avg_view     = metrics["avg_view"]
        if metrics.get("avg_like")         is not None: creator.avg_like     = metrics["avg_like"]
        if metrics.get("avg_comment")      is not None: creator.avg_comment  = metrics["avg_comment"]
        if metrics.get("engagement_rate")  is not None: creator.engagement_rate = metrics["engagement_rate"]
        if metrics.get("videos_per_month") is not None: creator.videos_per_month = metrics["videos_per_month"]
        creator.category_target  = category
        creator.influencer_size  = inf_size
        creator.creator_type     = creator_type
        creator.updated_at       = datetime.utcnow()
        logger.debug(f"Updated creator: {username}")
    else:
        creator = Creator(
            username=username,
            display_name=author_data.get("display_name"),
            platform="TikTok",
            followers=author_data.get("followers"),
            following=author_data.get("following"),
            total_likes=author_data.get("total_likes"),
            profile_url=author_data.get("profile_url"),
            bio=author_data.get("bio"),
            category_target=category,
            influencer_size=inf_size,
            creator_type=creator_type,
            engagement_rate=metrics.get("engagement_rate"),
            avg_view=metrics.get("avg_view"),
            avg_like=metrics.get("avg_like"),
            avg_comment=metrics.get("avg_comment"),
            videos_per_month=metrics.get("videos_per_month"),
            notes=None,
            first_found_hashtag=source_hashtag,
        )
        db.add(creator)
        db.flush()   # get creator.id before saving raw data
        logger.info(f"New creator saved: {username}")

    # ── Save raw items ──
    for raw_item in raw_items:
        rd = RawData(
            creator_id=creator.id,
            source_hashtag=source_hashtag,
            apify_run_id=apify_run_id,
            raw_json=json.dumps(raw_item, ensure_ascii=False),
        )
        db.add(rd)

    db.commit()
    db.refresh(creator)
    return creator


# ── Per-hashtag scrape ───────────────────────────────────────────────────────

def scrape_one_hashtag(
    db: Session,
    hashtag_row: Hashtag,
    max_profiles_per_query: int,
    max_depth: int,
) -> dict:
    """
    Run the full pipeline for a single hashtag row.
    Returns a summary dict.
    """
    tag = hashtag_row.hashtag
    logger.info(f"Scraping hashtag: #{tag}  depth={hashtag_row.depth}")

    # Mark as processing
    hashtag_row.status = HashtagStatus.processing
    db.commit()

    try:
        run_id, items = run_tiktok_scrape(
            hashtags=[tag],
            max_profiles_per_query=max_profiles_per_query,
        )
    except Exception as exc:
        logger.error(f"Apify error for #{tag}: {exc}")
        hashtag_row.status = HashtagStatus.failed
        db.commit()
        return {"hashtag": tag, "status": "failed", "error": str(exc)}

    if not items:
        logger.warning(f"No items returned for #{tag}")
        hashtag_row.status = HashtagStatus.done
        hashtag_row.last_scraped_at = datetime.utcnow()
        db.commit()
        return {"hashtag": tag, "status": "done", "items": 0, "creators": 0}

    # Group by author
    grouped = group_items_by_author(items)
    creators_saved = 0

    for username, author_items in grouped.items():
        author_data = extract_author_from_item(author_items[0])
        if not author_data:
            continue

        video_metrics_list = [
            vm for item in author_items
            for vm in [extract_video_metrics(item)]
            if vm is not None
        ]

        upsert_creator(
            db=db,
            author_data=author_data,
            video_metrics_list=video_metrics_list,
            source_hashtag=tag,
            apify_run_id=run_id,
            raw_items=author_items,
        )
        creators_saved += 1

    # Save items that had no identifiable author (still useful raw data)
    unknown_count = 0
    for item in items:
        author = extract_author_from_item(item)
        if not author:
            rd = RawData(
                creator_id=None,
                source_hashtag=tag,
                apify_run_id=run_id,
                raw_json=json.dumps(item, ensure_ascii=False),
            )
            db.add(rd)
            unknown_count += 1
    if unknown_count:
        db.commit()

    # Discover related hashtags
    related = discover_hashtags_from_items(items)
    new_queue_count = 0
    if hashtag_row.depth < max_depth:
        for rel_tag in related:
            existing = db.query(Hashtag).filter(Hashtag.hashtag == rel_tag).first()
            if not existing:
                enqueue_hashtag(
                    db=db,
                    hashtag=rel_tag,
                    depth=hashtag_row.depth + 1,
                    source_hashtag=hashtag_row.source_hashtag or tag,
                    discovered_from=tag,
                )
                new_queue_count += 1

    # Mark done
    hashtag_row.status = HashtagStatus.done
    hashtag_row.last_scraped_at = datetime.utcnow()
    db.commit()

    summary = {
        "hashtag":        tag,
        "status":         "done",
        "apify_run_id":   run_id,
        "items_total":    len(items),
        "creators_saved": creators_saved,
        "related_queued": new_queue_count,
    }
    logger.info(f"Hashtag #{tag} done: {summary}")
    return summary


# ── Top-level job runner ─────────────────────────────────────────────────────

def run_scrape_job(
    db: Session,
    hashtags: list[str],
    max_profiles_per_query: int,
    depth: int,
) -> list[dict]:
    """
    Entry point called from the API route.
    Enqueues initial hashtags, then processes them depth-first (breadth within depth).
    Returns a list of per-hashtag summaries.
    """
    # Enqueue initial hashtags
    for tag in hashtags:
        norm = normalize_hashtag(tag)
        enqueue_hashtag(
            db=db,
            hashtag=norm,
            depth=0,
            source_hashtag=norm,
            discovered_from=None,
        )

    summaries = []

    # Process loop — keeps going until no more pending hashtags within depth
    while True:
        pending = get_pending_hashtag(db, max_depth=depth)
        if pending is None:
            break

        # Skip hashtags already in done/processing state
        # (get_pending_hashtag only returns "pending", so this is just safety)
        if pending.status != HashtagStatus.pending:
            break

        summary = scrape_one_hashtag(
            db=db,
            hashtag_row=pending,
            max_profiles_per_query=max_profiles_per_query,
            max_depth=depth,
        )
        summaries.append(summary)

    return summaries
