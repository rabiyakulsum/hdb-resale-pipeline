"""A Streamlit dashboard - just one more consumer of our own API.

Same idea as consume_own_api.py: requests.get against our Step 3 API. The
only difference is that the results render as a page instead of print().
Nothing here touches Mongo or Redis directly - the API already does that.

The "Use Redis cache" toggle is the Step 4 lesson made visible: flip it and
watch the same answer arrive in a fraction of the time.
"""
import pandas as pd
import requests
import streamlit as st

from config import API_PORT

BASE = f"http://localhost:{API_PORT}"

st.set_page_config(page_title="HDB Resale Pipeline", layout="wide")
st.title("HDB Resale Pipeline")
st.caption(f"Every number on this page came from our own API at {BASE}")


def get(path, **params):
    """One GET against our API. Stops the page with a hint if it's not up."""
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
left, right = st.columns([2, 1])
town = left.selectbox("Town", towns)
use_cache = right.toggle("Use Redis cache", value=False,
                         help="Off: aggregate in MongoDB every time. On: Redis.")

summary = get(f"/towns/{town}", cache="true" if use_cache else "false")

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
flat_types = ["All"] + sorted({r["_id"] for r in get("/stats")["by_flat_type"]})
flat_type = st.selectbox("Flat type", flat_types)

params = {"town": town, "limit": 500}
if flat_type != "All":
    params["flat_type"] = flat_type

flats = pd.DataFrame(get("/flats", **params))
st.write(f"{len(flats):,} rows (capped at 500)")
st.dataframe(flats, width="stretch")

# --- Dataset-level summary -------------------------------------------------
stats = get("/stats")
st.subheader("Average price by flat type")
st.caption(f"{stats['total_transactions']:,} transactions across {stats['towns']} towns")
st.bar_chart(pd.DataFrame(stats["by_flat_type"]).set_index("_id")["avg_price"])
