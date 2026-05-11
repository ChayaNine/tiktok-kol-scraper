# TikTok KOL/KOC Scraper — Complete Local System

---

## 1. Final System Architecture

```
POST /scrape
    │
    ▼
ScrapeJob (DB row)
    │
    ▼
run_scrape_job()
    │
    ├── enqueue_hashtag()       — adds to Hashtag table if not already there
    │
    └── loop: get_pending_hashtag()
              │
              ├── Apify actor GdWCkxBtKWOsKjdch  ← HTTP call
              │         returns raw items
              │
              ├── group_items_by_author()
              │         for each author:
              │             upsert_creator()
              │             calculate_creator_metrics()
              │             classify_influencer_size / creator_type / category
              │             save RawData rows
              │
              ├── discover_hashtags_from_items()
              │         enqueue new hashtags at depth+1
              │
              └── mark Hashtag as done
```

**Tech stack**
| Layer       | Tool                         |
|-------------|------------------------------|
| API         | FastAPI + Uvicorn            |
| DB (local)  | SQLite                       |
| ORM         | SQLAlchemy 2.x               |
| Scraping    | Apify Python client          |
| Config      | python-dotenv / pydantic-settings |
| Python      | 3.11+                        |

---

## 2. Folder Structure

```
tiktok-kol-scraper/
├── .env                          ← YOU CREATE THIS (copy from .env.example)
├── .env.example
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── main.py                   ← FastAPI app + table creation
    ├── config.py                 ← loads .env
    ├── database.py               ← SQLAlchemy engine + get_db()
    ├── models.py                 ← Creator, RawData, Hashtag, ScrapeJob
    ├── routes/
    │   ├── __init__.py
    │   ├── health.py             ← GET /health
    │   ├── scrape.py             ← POST /scrape
    │   ├── creators.py           ← GET /creators  GET /creators/{id}
    │   ├── hashtags.py           ← GET /hashtags
    │   └── raw_data.py           ← GET /raw-data
    ├── services/
    │   ├── __init__.py
    │   ├── apify_service.py      ← calls Apify actor
    │   └── scraper_service.py    ← main orchestration
    └── utils/
        ├── __init__.py
        ├── classification.py     ← influencer size, creator type, category
        └── extraction.py        ← parse Apify items, metrics, hashtag discovery
```

---

## 3. Setup Commands (Windows PowerShell)

Open PowerShell in your project folder and run these commands one by one.

```powershell
# 3-1  Go to your project root (change path as needed)
cd C:\Projects\tiktok-kol-scraper

# 3-2  Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# If you get an execution policy error, run this first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3-3  Install dependencies
pip install -r requirements.txt

# 3-4  Copy env file and fill in your token
Copy-Item .env.example .env
notepad .env
# → Replace the placeholder with your real Apify API token, then save and close.
```

---

## 4. requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
apify-client==1.7.1
python-dotenv==1.0.1
pydantic==2.7.1
pydantic-settings==2.2.1
aiohttp==3.9.5
```

---

## 5. .env.example

```
APIFY_API_TOKEN=apify_api_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
DATABASE_URL=sqlite:///./tiktok_kol.db
```

After copying to `.env`, replace `apify_api_XXXXX...` with your real token.
Find your token at: https://console.apify.com/account/integrations

---

## 6. Database Models

Four tables:

| Table        | Purpose                                               |
|--------------|-------------------------------------------------------|
| `creators`   | One row per unique TikTok creator                     |
| `raw_data`   | Every raw Apify item JSON (linked to creator if found)|
| `hashtags`   | Hashtag queue + status tracking                       |
| `scrape_jobs`| One row per POST /scrape call                         |

Tables are created automatically on first startup — no migration needed.

---

## 7. Apify Service (`app/services/apify_service.py`)

- Uses `ApifyClient` from the official `apify-client` Python package.
- Reads `APIFY_API_TOKEN` from `.env` — never hardcoded.
- Calls actor `GdWCkxBtKWOsKjdch` synchronously (`.call()` blocks until done).
- Returns `(run_id, items)` — the run ID is stored for traceability.

---

## 8. Data Extraction / Normalization Logic

File: `app/utils/extraction.py`

**`extract_author_from_item(item)`**
Apify returns different shapes depending on whether an item is a video or profile.
This function tries `authorMeta`, `author`, `userInfo` in that order.
Fields extracted: username, display_name, followers, following, total_likes, bio, profile_url.

**`extract_video_metrics(item)`**
Tries `statsV2` then `stats`.
Fields: plays, likes, comments, shares, created_at (from Unix timestamp), description.

**`group_items_by_author(items)`**
Groups all items from one Apify run by `username` so we can aggregate per creator.

---

## 9. Engagement Rate Calculation

Formula:
```
engagement_rate = (avg_like + avg_comment) / avg_view × 100
```

Only calculated when at least one video has both likes and comments.
Stored as a percentage (e.g., `4.5` means 4.5%).

Other metrics:
- `avg_view`, `avg_like`, `avg_comment` — simple mean across all videos for that creator.
- `videos_per_month` — calculated as `video_count / (date_span_days / 30)`.
  Requires at least 2 videos with timestamps. Otherwise `null`.

---

## 10. Hashtag Discovery Logic

File: `app/utils/extraction.py` → `discover_hashtags_from_items()`

For every Apify item returned, it extracts hashtags from:
1. `challenges` array (TikTok's native hashtag objects on videos)
2. `desc` / `text` / `description` — using regex `#word`
3. `textExtra` array (TikTok API supplement)

