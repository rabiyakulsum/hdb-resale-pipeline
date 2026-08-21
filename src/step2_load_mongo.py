"""Step 2 - Load into MongoDB: the system of record.

Durable, queryable, the source of truth. Everything downstream (the API, the
cache, the served API) reads from here, not from the CSV.

town_summary() lives here and is deliberately UNCACHED. It is the slow thing
that Step 4 later makes fast - so the cache has a real problem to solve
instead of being introduced as a good idea in the abstract.
"""
import time

from config import MONGO_COLLECTION, get_db


def load_flats(df, drop_existing=True):
    """Insert the DataFrame into MongoDB. Returns the doc count."""
    db = get_db()
    coll = db[MONGO_COLLECTION]

    if drop_existing:
        coll.delete_many({})  # keep re-runs idempotent

    coll.insert_many(df.to_dict("records"))

    # An index on town makes the town aggregation and the ?town= filter
    # cheap - part of the architecture, not an extra.
    coll.create_index("town")
    return coll.count_documents({})


def read_flats(query=None, limit=None):
    """Read flats back out, without Mongo's internal _id field."""
    cursor = get_db()[MONGO_COLLECTION].find(query or {}, {"_id": 0})
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def list_towns():
    """Every town we hold, sorted. Used by the API and the dashboard."""
    return sorted(get_db()[MONGO_COLLECTION].distinct("town"))


def town_summary(town):
    """Aggregate resale stats for one town, straight from MongoDB.

    No cache. Every call re-scans the town's documents and recomputes.
    Returns the timing alongside the numbers so the cost is visible.
    """
    t0 = time.perf_counter()
    pipeline = [
        {"$match": {"town": town}},
        {
            "$group": {
                "_id": "$town",
                "transactions": {"$sum": 1},
                "avg_price": {"$avg": "$resale_price"},
                "min_price": {"$min": "$resale_price"},
                "max_price": {"$max": "$resale_price"},
                "avg_price_per_sqm": {"$avg": "$price_per_sqm"},
            }
        },
    ]
    rows = list(get_db()[MONGO_COLLECTION].aggregate(pipeline))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not rows:
        return {"town": town, "transactions": 0, "elapsed_ms": round(elapsed_ms, 2)}

    row = rows[0]
    return {
        "town": row["_id"],
        "transactions": row["transactions"],
        "avg_price": round(row["avg_price"], 2),
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "avg_price_per_sqm": round(row["avg_price_per_sqm"], 2),
        "elapsed_ms": round(elapsed_ms, 2),
        "source": "mongodb",
    }


def market_overview():
    """Every town ranked by price per sqm - the whole-dataset question.

    This is the expensive one, and the reason Step 4 exists. Unlike
    town_summary() there is no $match to narrow things down first: Mongo
    walks the entire collection, groups it, and sorts the result. It is
    also the query a dashboard homepage runs for every single visitor,
    which is exactly the profile of something worth caching.
    """
    t0 = time.perf_counter()
    rows = list(get_db()[MONGO_COLLECTION].aggregate([
        {
            "$group": {
                "_id": "$town",
                "transactions": {"$sum": 1},
                "avg_price": {"$avg": "$resale_price"},
                "avg_price_per_sqm": {"$avg": "$price_per_sqm"},
            }
        },
        {"$sort": {"avg_price_per_sqm": -1}},
    ]))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    for row in rows:
        row["town"] = row.pop("_id")
        row["avg_price"] = round(row["avg_price"], 2)
        row["avg_price_per_sqm"] = round(row["avg_price_per_sqm"], 2)

    return {"towns": rows, "elapsed_ms": round(elapsed_ms, 2), "source": "mongodb"}
