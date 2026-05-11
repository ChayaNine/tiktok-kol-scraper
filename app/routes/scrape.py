"""
POST /scrape  — trigger a scraping job.
The job runs synchronously in the same request for simplicity.
(A future improvement can move this to a background task / Celery.)
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScrapeJob, JobStatus
from app.services.scraper_service import run_scrape_job

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    hashtags: list[str] = Field(
        ...,
        example=["ซ่อมบ้านเอง", "ทำสวน"],
        description="List of hashtags or keywords to scrape (# is optional).",
    )
    max_profiles_per_query: int = Field(
        default=10,
        ge=1,
        le=100,
        description="How many profiles Apify should collect per hashtag.",
    )
    depth: int = Field(
        default=1,
        ge=0,
        le=3,
        description="How many levels of related-hashtag discovery to follow.",
    )


class ScrapeResponse(BaseModel):
    job_id: int
    status: str
    summaries: list[dict]
    started_at: datetime
    finished_at: datetime


# ── Route ────────────────────────────────────────────────────────────────────

@router.post("/scrape", response_model=ScrapeResponse, tags=["Scraping"])
def trigger_scrape(request: ScrapeRequest, db: Session = Depends(get_db)):
    """
    Trigger a TikTok scraping job.

    - Normalises hashtags (removes #).
    - Skips hashtags already in the database.
    - Calls Apify for new hashtags.
    - Saves creators, raw data, and discovers related hashtags.
    - Continues to related hashtags up to the requested depth.
    """
    # Create job record
    job = ScrapeJob(
        status=JobStatus.running,
        started_at=datetime.utcnow(),
        input_json=json.dumps(request.model_dump(), ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        summaries = run_scrape_job(
            db=db,
            hashtags=request.hashtags,
            max_profiles_per_query=request.max_profiles_per_query,
            depth=request.depth,
        )
        job.status = JobStatus.done
    except Exception as exc:
        logger.exception("Scrape job failed")
        job.status = JobStatus.failed
        job.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Scrape job failed: {exc}")

    job.finished_at = datetime.utcnow()
    db.commit()

    return ScrapeResponse(
        job_id=job.id,
        status=job.status.value,
        summaries=summaries,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
