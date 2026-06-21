import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from app.scrapers.bok.bok_scraper import BOKScraper

scraper = BOKScraper()

# 817Y002 / D / 010210000 = 금리 종합, 일별, 국고채(10년) — used by yield_daily ('KR', '10Y')
result = scraper.fetch_last_1y_series(stat_code="817Y002", item_code="010901000")

print(f"source       : {result.source}")
print(f"stat_code    : {result.stat_code}")
print(f"item_code    : {result.item_code}")
print(f"fetched_at   : {result.fetched_at}")
print(f"observations : {len(result.observations)} entries")

print("\n--- first 5 ---")
for obs in result.observations[:5]:
    print(f"  [{obs.observation_date}] value={obs.value}")

print("\n--- last 5 ---")
for obs in result.observations[-5:]:
    print(f"  [{obs.observation_date}] value={obs.value}")
