"""
SQLAlchemy ORM models.
All tables are created automatically on first run via Base.metadata.create_all().
"""

import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Text, DateTime,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


# ── Enums ────────────────────────────────────────────────────────────────────

class HashtagStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    done       = "done"
    failed     = "failed"
    skipped    = "skipped"


class JobStatus(str, enum.Enum):
    pending    = "pending"
    running    = "running"
    done       = "done"
    failed     = "failed"


# ── Models ───────────────────────────────────────────────────────────────────

class Creator(Base):
    """One row per unique TikTok creator."""
    __tablename__ = "creators"

    id                  = Column(Integer, primary_key=True, index=True)
    username            = Column(String, unique=True, index=True, nullable=False)
    display_name        = Column(String, nullable=True)
    platform            = Column(String, default="TikTok", nullable=False)

    followers           = Column(BigInteger, nullable=True)
    following           = Column(BigInteger, nullable=True)
    total_likes         = Column(BigInteger, nullable=True)

    profile_url         = Column(String, nullable=True)
    bio                 = Column(Text, nullable=True)

    # Classification
    category_target     = Column(String, nullable=True)   # DIY / Garden / Unknown
    influencer_size     = Column(String, nullable=True)   # Nano / Micro / MOF / Mega
    creator_type        = Column(String, nullable=True)   # KOC / KOL / Creator / Unknown

    # Calculated metrics
    engagement_rate     = Column(Float, nullable=True)
    avg_view            = Column(Float, nullable=True)
    avg_like            = Column(Float, nullable=True)
    avg_comment         = Column(Float, nullable=True)
    videos_per_month    = Column(Float, nullable=True)

    notes               = Column(Text, nullable=True)     # empty for now
    first_found_hashtag = Column(String, nullable=True)

    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    raw_data = relationship("RawData", back_populates="creator")


class RawData(Base):
    """Stores the raw JSON from every Apify item so nothing is lost."""
    __tablename__ = "raw_data"

    id              = Column(Integer, primary_key=True, index=True)
    creator_id      = Column(Integer, ForeignKey("creators.id"), nullable=True, index=True)
    source_hashtag  = Column(String, nullable=True, index=True)
    apify_run_id    = Column(String, nullable=True)
    raw_json        = Column(Text, nullable=False)   # JSON string
    created_at      = Column(DateTime, default=datetime.utcnow)

    creator = relationship("Creator", back_populates="raw_data")

    @property
    def parsed(self):
        """Helper to get the raw data as a Python dict."""
        return json.loads(self.raw_json)


class Hashtag(Base):
    """Tracks which hashtags have been queued / scraped."""
    __tablename__ = "hashtags"

    id               = Column(Integer, primary_key=True, index=True)
    hashtag          = Column(String, unique=True, index=True, nullable=False)
    status           = Column(SAEnum(HashtagStatus), default=HashtagStatus.pending, nullable=False)
    depth            = Column(Integer, default=0, nullable=False)
    source_hashtag   = Column(String, nullable=True)   # original hashtag that triggered this job
    discovered_from  = Column(String, nullable=True)   # hashtag that led to discovering this one
    last_scraped_at  = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScrapeJob(Base):
    """One row per POST /scrape call — tracks the top-level job."""
    __tablename__ = "scrape_jobs"

    id            = Column(Integer, primary_key=True, index=True)
    status        = Column(SAEnum(JobStatus), default=JobStatus.pending, nullable=False)
    started_at    = Column(DateTime, nullable=True)
    finished_at   = Column(DateTime, nullable=True)
    input_json    = Column(Text, nullable=True)    # JSON of the original request body
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
