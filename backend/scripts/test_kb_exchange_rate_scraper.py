import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scrapers.exchange_rate.kb_exchange_rate_scraper import KBExchangeRateScraper

scraper = KBExchangeRateScraper()

# ── 1. 장중 시세 요약 (조회기준=1) ──────────────────────────
print("=" * 50)
print("Intraday summary")
print("=" * 50)
summary = scraper.fetch_usdkrw_summary(search_date="20260612")
print(f"target_date  : {summary.target_date}")
print(f"fetched_at   : {summary.fetched_at}")
print(f"first_rate   : {summary.first_rate:,.2f}")   # 최초 회차
print(f"last_rate    : {summary.last_rate:,.2f}")    # 최종 회차
print(f"daily_low    : {summary.daily_low:,.2f}")    # 일최저
print(f"daily_high   : {summary.daily_high:,.2f}")   # 일최고
print(f"daily_avg    : {summary.daily_avg:,.2f}")    # 일평균

# ── 2. 일별 종가 시계열 (조회기준=2) ────────────────────────
print("\n" + "=" * 50)
print("Daily series (1 year)")
print("=" * 50)
series = scraper.fetch_usdkrw_range(start_date="20250614", end_date="20260614")
print(f"start_date   : {series.start_date}")
print(f"end_date     : {series.end_date}")
print(f"fetched_at   : {series.fetched_at}")
print(f"quotes       : {len(series.quotes)} entries")
for q in series.quotes[:5]:
    print(f"  {q.quote_date}  {q.base_rate:,.2f}")