New hashtags are added to the `hashtags` table with `depth = current_depth + 1`.
They are only added if they do not already exist in the table.
The loop in `run_scrape_job()` only processes hashtags up to the requested `depth`.

---

## 11. FastAPI Routes

| Method | Path                  | Description                              |
|--------|-----------------------|------------------------------------------|
| GET    | `/health`             | Health check                             |
| POST   | `/scrape`             | Trigger a scraping job                   |
| GET    | `/creators`           | List creators (filterable)               |
| GET    | `/creators/{id}`      | Get one creator                          |
| GET    | `/hashtags`           | List hashtag queue                       |
| GET    | `/raw-data`           | View raw Apify items                     |

---

## 12. Full File Code

All files are in the project folder. Summary of each:

| File                             | Role                                         |
|----------------------------------|----------------------------------------------|
| `app/main.py`                    | App entry point, table creation, router registration |
| `app/config.py`                  | Reads .env via pydantic-settings             |
| `app/database.py`                | SQLAlchemy engine, SessionLocal, get_db()    |
| `app/models.py`                  | All ORM models + enums                       |
| `app/utils/extraction.py`        | Parse Apify items, metrics, hashtag discovery|
| `app/utils/classification.py`    | Influencer size, creator type, category      |
| `app/services/apify_service.py`  | Apify API call wrapper                       |
| `app/services/scraper_service.py`| Orchestration: queue, scrape, upsert, discover|
| `app/routes/health.py`           | GET /health                                  |
| `app/routes/scrape.py`           | POST /scrape                                 |
| `app/routes/creators.py`         | GET /creators, GET /creators/{id}            |
| `app/routes/hashtags.py`         | GET /hashtags                                |
| `app/routes/raw_data.py`         | GET /raw-data                                |

---

## 13. How to Run the Project

```powershell
# Make sure venv is active and you are in the project root
.\venv\Scripts\Activate.ps1

# Start the server
uvicorn app.main:app --reload --port 8000
```

You will see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

The SQLite database file `tiktok_kol.db` is created automatically in the project root.

---

## 14. How to Test Using Swagger

Open your browser and go to:
```
http://127.0.0.1:8000/docs
```

This is the interactive Swagger UI. You can:
1. Click any endpoint.
2. Click **Try it out**.
3. Fill in the request body.
4. Click **Execute**.
5. See the response below.

---

## 15. Example API Request Bodies

### POST /scrape — minimal test (cheap, only 5 profiles)
```json
{
  "hashtags": ["ทำสวน"],
  "max_profiles_per_query": 5,
  "depth": 0
}
```

### POST /scrape — real DIY scrape, 2 levels deep
```json
{
  "hashtags": ["ซ่อมบ้านเอง", "ทำสวน", "DIYง่ายๆ"],
  "max_profiles_per_query": 30,
  "depth": 2
}
```

### POST /scrape — full initial seed (all your keywords at once)
```json
{
  "hashtags": [
    "ซ่อมบ้านเอง", "ซ่อมของเอง", "งานช่างมือใหม่", "ติดตั้งของในบ้าน",
    "DIYง่ายๆ", "รีโนเวท", "แต่งบ้าน", "ช่างประจำบ้าน",
    "ทำสวน", "ดูแลสวน", "จัดสวนหน้าบ้าน", "ปลูกผัก",
    "สวนครัว", "ปลูกกินเอง", "เกษตรขนาดเล็ก", "คนรักต้นไม้"
  ],
  "max_profiles_per_query": 20,
  "depth": 1
}
```

### GET /creators — filter for Micro KOLs in Garden
```
GET /creators?category=Garden&influencer_size=Micro&creator_type=KOL
```

### GET /creators — filter by source hashtag
```
GET /creators?hashtag=ทำสวน
```

### GET /raw-data — inspect raw Apify data for a creator
```
GET /raw-data?creator_id=1
```

### GET /hashtags — see what's in the queue
```
GET /hashtags?status=pending
```

---

## 16. How to Inspect the SQLite Database

Install DB Browser for SQLite (free GUI):
https://sqlitebrowser.org/dl/

Then:
1. Open DB Browser.
2. Click **Open Database**.
3. Navigate to your project folder.
4. Select `tiktok_kol.db`.
5. Click the **Browse Data** tab.
6. Select a table from the dropdown.

Or use the SQLite command line tool in PowerShell:

```powershell
# Install sqlite3 if not present (or use the one bundled with Python)
python -c "import sqlite3; conn = sqlite3.connect('tiktok_kol.db'); print([row for row in conn.execute('SELECT username, followers, influencer_size FROM creators LIMIT 10')])"
```

