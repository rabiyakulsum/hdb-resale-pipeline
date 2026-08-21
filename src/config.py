"""Shared configuration and connection helpers for the HDB resale pipeline.

Every step imports from here so there is exactly one place that knows where
MongoDB lives, where Redis lives, and where files land.

WHERE SETTINGS COME FROM

    Connection details live in a .env file in the project root, NOT in this
    file, because they change per machine and can contain passwords. Copy
    .env.example to .env and edit it:

        cp .env.example .env

    .env is gitignored. .env.example is committed and holds no real
    credentials - it is the template that tells you which keys exist.

    Everything below falls back to a sensible local default, so the project
    still runs with no .env at all.

    Teaching constants (page sizes, the dataset id) stay in this file. They
    are part of the lesson, not part of the environment.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_CSV = DATA_DIR / "hdb_resale.csv"

# Read PROJECT_ROOT/.env into the environment. Real environment variables
# already set in the shell win, which is how deployments override a file.
load_dotenv(PROJECT_ROOT / ".env")

# --- Storage layers --------------------------------------------------------
# Local default is a plain mongod. For MongoDB Atlas, put the full
# mongodb+srv://... string in .env instead - nothing else needs to change.
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "hdb_demo")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "resale_flats")

# One URL rather than host/port/password, so the same setting works for a
# local Redis and a hosted one. rediss:// (two s) means TLS.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# --- The real dataset we extract (Step 1) ----------------------------------
# HDB resale flat prices, 2017 onwards - data.gov.sg, no API key needed.
# 238,000+ real transactions across 26 towns.
DATA_GOV_URL = "https://data.gov.sg/api/action/datastore_search"
RESALE_DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"

N_RECORDS = 100   # how many rows we pull for class
PAGE_SIZE = 50    # deliberately small, so paging takes more than one request
PAGE_PAUSE_SECONDS = 1.2   # data.gov.sg returns 429 if you page too fast

# --- Our own API (Step 3) --------------------------------------------------
API_PORT = int(os.getenv("API_PORT", "5001"))  # 5000 is AirPlay on macOS


def get_db():
    """Return the MongoDB database handle (the system of record)."""
    from pymongo import MongoClient

    # A longer timeout than a local socket needs, because Atlas is a network
    # round trip away and a cold cluster can take a moment to answer.
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10_000)
    return client[MONGO_DB]


def get_redis():
    """Return the Redis client (the speed layer)."""
    import redis

    # decode_responses=True hands us str instead of bytes, so callers can
    # json.loads() the result directly.
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)
