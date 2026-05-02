import pytest

from app.clients.llm_client import LLMClient

MOCK_LLM_RESULT = {
    "summary": "외국인 순매도가 이어지며 단기 약세 압력이 우세합니다.",
    "key_points": [
        {"title": "수급 포인트", "description": "외국인 선물 순매도 지속"},
        {"title": "파생 포인트", "description": "베이시스 마이너스 유지"},
    ],
    "risks": ["장중 변동성 확대", "수급 왜곡"],
    "outlook": "단기 중립~약세 시나리오 우세",
}


@pytest.fixture(autouse=True)
def patch_llm(monkeypatch):
    monkeypatch.setattr(LLMClient, "__init__", lambda self: None)
    monkeypatch.setattr(LLMClient, "generate_report", lambda self, prompt: MOCK_LLM_RESULT)


def test_generate_analysis_returns_200(client):
    response = client.post(
        "/api/v1/analysis/generate",
        json={"symbol": "005930", "market": "KRX"},
    )
    assert response.status_code == 200


def test_generate_analysis_schema(client):
    response = client.post(
        "/api/v1/analysis/generate",
        json={"symbol": "005930", "market": "KRX", "report_type": "daily", "tone": "professional"},
    )
    data = response.json()
    assert data["symbol"] == "005930"
    assert isinstance(data["summary"], str) and len(data["summary"]) > 0
    assert isinstance(data["key_points"], list) and len(data["key_points"]) > 0
    assert isinstance(data["risks"], list) and len(data["risks"]) > 0
    assert isinstance(data["outlook"], str) and len(data["outlook"]) > 0


def test_generate_analysis_key_points_structure(client):
    response = client.post(
        "/api/v1/analysis/generate",
        json={"symbol": "005930"},
    )
    for kp in response.json()["key_points"]:
        assert "title" in kp
        assert "description" in kp


def test_generate_analysis_prompt_contains_symbol(client):
    captured = {}

    def capturing_generate(self, prompt):
        captured["prompt"] = prompt
        return MOCK_LLM_RESULT

    import app.clients.llm_client as llm_module
    original = LLMClient.generate_report
    LLMClient.generate_report = capturing_generate
    try:
        client.post("/api/v1/analysis/generate", json={"symbol": "005930"})
        assert "005930" in captured.get("prompt", "")
    finally:
        LLMClient.generate_report = original


def test_generate_analysis_missing_symbol_returns_422(client):
    response = client.post("/api/v1/analysis/generate", json={})
    assert response.status_code == 422


def test_generate_analysis_with_user_prompt(client):
    response = client.post(
        "/api/v1/analysis/generate",
        json={"symbol": "005930", "user_prompt": "단기 매매 관점에서 분석해주세요"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_prompt" not in data or data.get("raw_prompt") is not None
