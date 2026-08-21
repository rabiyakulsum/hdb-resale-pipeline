"""Step 1 - Extract: pull a real dataset out of a real API, land it as a file.

HDB resale flat prices from data.gov.sg. No API key, no signup, 238,000+
real transactions.

Two things worth noticing here:

  1. The data is LIVE and someone else's. It can 500, it can time out, it can
     change between runs. Contrast a file sitting on your disk.
  2. You cannot ask for all 238,000 rows at once. The API caps a response, so
     you PAGE - loop with limit/offset until you have what you asked for.
     Paging is the first thing that makes data engineering different from
     "just read the file".

Extraction ends with the data landed as a CSV. Everything after this step
reads that file, not the API.
"""
import sys
import time

import pandas as pd
import requests

from config import (DATA_GOV_URL, N_RECORDS, PAGE_PAUSE_SECONDS, PAGE_SIZE,
                    RAW_CSV, RESALE_DATASET_ID)

# The columns we keep. The dataset has more; extraction is also the act of
# deciding what you don't need.
COLUMNS = [
    "flat_id", "month", "town", "flat_type", "block", "street_name",
    "storey_range", "floor_area_sqm", "flat_model", "lease_commence_date",
    "resale_price", "price_per_sqm",
]


def fetch_page(offset, limit, retries=5):
    """One GET against data.gov.sg. Returns (records, total_rows_available).

    Handles HTTP 429. Public APIs rate-limit you, and the polite response is
    to back off and retry, not to hammer harder. Another thing reading a
    local file never teaches you.
    """
    delay = 1.0
    for attempt in range(retries):
        resp = requests.get(
            DATA_GOV_URL,
            params={"resource_id": RESALE_DATASET_ID, "limit": limit, "offset": offset},
            timeout=90,
        )
        if resp.status_code == 429:
            print(f"    429 rate-limited, backing off {delay:.0f}s "
                  f"(attempt {attempt + 1}/{retries})")
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"API returned success=false: {body}")
        return body["result"]["records"], body["result"]["total"]

    raise RuntimeError(f"Still rate-limited after {retries} attempts at offset={offset}")


def fetch_resale(n=N_RECORDS, page_size=PAGE_SIZE, verbose=True):
    """Page across the dataset until we have n records. Returns a DataFrame.

    Note we do NOT just take the first n rows. The API hands the data back
    sorted by town, so the first 100 rows are all ANG MO KIO - and then
    "median price by town" has nothing to compare. Instead we spread our
    pages evenly across the whole dataset, which is a real sampling
    technique and the reason this function is more than one line.
    """
    _, total = fetch_page(0, 1)
    n_pages = max(1, -(-n // page_size))          # ceiling division
    stride = max(1, total // n_pages)             # one page per slice
    if verbose:
        print(f"  {total:,} rows available; taking {n_pages} pages of "
              f"{page_size}, one every {stride:,} rows")

    records = []
    for i in range(n_pages):
        want = min(page_size, n - len(records))
        page, _ = fetch_page(i * stride, want)
        if not page:
            break
        records.extend(page)
        time.sleep(PAGE_PAUSE_SECONDS)   # stay under the rate limit
        if verbose:
            print(f"  page {i + 1:>2}/{n_pages} @offset={i * stride:<7} "
                  f"+{len(page):<5} total {len(records):,}")

    return clean(records)


def clean(records):
    """Everything arrives as strings. Give the columns real types."""
    df = pd.DataFrame(records)
    df = df.rename(columns={"_id": "flat_id"})

    # Everything arrives as text - "232000", not 232000. Until we fix that,
    # sorting by price would put "99000" after "1000000" (alphabetical), and
    # summing would concatenate strings. This is the single most common
    # source of quiet, wrong answers in a pipeline.

    df["flat_id"] = df["flat_id"].astype("int64")
    df["floor_area_sqm"] = df["floor_area_sqm"].astype(float)
    df["resale_price"] = df["resale_price"].astype(float)
    df["lease_commence_date"] = df["lease_commence_date"].astype("int64")

    # A derived column - the number Singaporeans actually compare flats on.
    df["price_per_sqm"] = (df["resale_price"] / df["floor_area_sqm"]).round(2)

    return df[COLUMNS]


def extract(n=N_RECORDS, path=RAW_CSV):
    """Fetch from the API and land the result as a CSV.

    Page size scales with n. The dataset arrives sorted by town, so what
    gets us all 26 towns is MANY pages spread wide, not a few big ones.

    If the API is unreachable, fall back to the CSV we landed last time so a
    flaky network cannot block the rest of the pipeline.
    """
    t0 = time.perf_counter()
    page_size = 1_000 if n > 1_000 else PAGE_SIZE
    try:
        df = fetch_resale(n, page_size=page_size)
        df.to_csv(path, index=False)
        print(f"Wrote {len(df):,} rows to {path.name} in {time.perf_counter() - t0:.1f}s")
        return df
    except requests.exceptions.RequestException as exc:
        print(f"data.gov.sg unreachable ({exc})")
        if path.exists():
            df = pd.read_csv(path)
            print(f"Falling back to the existing {path.name} ({len(df):,} rows)")
            return df
        raise SystemExit(
            f"No network and no {path.name} to fall back on - "
            "run this once while you have a connection."
        )


def read_local(path=RAW_CSV):
    """Read the landed file. This is what Step 2 onwards actually uses."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run step1_extract.py first.")
    return pd.read_csv(path)
