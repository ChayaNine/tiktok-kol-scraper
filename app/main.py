"""
TikTok KOL/KOC Scraper — FastAPI application.
Run with:  uvicorn app.main:app --reload --port 8000
"""

import logging
from fastapi import FastAPI
from app.database import engine, Base
from app.routes import health, scrape, creators, hashtags, raw_data

# Create all tables on startup
Base.metadata.create_all(bind=engine)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

app = FastAPI(
    title="TikTok KOL/KOC Scraper",
    description=(
        "Local backend that scrapes TikTok creators via Apify, "
        "stores profiles and raw data, and discovers related hashtags."
    ),
    version="1.0.0",
)

# Register all routers
app.include_router(health.router)
app.include_router(scrape.router)
app.include_router(creators.router)
app.include_router(hashtags.router)
app.include_router(raw_data.router)
