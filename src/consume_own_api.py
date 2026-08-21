"""The 'aha' exercise: extract from YOUR OWN pipeline.

This is Step 1's code shape pointed at localhost instead of data.gov.sg.
Student A runs step3_api.py; Student B runs this. Extraction isn't a
one-time step - it's a role any system can play.
"""
import requests

from config import API_PORT

BASE = f"http://localhost:{API_PORT}"


def main():
    try:
        # Exactly the shape of Step 1 - only the URL changed.
        resp = requests.get(f"{BASE}/flats", params={"limit": 3}, timeout=10)
        print(f"GET {resp.url} -> {resp.status_code}")
        for flat in resp.json():
            print(f"  #{flat['flat_id']:>6} {flat['town']:<16} {flat['flat_type']:<11} "
                  f"${flat['resale_price']:>10,.0f}")

        town = requests.get(f"{BASE}/towns", timeout=10).json()[0]

        slow = requests.get(f"{BASE}/towns/{town}", timeout=30).json()
        fast = requests.get(f"{BASE}/towns/{town}", params={"cache": "true"},
                            timeout=30).json()
        print(f"\nGET /towns/{town}")
        print(f"  no cache: {slow['elapsed_ms']:>8.2f} ms  ({slow.get('source')})")
        print(f"  cached:   {fast['elapsed_ms']:>8.2f} ms  ({fast.get('source')})")

        stats = requests.get(f"{BASE}/stats", timeout=30).json()
        print(f"\nGET {BASE}/stats")
        print(f"  {stats['total_transactions']:,} transactions across "
              f"{stats['towns']} towns")
        for row in stats["by_flat_type"]:
            print(f"  {row['_id']:<11} {row['transactions']:>6,} sales  "
                  f"avg ${row['avg_price']:>10,.0f}")
    except requests.exceptions.RequestException as exc:
        print(f"Could not reach {BASE} - is step3_api.py running?\n  {exc}")


if __name__ == "__main__":
    main()
