"""Step 4 - Redis: the speed layer, introduced only once it is needed.

By now the API works and the dashboard is visibly slow on the town summary.
Step 4 does not change what the answer IS - it changes how long it takes to
get it. That is the whole idea of a cache: same answer, different cost.

    cache-then-store:  look in Redis -> hit? return it
                                     -> miss? ask MongoDB, remember, return

revenue-style aggregations are the classic thing to cache: expensive to
compute, identical for every user who asks, and fine to be a few seconds
stale.
"""
import json
import time

from config import CACHE_TTL_SECONDS, get_redis

# NEW TO REDIS? It is a dictionary that lives in memory, in its own process:
#
#   r.get(key)              read a value, or None if it is not there
#   r.setex(key, ttl, val)  write a value that DELETES ITSELF after ttl seconds
#
# Two consequences worth saying out loud. Redis only stores strings, so we
# json.dumps() on the way in and json.loads() on the way out. And because it
# holds everything in RAM, it is fast but it is not the truth - MongoDB is.
# Anything in here can vanish and the system must still be correct.
from step2_load_mongo import market_overview, town_summary


def cached(key, compute, ttl=CACHE_TTL_SECONDS):
    """Generic cache-then-store: return the cached value, or compute and keep it.

    The same four lines as cached_town_summary() below, with the specific
    query swapped for any function. Used for the queries that are identical
    for every visitor - the town list, the dataset summary - which are the
    textbook things to cache: expensive to fetch, same answer for everyone,
    and harmless if a few seconds stale.
    """
    r = get_redis()
    hit = r.get(key)
    if hit is not None:
        return json.loads(hit)

    value = compute()
    r.setex(key, ttl, json.dumps(value))
    return value


def cached_town_summary(town, ttl=CACHE_TTL_SECONDS, verbose=False):
    """town_summary() with Redis in front of it."""
    r = get_redis()
    key = f"town:{town}"   # e.g. "town:BEDOK" - one cache entry per town

    t0 = time.perf_counter()
    cached = r.get(key)
    if cached is not None:
        if verbose:
            print(f"  CACHE HIT  {key}")
        result = json.loads(cached)
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        result["source"] = "redis"
        return result

    if verbose:
        print(f"  CACHE MISS {key} -> aggregating in MongoDB")

    # Cache miss: do the expensive thing, then remember the answer so the
    # next caller does not have to. The TTL is our tolerance for staleness -
    # after it expires the next request pays full price again.
    result = town_summary(town)
    r.setex(key, ttl, json.dumps(result))
    return result


def cached_market_overview(ttl=CACHE_TTL_SECONDS):
    """market_overview() with Redis in front of it.

    This is where the cache earns its keep: the underlying aggregation walks
    the whole collection, and every visitor asks for the same answer.
    """
    r = get_redis()
    key = "market:overview"

    t0 = time.perf_counter()
    cached = r.get(key)
    if cached is not None:
        result = json.loads(cached)
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        result["source"] = "redis"
        return result

    result = market_overview()
    r.setex(key, ttl, json.dumps(result))
    return result


def demo_overview():
    """The headline comparison: whole-collection aggregation, cached or not."""
    get_redis().delete("market:overview")   # start from a guaranteed miss

    miss = cached_market_overview()
    hit = cached_market_overview()
    speedup = miss["elapsed_ms"] / hit["elapsed_ms"] if hit["elapsed_ms"] else 0

    print("Market overview - every town, ranked by price per sqm")
    print(f"  miss: {miss['elapsed_ms']:>8.2f} ms  (mongodb walks {len(miss['towns'])} towns)")
    print(f"  hit:  {hit['elapsed_ms']:>8.2f} ms  (redis)     ~{speedup:.0f}x faster")
    print(f"  priciest: {hit['towns'][0]['town']} at "
          f"${hit['towns'][0]['avg_price_per_sqm']:,.0f}/sqm")
    return miss, hit


def demo(town):
    """Show the miss/hit difference side by side."""
    # Delete the key first, otherwise a leftover entry from an earlier run
    # makes the "miss" a hit and the demo shows nothing.
    get_redis().delete(f"town:{town}")

    miss = cached_town_summary(town, verbose=True)
    hit = cached_town_summary(town, verbose=True)

    speedup = miss["elapsed_ms"] / hit["elapsed_ms"] if hit["elapsed_ms"] else 0
    print(f"  miss: {miss['elapsed_ms']:>8.2f} ms  (mongodb)")
    print(f"  hit:  {hit['elapsed_ms']:>8.2f} ms  (redis)     ~{speedup:.0f}x faster")
    print(f"  same answer either way: avg ${hit.get('avg_price', 0):,.0f} "
          f"over {hit.get('transactions', 0):,} transactions")
    return miss, hit
