"""Step 3 - Serve it back out as your own REST API.

In Step 1 we consumed someone else's API. Here we become one. Structurally
identical: data in a store, a GET arrives, query, return JSON.

/towns/<town> takes a ?cache=true switch. Right now (Step 3) the cached side
does nothing different - Step 4 fills it in. Run the uncached route against a
full dataset first and watch the elapsed_ms: that number is the reason Step 4
exists.
"""
from flask import Flask, jsonify, request

from config import API_PORT, MONGO_COLLECTION, get_db
from step2_load_mongo import list_towns, market_overview, read_flats, town_summary

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Tiny self-documenting root, so learners can discover the routes."""
    return jsonify(
        {
            "service": "hdb-resale-pipeline",
            "endpoints": {
                "GET /flats": "resale transactions; ?town=&flat_type=&limit=",
                "GET /flats/<flat_id>": "a single transaction",
                "GET /towns": "every town we hold",
                "GET /towns/<town>": "aggregated stats; add ?cache=true for Step 4",
                "GET /overview": "every town ranked; add ?cache=true",
                "GET /stats": "dataset-level summary",
                "GET /health": "mongo + redis liveness",
            },
        }
    )


@app.route("/flats", methods=["GET"])
def get_flats():
    query = {}
    for field in ("town", "flat_type"):
        value = request.args.get(field)
        if value:
            query[field] = value

    return jsonify(read_flats(query, limit=request.args.get("limit", type=int)))


@app.route("/flats/<int:flat_id>", methods=["GET"])
def get_flat(flat_id):
    doc = get_db()[MONGO_COLLECTION].find_one({"flat_id": flat_id}, {"_id": 0})
    if doc is None:
        return jsonify({"error": f"flat {flat_id} not found"}), 404
    return jsonify(doc)


@app.route("/towns", methods=["GET"])
def get_towns():
    return jsonify(list_towns())


@app.route("/towns/<town>", methods=["GET"])
def get_town(town):
    """Aggregated stats for a town, with or without the Step 4 cache."""
    town = town.upper()
    if request.args.get("cache") == "true":
        from step4_cache_redis import cached_town_summary

        return jsonify(cached_town_summary(town))
    return jsonify(town_summary(town))


@app.route("/overview", methods=["GET"])
def overview():
    """Every town ranked. The expensive query - add ?cache=true for Step 4."""
    if request.args.get("cache") == "true":
        from step4_cache_redis import cached_market_overview

        return jsonify(cached_market_overview())
    return jsonify(market_overview())


@app.route("/stats", methods=["GET"])
def stats():
    coll = get_db()[MONGO_COLLECTION]
    by_type = list(
        coll.aggregate(
            [
                {
                    "$group": {
                        "_id": "$flat_type",
                        "transactions": {"$sum": 1},
                        "avg_price": {"$avg": "$resale_price"},
                    }
                },
                {"$sort": {"avg_price": -1}},
            ]
        )
    )
    for row in by_type:
        row["avg_price"] = round(row["avg_price"], 2)

    return jsonify(
        {
            "total_transactions": coll.count_documents({}),
            "towns": len(coll.distinct("town")),
            "by_flat_type": by_type,
        }
    )


@app.route("/health", methods=["GET"])
def health():
    from config import get_redis

    checks = {}
    try:
        get_db().command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        checks["mongodb"] = f"down: {exc}"
    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"down: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return jsonify(checks), (200 if healthy else 503)


if __name__ == "__main__":
    print(f"Serving on http://localhost:{API_PORT}")
    app.run(port=API_PORT, debug=True)
