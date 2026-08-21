"""Run the lifecycle end to end.

    EXTRACT -> STORE -> (serve) -> CACHE

Steps 1, 2 and 4 run here. Step 3 (the API) and the dashboard are servers,
so they get their own terminals - see run.sh.
"""
import sys

from config import MONGO_COLLECTION, N_RECORDS


def banner(step, title):
    print(f"\n{'=' * 62}\n  STEP {step} - {title}\n{'=' * 62}")


def main(n=N_RECORDS, refetch=False):
    banner(1, "Extract: page a real dataset out of data.gov.sg")
    from config import RAW_CSV
    from step1_extract import extract, read_local

    if RAW_CSV.exists() and not refetch:
        df = read_local()
        print(f"{RAW_CSV.name} already landed - reusing it "
              f"({len(df):,} rows). --extract to re-pull.")
    else:
        df = extract(n)
    print(f"shape: {df.shape}")
    print(f"towns: {df['town'].nunique()}  flat types: {df['flat_type'].nunique()}")

    banner(2, "Load into MongoDB (system of record)")
    from step2_load_mongo import list_towns, load_flats, town_summary

    count = load_flats(df)
    print(f"{count:,} documents in {MONGO_COLLECTION}, {len(list_towns())} towns")

    banner(3, "Serve it back out (run this one yourself)")
    print("The API is a server, so it needs its own terminal:")
    print("    ./run.sh api          then  ./run.sh dashboard")
    print("\nUncached town summary, straight from MongoDB:")
    print(f"  {town_summary(list_towns()[0])}")

    banner(4, "Cache with Redis (the speed layer)")
    from step4_cache_redis import demo, demo_overview

    demo_overview()
    print()
    for town in list_towns()[:1]:
        print(f"{town}:")
        demo(town)

    print("\nPipeline complete.")


if __name__ == "__main__":
    rows = N_RECORDS
    if "--rows" in sys.argv:
        rows = int(sys.argv[sys.argv.index("--rows") + 1])
    main(n=rows, refetch="--extract" in sys.argv)
