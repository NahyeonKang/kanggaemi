from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import yaml

from app.agent.assets import AssetResolver, AssetTaxonomyRegistry
from app.agent.contracts import AssetExtraction, Evidence, FactorFeature, SelectedFactor
from app.agent.feature_engine import FeatureEngine, SeriesPoint, apply_transform
from app.agent.nodes import make_analyzer, plan_node
from app.scrapers.kis.domestic_stock_master import _SPECS, parse_domestic_stock_mst


class FakeExtractor:
    def __init__(self, name="삼성전자"):
        self.name = name

    def extract(self, _query):
        return AssetExtraction(
            asset_name=self.name, asset_class="kr_equity", horizon="3M",
            query_intent="general_outlook", aliases=[self.name], confidence=0.9,
        )


def test_stock_master_fixed_width_parser_matches_attached_contract(tmp_path):
    spec = _SPECS["KOSPI"]
    values = [""] * len(spec["widths"])
    values[2], values[3], values[4] = "0010", "0020", "0030"
    values[spec["listing_idx"]] = "19750611"
    values[spec["preferred_idx"]] = "0"
    tail = "".join(value.ljust(width)[:width] for value, width in zip(values, spec["widths"]))
    prefix = "005930".ljust(9) + "KR7005930003".ljust(12) + "삼성전자"
    path = tmp_path / "kospi_code.mst"
    path.write_text(prefix + tail + "\n", encoding="cp949")
    items = parse_domestic_stock_mst(path, "KOSPI")
    assert len(items) == 1
    assert items[0].ticker == "005930"
    assert items[0].name == "삼성전자"
    assert items[0].sector_large_code == "0010"
    assert items[0].listing_date == "19750611"


def test_transform_interface_supports_required_methods():
    points = [
        SeriesPoint(f"2025-01-0{index}", float(index), "test")
        for index in range(1, 6)
    ]
    assert apply_transform(points, {"method": "rolling_sum", "window": "5D"}) == 15
    assert apply_transform(points, {"method": "z_score", "window": "5D"}) == pytest.approx(1.41421356)
    yoy = [
        SeriesPoint("2025-01-01", 100, "test"),
        SeriesPoint("2026-01-02", 120, "test"),
    ]
    assert apply_transform(yoy, {"method": "yoy_growth", "window": "1Y"}) == 20


def test_classify_cache_hit_uses_registry_code_not_llm_code(tmp_path):
    path = tmp_path / "asset_taxonomy.yaml"
    path.write_text(yaml.safe_dump({"assets": [{
        "asset_code": "005930", "asset_name": "삼성전자", "asset_class": "kr_equity",
        "region": "kr", "market": "KOSPI", "sector": "반도체",
        "aliases": ["삼성전자", "삼전"], "status": "active",
    }]}, allow_unicode=True), encoding="utf-8")
    resolver = AssetResolver(FakeExtractor(), registry=AssetTaxonomyRegistry(path))
    result = resolver.resolve(None, "삼성전자 전망")
    assert result.asset_code == "005930"
    assert result.cache_hit is True
    assert result.applicable_dimensions == ["macro", "flow", "industry", "valuation"]


def test_classify_cache_miss_grounds_and_appends_master_result(tmp_path):
    path = tmp_path / "asset_taxonomy.yaml"
    path.write_text("assets: []\n", encoding="utf-8")

    class FakeMaster:
        def find_candidates(self, _db, name):
            assert name == "테스트전자"
            return [SimpleNamespace(
                ticker="123456", name="테스트전자", market="KOSDAQ",
                sector_large_code="0010",
            )]

    resolver = AssetResolver(
        FakeExtractor("테스트전자"), registry=AssetTaxonomyRegistry(path),
        master_repository=FakeMaster(),
    )
    result = resolver.resolve(object(), "테스트전자 분석")
    assert result.asset_code == "123456"
    assert result.cache_hit is False
    assert AssetTaxonomyRegistry(path).find("123456")["market"] == "KOSDAQ"


