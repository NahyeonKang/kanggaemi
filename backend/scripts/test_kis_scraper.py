import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from app.scrapers.kis.kis_scraper import KISScraper

scraper = KISScraper()

result = scraper.fetch_comp_interest(
    fid_cond_mrkt_div_code="I",
    fid_cond_scr_div_code="20702",
    fid_div_cls_code="1",
    fid_div_cls_code1="",
)

print(f"source       : {result.source}")
print(f"fetched_at   : {result.fetched_at}")
print(f"output1      : {len(result.output1)} entries")

print("\n--- output1 ---")
for item in result.output1:
    print(f"  [{item.bcdt_code}] [{item.stck_bsop_date}] {item.hts_kor_isnm:<20}  rate={item.bond_mnrt_prpr}")
