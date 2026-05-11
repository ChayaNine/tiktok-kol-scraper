"""
Raw data read endpoints — for inspecting Apify responses.
Returns the raw_json as a parsed object so you can read it in Swagger.
"""

import json
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RawData

router = APIRouter()


class RawDataOut(BaseModel):
    id:             int
    creator_id:     Optional[int]
    source_hashtag: Optional[str]
    apify_run_id:   Optional[str]
    raw_json:       dict         # parsed for readability
    created_at:     datetime

    class Config:
        from_attributes = True


def _parse_raw(rd: RawData) -> dict:
    return {
        "id":             rd.id,
        "creator_id":     rd.creator_id,
        "source_hashtag": rd.source_hashtag,
        "apify_run_id":   rd.apify_run_id,
        "raw_json":       json.loads(rd.raw_json),
        "created_at":     rd.created_at,
    }


@router.get("/raw-data", tags=["Raw Data"])
def list_raw_data(
    creator_id:     Optional[int] = Query(None, description="Filter by creator ID"),
    source_hashtag: Optional[str] = Query(None, description="Filter by source hashtag"),
    limit:          int           = Query(20, ge=1, le=200),
    offset:         int           = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    View raw Apify data.
    Use this to inspect exactly what Apify returned for a creator or hashtag.
    """
    q = db.query(RawData)
    if creator_id:
        q = q.filter(RawData.creator_id == creator_id)
    if source_hashtag:
        q = q.filter(RawData.source_hashtag == source_hashtag.lstrip("#").lower())

    rows = q.order_by(RawData.id.desc()).limit(limit).offset(offset).all()
    return [_parse_raw(r) for r in rows]