def test_plan_selects_only_active_flow_factors_for_equity():
    update = plan_node({"classification": {
        "asset_class": "kr_equity",
        "applicable_dimensions": ["macro", "flow", "industry", "valuation"],
    }})
    assert {
        factor["factor_id"] for factor in update["selected_factors"]
        if factor["dimension"] == "flow"
    } == {
        "FLOW_FOREIGN_SPOT", "FLOW_INSTITUTION_SPOT",
        "FLOW_INDIVIDUAL_SPOT", "PROGRAM_NET",
    }
    assert "SHORT_BALANCE" not in update["execution_plan"]["flow_node"]


def test_plan_expands_active_dimensions_and_singular_financial_spec():
    update = plan_node({"classification": {
        "asset_class": "kr_equity",
        "applicable_dimensions": ["macro", "flow", "industry", "valuation"],
    }})
    dimensions = {factor["dimension"] for factor in update["selected_factors"]}
    valuation_ids = {
        factor["factor_id"] for factor in update["selected_factors"]
        if factor["dimension"] == "valuation"
    }
    assert dimensions == {"macro", "flow", "industry", "valuation"}
    assert "VAL_REVENUE_GROWTH" in valuation_ids
    assert "VAL_OP_MARGIN" in valuation_ids


def test_feature_engine_enforces_as_of_and_evidence_contract(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.agent.feature_engine as module
    from app.models.investor_flow import InvestorFlowDailyModel

    engine = create_engine("sqlite:///:memory:")
    InvestorFlowDailyModel.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    with Session() as db:
        db.add_all([
            InvestorFlowDailyModel(
                id=index, source="kis", scope="stock", market="KOSPI",
                entity_code="005930", investor_type="frgn",
                observation_date=f"2026-07-{10 + index:02d}", net_amount=index,
                ingested_at=now,
            ) for index in range(1, 6)
        ] + [InvestorFlowDailyModel(
            id=99, source="kis", scope="stock", market="KOSPI",
            entity_code="005930", investor_type="frgn",
            observation_date="2026-07-20", net_amount=999, ingested_at=now,
        )])
        db.commit()
    monkeypatch.setattr(module, "SessionLocal", Session)
    feature = FeatureEngine(fetcher=SimpleNamespace(fetch_stock_bundle=lambda *_: []))
    result = feature.compute_factor(
        SelectedFactor(
            factor_id="FLOW_FOREIGN_SPOT", factor_name="외국인 순매수",
            dimension="flow", data_spec_id="DS_KR_MARKET_INVESTOR_FLOW",
            transform={"method": "rolling_sum", "window": "5D"},
            interpretation={}, caveats=[],
        ),
        {"asset_class": "kr_equity", "asset_code": "005930", "market": "KOSPI"},
        "2026-07-15",
    )
    assert result.evidence.value == 15
    assert result.evidence.observation_date == "2026-07-15"
    assert result.evidence.as_of_date == "2026-07-15"
    assert result.evidence.data_spec_id == "DS_KR_EQUITY_INVESTOR_FLOW"


def test_index_futures_factor_uses_grounded_contract_evidence(monkeypatch):
    feature = FeatureEngine(fetcher=SimpleNamespace(fetch_stock_bundle=lambda *_: []))
    monkeypatch.setattr(
        feature, "_read_points",
        lambda *_: [SeriesPoint("2026-07-16", 0.35, "kis", "A01609")],
    )
    result = feature.compute_factor(
        SelectedFactor(
            factor_id="FUTURES_BASIS_DISPARITY", factor_name="선물 괴리율",
            dimension="flow", data_spec_id="DS_KR_INDEX_FUTURES_BASIS",
            transform={"method": "level", "window": None},
            interpretation={}, caveats=[],
        ),
        {"asset_class": "kr_index", "asset_code": "0001", "market": "KOSPI"},
        "2026-07-16",
    )
    assert result.evidence is not None
    assert result.evidence.entity_code == "A01609"
    assert result.evidence.field == "disparity"


def test_missing_flow_adapter_does_not_abort_graph():
    feature = FeatureEngine(fetcher=SimpleNamespace(fetch_stock_bundle=lambda *_: []))
    result = feature.compute_factor(
        SelectedFactor(
            factor_id="UNIMPLEMENTED_ACTIVE_FACTOR", factor_name="미구현 팩터",
            dimension="flow", data_spec_id="DS_KR_INDEX_FUTURES_BASIS",
            transform={"method": "level"}, interpretation={}, caveats=[],
        ),
        {"asset_class": "kr_index", "asset_code": "0001", "market": "KOSPI"},
        "2026-07-16",
    )
    assert result.evidence is None
    assert "adapter missing" in result.missing_reason


def test_factory_flow_analyzer_writes_only_flow_state_key():
    class FakeEngine:
        def compute_factor(self, factor, classification, as_of):
            return FactorFeature(
                factor_id=factor.factor_id, factor_name=factor.factor_name,
                signal="positive", strength=0.5,
                evidence=Evidence(
                    data_spec_id="DS_KR_EQUITY_INVESTOR_FLOW", source="kis",
                    entity_code=classification["asset_code"], field="net_amount",
                    value=10, unit="KRW_million", observation_date=as_of,
                    as_of_date=as_of,
                    transform={"method": "rolling_sum", "window": "5D"},
                    is_estimated=True, caveats=[],
                ),
            )

    factor = SelectedFactor(
        factor_id="FLOW_FOREIGN_SPOT", factor_name="외국인 순매수",
        dimension="flow", data_spec_id="DS_KR_MARKET_INVESTOR_FLOW",
        transform={"method": "rolling_sum", "window": "5D"},
        interpretation={}, caveats=[],
    )
    node = make_analyzer("flow", FakeEngine())
    update = node({
        "classification": {"asset_code": "005930", "asset_name": "삼성전자"},
        "selected_factors": [factor.model_dump()], "as_of_date": "2026-07-17",
    })
    assert set(update) == {"flow_result"}
    assert update["flow_result"]["key_evidence"][0]["data_spec_id"] == "DS_KR_EQUITY_INVESTOR_FLOW"


def test_single_stock_langgraph_end_to_end_slice():
    pytest.importorskip("langgraph")
    from app.agent.contracts import ClassificationResult
    from app.agent.graph import build_flow_slice_graph

    class FakeResolver:
        def resolve(self, _db, _query):
            return ClassificationResult(
                asset_code="005930", asset_name="삼성전자", asset_class="kr_equity",
                region="kr", market="KOSPI", sector="반도체", currency="KRW",
                aliases=["삼성전자"], horizon="3M", query_intent="general_outlook",
                applicable_dimensions=["macro", "flow", "industry", "valuation"],
                classification_confidence=1.0, cache_hit=True,
            )

    class FakeEngine:
        def compute_factor(self, factor, classification, as_of):
            return FactorFeature(
                factor_id=factor.factor_id, factor_name=factor.factor_name,
                signal="positive", strength=0.5,
                evidence=Evidence(
                    data_spec_id="DS_KR_EQUITY_INVESTOR_FLOW", source="kis",
                    entity_code=classification["asset_code"], field="net_amount",
                    value=10, unit="KRW_million", observation_date=as_of,
                    as_of_date=as_of,
                    transform=factor.transform, is_estimated=True, caveats=[],
                ),
            )

    graph = build_flow_slice_graph(FakeResolver(), FakeEngine())
    result = graph.invoke({
        "run_id": "test-run", "user_query": "삼성전자 수급 전망",
        "as_of_date": "2026-07-17", "locale": "ko-KR",
    })
    assert result["classification"]["asset_code"] == "005930"
    assert result["flow_result"]["dimension"] == "flow"
    assert "DS_KR_EQUITY_INVESTOR_FLOW" in result["simple_output"]
