def test_fetch_market_data_returns_200(client):
    response = client.post(
        "/api/v1/market-data/fetch",
        json={"symbol": "005930", "market": "KRX"},
    )
    assert response.status_code == 200


def test_fetch_market_data_schema(client):
    response = client.post(
        "/api/v1/market-data/fetch",
        json={
            "symbol": "005930",
            "market": "KRX",
            "include_intraday": True,
            "include_investor_flow": True,
            "include_program_trading": False,
            "include_derivatives": True,
        },
    )
    data = response.json()
    assert data["symbol"] == "005930"
    assert data["market"] == "KRX"
    assert isinstance(data["price_series"], list)
    assert isinstance(data["investor_flows"], list)
    assert len(data["price_series"]) > 0


def test_fetch_market_data_ohlcv_fields(client):
    response = client.post(
        "/api/v1/market-data/fetch",
        json={"symbol": "005930"},
    )
    item = response.json()["price_series"][0]
    for field in ("timestamp", "open", "high", "low", "close", "volume"):
        assert field in item


def test_fetch_market_data_investor_flow_fields(client):
    response = client.post(
        "/api/v1/market-data/fetch",
        json={"symbol": "005930", "include_investor_flow": True},
    )
    flow = response.json()["investor_flows"][0]
    for field in ("date", "individual", "foreigner", "institution"):
        assert field in flow


def test_fetch_market_data_missing_symbol_returns_422(client):
    response = client.post("/api/v1/market-data/fetch", json={})
    assert response.status_code == 422