Or open a Python shell:
```python
import sqlite3, json
conn = sqlite3.connect("tiktok_kol.db")
conn.row_factory = sqlite3.Row

# See all creators
for row in conn.execute("SELECT * FROM creators LIMIT 10"):
    print(dict(row))

# Count by influencer size
for row in conn.execute("SELECT influencer_size, COUNT(*) as n FROM creators GROUP BY influencer_size"):
    print(dict(row))

# See all hashtags
for row in conn.execute("SELECT hashtag, status, depth FROM hashtags ORDER BY depth, id"):
    print(dict(row))

# Inspect one raw item
row = conn.execute("SELECT raw_json FROM raw_data LIMIT 1").fetchone()
print(json.loads(row["raw_json"]))
```

---

## 17. How to Avoid Duplicate Hashtags and Duplicate Creators

**Hashtags**
- `hashtags.hashtag` column has a `UNIQUE` constraint.
- `enqueue_hashtag()` checks `db.query(Hashtag).filter(Hashtag.hashtag == tag).first()` before inserting.
- If the hashtag already exists (any status), the function returns the existing row without inserting.
- `get_pending_hashtag()` only returns rows with `status = pending`.
  Rows with `done`, `failed`, `skipped`, or `processing` are never picked again.

**Creators**
- `creators.username` column has a `UNIQUE` constraint.
- `upsert_creator()` queries `db.query(Creator).filter(Creator.username == username).first()`.
- If found → updates the existing row (preserves `first_found_hashtag`, updates metrics).
- If not found → inserts a new row.

This means calling POST /scrape with the same hashtags repeatedly is completely safe.
Already-scraped hashtags are skipped, and existing creators are updated rather than duplicated.

---

## 18. Error Handling Strategy

| Situation                          | Behaviour                                               |
|------------------------------------|---------------------------------------------------------|
| Apify API error (network, quota)   | Hashtag marked as `failed`, error logged, job continues with next hashtag |
| Apify returns 0 items              | Hashtag marked as `done`, warning logged, metrics remain null |
| Author cannot be extracted         | Raw item saved with `creator_id = null`, creator not created |
| Missing fields from Apify          | All fields are `Optional` / nullable — stored as `null` |
| Calculation impossible (0 videos)  | Metric stored as `null`, never faked                    |
| Duplicate username insert          | Caught by `upsert_creator()` logic — UPDATE instead of INSERT |
| Entire job exception               | `ScrapeJob.status = failed`, `error_message` saved, HTTP 500 returned |

Logging uses Python's standard `logging` module.
All errors go to console with timestamps. Set `echo=True` in `database.py` to also see all SQL.

---

## 19. What Data May Be Unavailable from Apify

This actor does not always return every field. **Never assume these are present.**

| Field              | Notes                                                   |
|--------------------|---------------------------------------------------------|
| `following`        | Sometimes omitted or zero                               |
| `total_likes`      | Sometimes called `heart` or `heartCount` — mapped in code |
| `bio`              | Empty for many creators                                 |
| `avg_view`         | Only calculated if video items are returned             |
| `videos_per_month` | Needs ≥2 videos with timestamps                         |
| `engagement_rate`  | Needs both likes and views per video                    |
| `email`            | NOT available via Apify TikTok actor                    |
| `phone`            | NOT available                                           |
| `location`         | NOT available reliably                                  |
| `website`          | NOT available directly (may appear in bio text)         |
| `category` (TikTok official) | NOT available — we classify ourselves          |

**Rule:** if Apify does not provide it → stored as `null`. Never estimated or fabricated.

---

## 20. Next Improvements After Local Version Works

In priority order:

1. **Background tasks** — Move `run_scrape_job()` to FastAPI `BackgroundTasks` or Celery
   so POST /scrape returns immediately with a job ID instead of waiting.

2. **Job status endpoint** — Add `GET /jobs/{job_id}` to poll progress.

3. **PostgreSQL migration** — Change `DATABASE_URL` in `.env` to a Postgres URL.
   No code changes needed — SQLAlchemy handles it. Just `pip install psycopg2-binary`.

4. **Rate limiting / scheduling** — Add a delay between hashtag scrapes to avoid
   hitting Apify rate limits on large runs.

5. **CSV / Excel export** — Add `GET /creators/export.csv` using Python's `csv` module.

6. **Better category classification** — Replace keyword matching with a simple ML model
   trained on labelled creator bios.

7. **Webhook support** — Let Apify push results back instead of polling, reducing wait time.

8. **Deduplication by profile URL** — Some creators may appear under different `uniqueId`
   values if they change usernames. Cross-check by profile URL.

9. **Incremental scraping** — Store `last_scraped_at` per creator and re-scrape only creators
   older than N days, not all hashtags.

10. **Dashboard UI** — A simple React/HTML page calling these APIs to show creator tables,
    charts by influencer size, and hashtag discovery trees.
