import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from app.scrapers.bok.bok_bond_rate_scraper import BOKBondRateScraper

scraper = BOKBondRateScraper()

result = scraper.fetch_last_1y_treasury_10y()

print(f"source       : {result.source}")
print(f"item_code    : {result.item_code}")
print(f"fetched_at   : {result.fetched_at}")
print(f"items        : {len(result.items)} entries")

print("\n--- first 5 ---")
for item in result.items[:5]:
    print(f"  [{item.observation_date}] {item.item_name:<20}  value={item.value}")

print("\n--- last 5 ---")
for item in result.items[-5:]:
    print(f"  [{item.observation_date}] {item.item_name:<20}  value={item.value}")
