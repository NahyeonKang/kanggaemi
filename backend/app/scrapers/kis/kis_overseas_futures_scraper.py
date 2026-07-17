"""
app/scrapers/kis/kis_overseas_futures_scraper.py

KIS 해외선물 체결추이(일간) [해외선물-018] 스크래퍼 — 시세 도메인.
국내 kis_chart_scraper와 request가 완전히 달라 분리(인증만 공유).

  - daily-ccnl HHDFC55020100 (/uapi/overseas-futureoption/v1/quotations/daily-ccnl)
  - request: SRS_CD(종목) + EXCH_CD(거래소) + CLOSE_DATE_TIME + QRY_TP(Q/P) + INDEX_KEY
  - 페이징: tr_cont 불가. QRY_TP=Q 최초조회 → output1.index_key로 QRY_TP=P 연속조회.
            한 콜 최대 40건(QRY_CNT), 과거 방향으로 페이징.
  - output2: data_date, open_price, high_price, low_price, last_price(종가), vol(누적거래량).
             거래대금(amount) 없음. output1은 페이징 메타(index_key)뿐 → 스냅샷 없음.

★ 소수점 보정(sCalcDesz): 원시 시세는 해외선물종목마스터(ffcode.mst)의 sCalcDesz만큼
  소수점 이동이 필요함. 예) 품목 6A sCalcDesz=-4 → 6882.5 수신 → 0.68825.
  calc_decimal(=sCalcDesz)을 주입하면 raw × 10^calc_decimal 로 보정. 미지정 시 raw 저장.
  ※ feed 자체가 일부 행은 이미 보정, 일부는 미보정으로 섞여 올 수 있음(내부 불일치).
     일괄 보정이 특정 행을 오히려 틀리게 할 수 있어, 마스터 기준으로 심볼별 검증 권장.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.instrument_price import OhlcvObservation, ChartResult
from app.scrapers.kis.kis_auth import KISAuthClient, smart_sleep

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_PATH = "/uapi/overseas-futureoption/v1/quotations/daily-ccnl"
_TR_ID = "HHDFC55020100"
_MAX_QRY_CNT = 40
_MAX_PAGES = 25

# output2 필드맵
_OHLCV_MAP = {
    "open": "open_price", "high": "high_price", "low": "low_price",
    "close": "last_price", "volume": "vol",   # amount 없음
}


class KISOverseasFuturesScraper:
    """Fetches overseas-futures daily OHLCV (체결추이 일간) from KIS."""

    def __init__(self, auth_client: Optional[KISAuthClient] = None) -> None:
        self._auth = auth_client or KISAuthClient()

    def fetch_daily_ohlcv(
        self,
        exch_cd: str,                      # 거래소코드 예: CME
        srs_cd: str,                       # 종목코드 예: 6AM24
        close_date: str,                   # 조회종료일 YYYYMMDD
        qry_cnt: int = _MAX_QRY_CNT,
        calc_decimal: Optional[int] = None,  # sCalcDesz(마스터). None이면 raw 저장
        currency: Optional[str] = None,      # 상품 통화(마스터). None 허용
        max_pages: int = _MAX_PAGES,
    ) -> ChartResult:
        qry_cnt = min(qry_cnt, _MAX_QRY_CNT)
        entity_code = f"{exch_cd}:{srs_cd}"

        rows: list = []
        qry_tp = "Q"
        index_key = ""
        seen_keys: set[str] = set()

        for page in range(max_pages):
            params = {
                "SRS_CD": srs_cd,
                "EXCH_CD": exch_cd,
                "START_DATE_TIME": "",
                "CLOSE_DATE_TIME": close_date,
                "QRY_TP": qry_tp,
                "QRY_CNT": str(qry_cnt),
                "QRY_GAP": "",
                "INDEX_KEY": index_key,
            }
            res = self._auth.url_fetch(_PATH, _TR_ID, "", params)
            if not res.isOK():
                res.printError(_PATH)
                raise ValueError(
                    f"KIS overseas-futures call failed ({entity_code}): "
                    f"{res.getErrorCode()} - {res.getErrorMessage()}"
                )

            body = res.getBody()
            batch = _as_list(getattr(body, "output2", None))
            rows.extend(batch)

            # 페이징: output1.index_key로 QRY_TP=P 연속조회(과거 방향)
            next_key = _get(getattr(body, "output1", None), "index_key")
            if len(batch) < qry_cnt:
                break                       # 마지막 배치
            if not next_key or next_key in seen_keys:
                break                       # 키 정지/반복 → 종료
            seen_keys.add(next_key)
            index_key = next_key
            qry_tp = "P"
            smart_sleep()

        observations = _flatten(rows, calc_decimal)

        return ChartResult(
            source="kis",
            asset_class="os_future",
            entity_code=entity_code,
            resolution="D",
            observed_at=datetime.now(_KST),
            currency=currency,
            observations=observations,
        )


# ── parsing ──────────────────────────────────────────────────
def _flatten(rows: list, calc_decimal: Optional[int]) -> list[OhlcvObservation]:
    obs: list[OhlcvObservation] = []
    seen_dates: set[str] = set()
    factor = (Decimal(10) ** calc_decimal) if calc_decimal is not None else None
    for row in rows:
        raw_date = _get(row, "data_date")
        if not raw_date:
            continue
        d = _fmt_date(str(raw_date).strip())
        if d in seen_dates:                 # 페이징 경계 중복 제거
            continue
        seen_dates.add(d)
        obs.append(
            OhlcvObservation(
                observation_date=d,
                open=_adj(_get(row, _OHLCV_MAP["open"]), factor),
                high=_adj(_get(row, _OHLCV_MAP["high"]), factor),
                low=_adj(_get(row, _OHLCV_MAP["low"]), factor),
                close=_adj(_get(row, _OHLCV_MAP["close"]), factor),
                volume=_to_decimal(_get(row, _OHLCV_MAP["volume"])),  # 수량은 미보정
                amount=None,                # 해외선물 daily-ccnl에 거래대금 없음
            )
        )
    return obs


def _adj(value: object, factor: Optional[Decimal]) -> Optional[Decimal]:
    """가격에 sCalcDesz 보정(factor=10^sCalcDesz) 적용. factor None이면 raw."""
    dec = _to_decimal(value)
    if dec is None or factor is None:
        return dec
    return dec * factor


# ── helpers ──────────────────────────────────────────────────
def _get(obj: object, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_list(raw: object) -> list:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _fmt_date(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None