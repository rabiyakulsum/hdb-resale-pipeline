# HDB Resale Pipeline — Big Data Concepts

Build a complete data pipeline, end to end, on **real Singapore HDB resale
transactions** from [data.gov.sg](https://data.gov.sg) — 238,573 of them, no
API key required.

```
EXTRACT → STORE → SERVE → CACHE
```

You pull real data out of a live government API, store it in MongoDB, serve it
back out through a REST API you write yourself, put a Streamlit dashboard on
top, and speed the whole thing up with Redis.

## What you will learn

- **Extraction is not "read the file".** Real APIs cap their responses, rate
  limit you, and hand data back in an awkward order. You will hit all three.
- **Why a database, when a CSV exists.** MongoDB earns its place the moment
  you ask a question a file cannot answer.
- **What an API actually is.** You consume one in Step 1 and become one in
  Step 3, using nearly identical code.
- **When a cache helps, and when it does not.** You will measure both, and
  find at least one case where adding Redis makes things *slower*.

The order matters. You get it working, watch it be slow, and *then* reach for
Redis — because a cache introduced before there is a slow query is just a
word.

## Where to start

Work through
[notebooks/hdb_resale_pipeline.ipynb](notebooks/hdb_resale_pipeline.ipynb).
It runs the same code as the scripts, one step at a time, with the reasoning
next to each cell. Come back here when you want to run the whole thing or
look something up.

## Prerequisites

Python 3.11+, and MongoDB and Redis running locally.

```bash
# macOS
brew services start mongodb-community
brew services start redis

# Linux (systemd)
sudo systemctl start mongod redis

# or, with Docker, if you would rather not install either
docker run -d --name hdb-mongo -p 27017:27017 mongo
docker run -d --name hdb-redis -p 6379:6379 redis

# For WSL
# --- MongoDB ---
curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt update
sudo apt install -y mongodb-org

# --- Redis ---
sudo apt install -y redis-server

# --- Start both ---
sudo systemctl start mongod
sudo systemctl start redis-server

# --- Verify ---
mongosh --eval "db.version()"
redis-cli ping

```

## To stop the services being run locally
For WSL
```bash
sudo systemctl stop mongod
sudo systemctl stop redis-server
```
For mac
```bash
brew services stop mongodb-community
brew services stop redis
```

Those two commands pull the official MongoDB and Redis images straight from
Docker Hub and run them — there is no Dockerfile or compose file in this repo
because there is nothing here to build. Stop them again with
`docker rm -f hdb-mongo hdb-redis`. Data lives inside the containers, so
removing them clears it; re-run `./run.sh pipeline` to reload.

Verify whichever you chose with `nc -z localhost 27017 && nc -z localhost 6379`,
or `curl localhost:5001/health` once the API is up.

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
pipeline does **not** hit the network unless you pass `--extract`. You can run
everything on a train with no wifi.

## The four steps

| File | Step | What you will learn from it |
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
curl localhost:5001/towns                     # every town in the data
curl "localhost:5001/flats?town=BEDOK&limit=5"   # limit defaults to 100
curl "localhost:5001/flats?flat_type=4%20ROOM&limit=5"
curl localhost:5001/flats/42                  # single transaction (404 if absent)
curl localhost:5001/towns/BEDOK               # aggregated, uncached
curl "localhost:5001/overview?cache=true"     # the expensive query, cached
curl localhost:5001/stats                     # by flat type
curl localhost:5001/health                    # mongo + redis liveness
```

Routes that hit an expensive query accept `?cache=true`, so you can compare
the cached and uncached cost yourself without editing any code.

## Three things worth understanding

### 1. Extraction is harder than "read the file"

The API caps each response, so you page with `limit`/`offset`. Page too fast
and it returns **429** and you back off. And the rows arrive **sorted by
town** — take the first 100 and you get one town, which quietly ruins every
aggregation downstream. [step1_extract.py](src/step1_extract.py) spreads its
pages across the whole dataset instead.

### 2. A cache only helps if it is closer than what it is caching

With MongoDB and Redis both on your own machine:

```
Market overview — every town ranked (Mongo walks the whole collection)
  miss:  34.79 ms      hit:  0.18 ms      ~193x faster
One town — indexed, touches ~1,000 documents
  miss:  10.80 ms      hit:  0.13 ms       ~83x faster
```

Now move both to managed services. What matters is not that they are remote —
it is how far away. These are the round trips measured from one machine:

```
Redis on localhost           0.20 ms
Redis Cloud (same region)    7.32 ms
MongoDB Atlas              194.76 ms
Redis Cloud (us-east-1)    250.18 ms
```

With Redis in the **same region** as everything else, the cache still wins
comfortably:

```
Market overview   miss: 2167.57 ms   hit: 5.73 ms     ~378x faster
One town          miss:  180.32 ms   hit: 6.27 ms      ~29x faster
```

But put that same Redis in **us-east-1**, further away than the database it is
protecting, and it collapses:

```
Market overview   miss:  418.28 ms   hit: 250.79 ms          ~2x faster
One town          miss:  207.16 ms   hit: 250.51 ms   SLOWER than no cache
```

Nothing about the code or the data changed between those two — only the
distance to the cache. A cache's entire advantage is being cheap to reach,
and 250 ms away is not cheap.

**A cache is not fast because it is Redis. It is fast because it is close.**
Put your speed layer next to whatever is asking, or do not bother.

### 3. Creating a connection is not free

Opening a connection is work: a TCP handshake, an authentication round trip,
and for Atlas an SRV DNS lookup, a TLS handshake and replica-set discovery.
Do that once and it is nothing. Do it on every query and it costs more than
the query does:

```
                       a new client each call    one reused client
Redis GET                          1625.6 ms             248.7 ms
Mongo ping                         1813.3 ms             175.3 ms
```

Against localhost the difference is invisible, which is how this mistake
survives in a lot of real code until the database moves. The helpers in
[config.py](src/config.py) build each client **once** and hand the same one
back every time — both drivers keep an internal connection pool and are
designed to be long-lived.

## Extract from your own pipeline

Run `./run.sh api` in one terminal, then `./run.sh consume` in another.

`consume_own_api.py` is Step 1's `requests.get(...)` with nothing changed but
the URL. In Step 1 you pulled from data.gov.sg; now you are pulling from
something you built, and the code cannot tell the difference.

That is the whole idea: **extraction isn't a one-time step — it's a role any
system can play, source or destination, depending on which side of the
request you're on.**

## Offline fallback

If data.gov.sg is unreachable, [step1_extract.py](src/step1_extract.py) falls
back to the CSV landed last time and says so, so a flaky network cannot
block the rest of the pipeline.

## Licence

The code is MIT licensed — see [LICENSE](LICENSE). Use it, fork it, build on
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
dataset, committed so nothing here depends on the API being reachable.
`price_per_sqm` is the only column derived here; everything else is exactly as
published.
