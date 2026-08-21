"""A Streamlit dashboard - just one more consumer of our own API.

Same idea as consume_own_api.py: requests.get against our Step 3 API. The
only difference is that the results render as a page instead of print().
Nothing here touches Mongo or Redis directly - the API already does that.

The "Use Redis cache" toggle is the Step 4 lesson made visible: flip it and
watch the same answer arrive in a fraction of the time.

NEW TO STREAMLIT? The one thing to understand:

    This file is an ordinary top-to-bottom Python script. Streamlit runs the
    WHOLE thing again, from line 1, every time you touch any widget.

    So there is no callback, no event handler, no update() to write. You pick
    a different town from the dropdown, the script re-runs, and this time
    `town` holds the new value. Every `st.something(...)` call paints one
    element onto the page in the order it executes.

    That is it. The rest is just plain Python and requests.get().
"""
import pandas as pd
import requests
import streamlit as st

from config import API_PORT

BASE = f"http://localhost:{API_PORT}"

# set_page_config must be the first Streamlit call on the page.
st.set_page_config(page_title="HDB Resale Pipeline", layout="wide")
st.title("HDB Resale Pipeline")           # big heading
st.caption(f"Every number on this page came from our own API at {BASE}")


def get(path, **params):
    """One GET against our API. Stops the page with a hint if it's not up.

    st.stop() halts the script right here, so the rest of the page never
    renders - better than showing half a dashboard full of errors.
    """
    try:
        return requests.get(f"{BASE}{path}", params=params, timeout=60).json()
    except requests.exceptions.RequestException:
        st.error(f"Could not reach {BASE} - is `./run.sh api` running?")
        st.stop()


towns = get("/towns")
if not towns:
    st.warning("No data loaded. Run `./run.sh pipeline` first.")
    st.stop()

# --- Step 4 made visible ---------------------------------------------------
st.subheader("Town summary")

# st.columns splits the page into side-by-side areas. The [2, 1] means the
# left one is twice as wide. Calling left.selectbox() instead of
# st.selectbox() puts that widget inside that column.
left, right = st.columns([2, 1])

# Widgets RETURN the user's current choice. On the first run that is the
# first town in the list; after someone picks another, the script re-runs
# and `town` is whatever they picked.
town = left.selectbox("Town", towns)
use_cache = right.toggle("Use Redis cache", value=False,
                         help="Off: aggregate in MongoDB every time. On: Redis.")

# Our own API does the work. The toggle just changes one query parameter -
# which is the whole point: same request, same answer, different cost.
summary = get(f"/towns/{town}", cache="true" if use_cache else "false")

# st.metric draws one big number with a label. Four columns, four numbers.
c1, c2, c3, c4 = st.columns(4)
c1.metric("Transactions", f"{summary.get('transactions', 0):,}")
c2.metric("Average price", f"${summary.get('avg_price', 0):,.0f}")
c3.metric("Avg per sqm", f"${summary.get('avg_price_per_sqm', 0):,.0f}")
c4.metric("Time to answer", f"{summary.get('elapsed_ms', 0):,.1f} ms",
          help="Toggle the cache and watch this number.")
st.caption(f"Served from **{summary.get('source', 'unknown')}**. "
           "Same answer either way - only the cost changed.")

# --- The transactions themselves -------------------------------------------
st.subheader("Transactions")

# Build the dropdown options out of whatever the API reports, so this page
# never hardcodes a list that could drift from the data.
flat_types = ["All"] + sorted({r["_id"] for r in get("/stats")["by_flat_type"]})
flat_type = st.selectbox("Flat type", flat_types)

# The filtering happens in MongoDB, not here. We pass the user's choice
# through as query params and let the API (and its index) do the work -
# pulling everything back and filtering in pandas would defeat the point.
params = {"town": town, "limit": 500}
if flat_type != "All":
    params["flat_type"] = flat_type

flats = pd.DataFrame(get("/flats", **params))
st.write(f"{len(flats):,} rows (capped at 500)")
st.dataframe(flats, width="stretch")      # scrollable, sortable table

# --- Dataset-level summary -------------------------------------------------
stats = get("/stats")
st.subheader("Average price by flat type")
st.caption(f"{stats['total_transactions']:,} transactions across {stats['towns']} towns")

# st.bar_chart takes a DataFrame and charts it: the index becomes the x-axis
# labels (flat type) and the column becomes the bar heights (avg price).
st.bar_chart(pd.DataFrame(stats["by_flat_type"]).set_index("_id")["avg_price"])
