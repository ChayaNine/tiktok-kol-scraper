"""
Creator read endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import Creator

router = APIRouter()


# ── Response schema ──────────────────────────────────────────────────────────

class CreatorOut(BaseModel):
    id:                  int
    username:            str
    display_name:        Optional[str]
    platform:            str
    followers:           Optional[int]
    following:           Optional[int]
    total_likes:         Optional[int]
    profile_url:         Optional[str]
    bio:                 Optional[str]
    category_target:     Optional[str]
    influencer_size:     Optional[str]
    creator_type:        Optional[str]
    engagement_rate:     Optional[float]
    avg_view:            Optional[float]
    avg_like:            Optional[float]
    avg_comment:         Optional[float]
    videos_per_month:    Optional[float]
    notes:               Optional[str]
    first_found_hashtag: Optional[str]
    created_at:          datetime
    updated_at:          datetime

    class Config:
        from_attributes = True


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/creators", response_model=list[CreatorOut], tags=["Creators"])
def list_creators(
    category:       Optional[str] = Query(None, description="Filter by category_target: DIY / Garden / Unknown"),
    influencer_size: Optional[str] = Query(None, description="Filter by influencer_size: Nano / Micro / MOF / Mega"),
    creator_type:   Optional[str] = Query(None, description="Filter by creator_type: KOC / KOL / Creator / Unknown"),
    hashtag:        Optional[str] = Query(None, description="Filter by first_found_hashtag"),
    limit:          int           = Query(100, ge=1, le=1000),
    offset:         int           = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List creators with optional filters.
    Results are ordered by followers descending (highest first).
    """
    q = db.query(Creator)
    if category:
        q = q.filter(Creator.category_target == category)
    if influencer_size:
        q = q.filter(Creator.influencer_size == influencer_size)
    if creator_type:
        q = q.filter(Creator.creator_type == creator_type)
    if hashtag:
        q = q.filter(Creator.first_found_hashtag == hashtag.lstrip("#").lower())

    return (
        q.order_by(Creator.followers.desc().nullslast())
         .limit(limit)
         .offset(offset)
         .all()
    )


@router.get("/creators/{creator_id}", response_model=CreatorOut, tags=["Creators"])
def get_creator(creator_id: int, db: Session = Depends(get_db)):
    """Get a single creator by ID."""
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Creator not found")
    return creator
