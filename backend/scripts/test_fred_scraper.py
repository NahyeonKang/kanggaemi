import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scrapers.fred.fred_scraper import FredScraper

scraper = FredScraper()

for series_id in ["SOFR", "DGS30", "DFII10", "NASDAQSOX", "VIXCLS"]:
    result = scraper.fetch_last_1y_series(series_id)

    print(f"\n{'=' * 40}")
    print(f"series_id    : {result.series_id}")
    print(f"fetched_at   : {result.fetched_at}")
    print(f"observations : {len(result.observations)} entries")
    print("  --- first 5 ---")
    for obs in result.observations[:5]:
        print(f"  {obs.observation_date}  {obs.value}")
    print("  --- last 5 ---")
    for obs in result.observations[-5:]:
        print(f"  {obs.observation_date}  {obs.value}")
