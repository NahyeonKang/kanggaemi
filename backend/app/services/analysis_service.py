from app.clients.llm_client import LLMClient
from app.schemas.analysis import AnalysisRequest, AnalysisResponse, KeyPoint
from app.schemas.market_data import MarketDataRequest, MarketDataResponse
from app.services.market_data_service import MarketDataService


class AnalysisService:
    def __init__(self):
        self.market_data_service = MarketDataService()
        self.llm_client = LLMClient()

    def generate_analysis(self, req: AnalysisRequest) -> AnalysisResponse:
        market_data = self.market_data_service.get_market_data(
            MarketDataRequest(
                symbol=req.symbol,
                market=req.market,
                include_intraday=True,
                include_investor_flow=True,
                include_program_trading=True,
                include_derivatives=True,
            )
        )

        prompt = self._build_prompt(req, market_data)
        llm_result = self.llm_client.generate_report(prompt)

        return AnalysisResponse(
            symbol=req.symbol,
            summary=llm_result.get("summary", ""),
            key_points=[KeyPoint(**kp) for kp in llm_result.get("key_points", [])],
            risks=llm_result.get("risks", []),
            outlook=llm_result.get("outlook", ""),
            raw_prompt=prompt,
        )

    def _build_prompt(self, req: AnalysisRequest, market_data: MarketDataResponse) -> str:
        price_lines = "\n".join(
            f"  {item.timestamp} | O:{item.open} H:{item.high} L:{item.low} C:{item.close} V:{item.volume:,.0f}"
            for item in market_data.price_series
        )

        flow_lines = "\n".join(
            (
                f"  {item.date} | 개인:{item.individual:+.1f}억 외국인:{item.foreigner:+.1f}억 "
                f"기관:{item.institution:+.1f}억 금투:{item.financial_investment:+.1f}억"
                if item.financial_investment is not None
                else f"  {item.date} | 개인:{item.individual:+.1f}억 외국인:{item.foreigner:+.1f}억 기관:{item.institution:+.1f}억"
            )
            for item in market_data.investor_flows
        )

        derivatives_section = "없음"
        if market_data.derivatives:
            d = market_data.derivatives
            derivatives_section = (
                f"미결제약정:{d.open_interest}, 선물순포지션:{d.futures_net_position}, 베이시스:{d.basis}"
            )

        user_note = f"\n[추가 지시사항]\n{req.user_prompt}" if req.user_prompt else ""

        return f"""
종목: {market_data.symbol} ({market_data.market})
리포트 유형: {req.report_type}
분석 톤: {req.tone}

[가격 데이터 (OHLCV)]
{price_lines if price_lines else "데이터 없음"}

[수급 데이터 (억원)]
{flow_lines if flow_lines else "데이터 없음"}

[파생 데이터]
{derivatives_section}
{user_note}
        """.strip()
