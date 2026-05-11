import logging
from apify_client import ApifyClient
from app.config import settings

logger = logging.getLogger(__name__)

ACTOR_ID = "GdWCkxBtKWOsKjdch"


def run_tiktok_scrape(
    hashtags: list,
    max_profiles_per_query: int = 10,
):
    client = ApifyClient(settings.APIFY_API_TOKEN)

    run_input = {
        "hashtags":               hashtags,
        "resultsPerPage":         100,
        "profileScrapeSections":  ["videos"],
        "profileSorting":         "latest",
        "excludePinnedPosts":     False,
        "maxFollowersPerProfile": 0,
        "maxFollowingPerProfile": 0,
        "searchSection":          "",
        "maxProfilesPerQuery":    max_profiles_per_query,
        "videoSearchSorting":     "MOST_RELEVANT",
        "videoSearchDateFilter":  "ALL_TIME",
        "scrapeRelatedVideos":    False,
        "shouldDownloadVideos":   False,
        "shouldDownloadCovers":   False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars":  False,
        "shouldDownloadMusicCovers": False,
        "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
        "commentsPerPost":        0,
        "topLevelCommentsPerPost": 0,
        "maxRepliesPerComment":   0,
        "proxyCountryCode":       "TH",
    }

    logger.info(f"[Apify] Starting run for hashtags: {hashtags}")
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    run_id = run["id"]
    logger.info(f"[Apify] Run finished. run_id={run_id}")

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    logger.info(f"[Apify] Retrieved {len(items)} items from dataset.")
    return run_id, items