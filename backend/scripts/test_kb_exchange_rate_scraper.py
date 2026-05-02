import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scrapers.exchange_rate.kb_exchange_rate_scraper import KBExchangeRateScraper

scraper = KBExchangeRateScraper()

# fetch a specific past date to ensure data exists
result = scraper.fetch_usdkrw(search_date="20260313")

print(f"target_date  : {result.target_date}")
print(f"fetched_at   : {result.fetched_at}")
print(f"quotes       : {len(result.quotes)} entries")
for q in result.quotes[:5]:
    print(f"  {q.quote_time}  {q.base_rate:,.2f}")
