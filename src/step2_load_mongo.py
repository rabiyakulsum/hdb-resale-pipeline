"""Step 2 - Load into MongoDB: the system of record.

Durable, queryable, the source of truth. Everything downstream (the API, the
cache, the served API) reads from here, not from the CSV.

town_summary() lives here and is deliberately UNCACHED. It is the slow thing
that Step 4 later makes fast - so the cache has a real problem to solve
instead of being introduced as a good idea in the abstract.
"""
import time

from config import MONGO_COLLECTION, get_db

# NEW TO MONGODB? Two ideas cover everything in this file:
#
#   1. A "document" is just a dict, and a "collection" is a list of them.
#      No schema, no CREATE TABLE - you insert dicts and they are stored.
#
#   2. An "aggregation pipeline" is a list of stages that data flows through,
#      like shell pipes. Each stage takes rows in and passes rows out:
#           {"$match": ...}  keep only the rows that match   (like WHERE)
#           {"$group": ...}  collapse rows into groups       (like GROUP BY)
#           {"$sort":  ...}  order the result                (like ORDER BY)
#      The "$" prefix means "this is an operator", and "$town" means
#      "the value of the town field in this document".


def load_flats(df):
    """Insert the DataFrame into MongoDB. Returns the doc count."""
    db = get_db()
    coll = db[MONGO_COLLECTION]

    # Empty the collection first so running this twice does not give us
    # 48,000 documents. {} means "match everything". This is what makes the
    # step safe to re-run, which matters more than it sounds - a pipeline you
    # cannot run twice is a pipeline you cannot fix.
    coll.delete_many({})

    # to_dict("records") turns the DataFrame into a list of plain dicts,
    # which is exactly what Mongo wants.
    coll.insert_many(df.to_dict("records"))

    # An index on town makes the town aggregation and the ?town= filter
    # cheap - part of the architecture, not an extra.
    coll.create_index("town")
    return coll.count_documents({})


def read_flats(query=None, limit=None):
    """Read flats back out, without Mongo's internal _id field."""
    # find(what_to_match, which_fields). {"_id": 0} means "leave out the
    # _id field" - Mongo adds its own internal id that we never asked for.
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
        # Stage 1: throw away every town except the one asked for. Because
        # there is an index on `town`, Mongo jumps straight to those
        # documents instead of reading all 24,000.
        {"$match": {"town": town}},
        # Stage 2: squash what survived into a single row of totals.
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
        # No $match stage this time - nothing narrows the search first, so
        # Mongo has to walk every document in the collection. That is what
        # makes this query the expensive one, and worth caching in Step 4.
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

    # $group always names its key "_id"; rename it to something readable.
    for row in rows:
        row["town"] = row.pop("_id")
        row["avg_price"] = round(row["avg_price"], 2)
        row["avg_price_per_sqm"] = round(row["avg_price_per_sqm"], 2)

    return {"towns": rows, "elapsed_ms": round(elapsed_ms, 2), "source": "mongodb"}
