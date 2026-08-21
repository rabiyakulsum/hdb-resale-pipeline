"""Shared configuration and connection helpers for the HDB resale pipeline.

Every step imports from here so there is exactly one place that knows
where MongoDB lives, where Redis lives, and where files land.
"""
from pathlib import Path

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_CSV = DATA_DIR / "hdb_resale.csv"

# --- Storage layers --------------------------------------------------------
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "hdb_demo"
MONGO_COLLECTION = "resale_flats"

REDIS_HOST = "localhost"
REDIS_PORT = 6379
CACHE_TTL_SECONDS = 60

# --- The real dataset we extract (Step 1) ----------------------------------
# HDB resale flat prices, 2017 onwards - data.gov.sg, no API key needed.
# 238,000+ real transactions across 24 towns.
DATA_GOV_URL = "https://data.gov.sg/api/action/datastore_search"
RESALE_DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"

N_RECORDS = 100   # how many rows we pull for class
PAGE_SIZE = 50    # deliberately small, so paging takes more than one request
PAGE_PAUSE_SECONDS = 1.2   # data.gov.sg returns 429 if you page too fast

# --- Our own API (Step 5) --------------------------------------------------
API_PORT = 5001  # 5000 is AirPlay Receiver on macOS


def get_db():
    """Return the MongoDB database handle (the system of record)."""
    from pymongo import MongoClient

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    return client[MONGO_DB]


def get_redis():
    """Return the Redis client (the speed layer)."""
    import redis

    return redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
    )
