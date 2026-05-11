"""
Hashtag read endpoints.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Hashtag, HashtagStatus

router = APIRouter()


class HashtagOut(BaseModel):
    id:              int
    hashtag:         str
    status:          str
    depth:           int
    source_hashtag:  Optional[str]
    discovered_from: Optional[str]
    last_scraped_at: Optional[datetime]
    created_at:      datetime
    updated_at:      datetime

    class Config:
        from_attributes = True


@router.get("/hashtags", response_model=list[HashtagOut], tags=["Hashtags"])
def list_hashtags(
    status: Optional[str] = Query(None, description="pending / processing / done / failed / skipped"),
    limit:  int           = Query(200, ge=1, le=2000),
    offset: int           = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all hashtags in the queue with optional status filter."""
    q = db.query(Hashtag)
    if status:
        try:
            q = q.filter(Hashtag.status == HashtagStatus(status))
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    return q.order_by(Hashtag.depth, Hashtag.id).limit(limit).offset(offset).all()
