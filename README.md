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
cp .env.example .env
```

`.env` holds the connection settings and is gitignored — it is the only place
a password should ever appear. [.env.example](.env.example) is the committed
template that documents every key. Every setting has a working local default,
so the defaults run as-is against a local MongoDB and Redis.

### Using MongoDB Atlas instead of a local MongoDB

Put the Atlas connection string in `.env` and change nothing else:

```bash
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
```

Two things that catch people out: your IP has to be allowed under Atlas
**Network Access**, and a password containing `@ : / ?` must be
percent-encoded (`@` becomes `%40`). The same idea applies to a hosted Redis
— set `REDIS_URL` to a `rediss://` URL.

Verify either with `curl localhost:5001/health` once the API is up.

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

### 2. What a cache is worth depends on what is behind it

Run the same two queries against a **local MongoDB**:

```
Market overview — every town ranked (Mongo walks the whole collection)
  miss:  21.97 ms      hit:  1.19 ms       ~18x faster
One town — indexed, touches ~1,000 documents
  miss:   5.67 ms      hit:  1.29 ms        ~4x faster
```

Only the first one is really worth caching. Put Redis in front of a fast
indexed lookup and you have added a second system to keep consistent in
exchange for almost nothing.

Now move the database to **MongoDB Atlas** and change nothing else:

```
Market overview
  miss: 1747.59 ms     hit:  3.52 ms      ~496x faster
One town — the same indexed lookup
  miss: 1840.78 ms     hit:  6.90 ms      ~267x faster
```

The cheap query got expensive. Nothing about the query changed — the database
just moved to the other end of a network connection, and the round trip now
costs far more than the work. That is the lesson worth stopping on:

**"Should I cache this?" is not a property of the query. It depends on where
the data lives and what it costs to get there.**

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

## Licence

The code is MIT licensed — see [LICENSE](LICENSE). Use it, fork it, teach with
it. The dataset has its own separate terms, below.

## Data

Contains information from **Resale Flat Prices**, accessed on 21 August 2026
from [data.gov.sg](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view),
which is made available under the terms of the
[Singapore Open Data Licence version 1.0](https://data.gov.sg/open-data-licence).

That licence permits redistribution — which is why the CSV can be committed
here — provided this notice travels with it. If you fork this repo, keep the
notice.

No API key or account is needed to pull the data yourself.

[data/hdb_resale.csv](data/hdb_resale.csv) is a 24,000-row sample of that
dataset, committed so the class does not depend on the API being reachable.
`price_per_sqm` is the one column we derive ourselves; everything else is as
published.
