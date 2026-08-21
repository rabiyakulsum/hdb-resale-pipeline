# HDB Resale Pipeline — Big Data Concepts in One Hour

One data lifecycle, end to end, on **real Singapore HDB resale transactions**
from [data.gov.sg](https://data.gov.sg) — 238,573 of them, no API key required.

```
EXTRACT → STORE → SERVE → CACHE
```

The order is the point. We get it working, watch it be slow, and *then* reach
for Redis. A cache introduced before there is a slow query is just a word.

## Prerequisites

Python 3.11+, and MongoDB and Redis running locally.

```bash
# macOS
brew services start mongodb-community
brew services start redis

# Linux (systemd)
sudo systemctl start mongod redis

# or, with Docker, no local install
docker run -d -p 27017:27017 mongo
docker run -d -p 6379:6379 redis
```

Verify with `nc -z localhost 27017 && nc -z localhost 6379`, or
`curl localhost:5001/health` once the API is up.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run it

```bash
./run.sh pipeline              # Steps 1, 2, 4 — extract, store, cache
./run.sh pipeline --extract    # re-pull from data.gov.sg (~90s)
./run.sh api                   # Step 3 — serve on :5001 (own terminal)
./run.sh dashboard             # Streamlit on :8501 (own terminal)
./run.sh consume               # extract from your own pipeline
```

`api` and `dashboard` are servers — they block, so each needs its own terminal.

The dataset ships landed at [data/hdb_resale.csv](data/hdb_resale.csv), so the
pipeline does **not** hit the network unless you pass `--extract`.

For the classroom-facing walkthrough, open
[notebooks/hdb_resale_pipeline.ipynb](notebooks/hdb_resale_pipeline.ipynb) —
it runs the same code with the commentary alongside.

## The four steps

| File | Step | What it teaches |
|---|---|---|
| [src/config.py](src/config.py) | — | One place that knows where everything lives |
| [src/step1_extract.py](src/step1_extract.py) | 1 | Live API: paging, rate limits, landing a file |
| [src/step2_load_mongo.py](src/step2_load_mongo.py) | 2 | MongoDB as **system of record** |
| [src/step3_api.py](src/step3_api.py) | 3 | Build your own REST API — become the source |
| [src/step4_cache_redis.py](src/step4_cache_redis.py) | 4 | Redis as **speed layer**, and when *not* to cache |
| [src/dashboard.py](src/dashboard.py) | 3+ | Streamlit — just another API consumer |
| [src/consume_own_api.py](src/consume_own_api.py) | 3+ | Step 1's code shape pointed at localhost |
| [src/pipeline.py](src/pipeline.py) | 1–4 | Runs the lifecycle in one command |

## API endpoints

Served on **port 5001** (macOS uses 5000 for AirPlay Receiver).

```bash
curl localhost:5001/                          # self-documenting index
curl localhost:5001/towns                     # every town we hold
curl "localhost:5001/flats?town=BEDOK&limit=5"
curl "localhost:5001/flats?flat_type=4%20ROOM&limit=5"
curl localhost:5001/flats/42                  # single transaction (404 if absent)
curl localhost:5001/towns/BEDOK               # aggregated, uncached
curl "localhost:5001/overview?cache=true"     # the expensive query, cached
curl localhost:5001/stats                     # by flat type
curl localhost:5001/health                    # mongo + redis liveness
```

Every route takes `?cache=true` where a cache applies, so you can compare the
two costs live without editing code.

## Two things worth showing live

### 1. Extraction is harder than "read the file"

The API caps each response, so you page with `limit`/`offset`. Page too fast
and it returns **429** and you back off. And the rows arrive **sorted by
town** — take the first 100 and you get one town, which quietly ruins every
aggregation downstream. [step1_extract.py](src/step1_extract.py) spreads its
pages across the whole dataset instead.

### 2. A cache is only worth it when the thing behind it is expensive

```
Market overview — every town ranked (Mongo walks the whole collection)
  miss:  21.97 ms  (mongodb)
  hit:    1.19 ms  (redis)      ~18x faster

One town — Mongo has an index and touches ~1,000 documents
  miss:   5.67 ms  (mongodb)
  hit:    1.29 ms  (redis)       ~4x faster
```

The second comparison is the more useful lesson: put a cache in front of a
fast indexed lookup and you have added a second system to keep consistent in
exchange for almost nothing.

## Classroom exercise

Pair up. Student A runs `./run.sh api`. Student B runs `./run.sh consume` —
which is Step 1's `requests.get(...)` shape with only the URL changed. Student
B has now extracted from Student A's pipeline.

The point: **extraction isn't a one-time step — it's a role any system can
play, source or destination, depending on which side of the request you're
on.**

## Offline fallback

If data.gov.sg is unreachable, [step1_extract.py](src/step1_extract.py) falls
back to the CSV landed last time and says so, so a classroom with flaky wifi
can still complete the pipeline.

## Data

HDB resale flat prices, published by Singapore's Housing & Development Board
through [data.gov.sg](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view)
and made available under the
[Singapore Open Data Licence](https://data.gov.sg/open-data-licence).
No API key or account is needed to pull it.

[data/hdb_resale.csv](data/hdb_resale.csv) is a 24,000-row sample of that
dataset, committed so the class does not depend on the API being reachable.
`price_per_sqm` is the one column we derive ourselves; everything else is as
published.
