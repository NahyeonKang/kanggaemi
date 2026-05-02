import json

import openai

from app.core.config import settings

SYSTEM_PROMPT = """당신은 한국 주식시장 전문 분석가입니다.
사용자가 제공하는 시장 데이터를 분석하고 반드시 다음 JSON 형식으로만 응답하세요.
다른 텍스트 없이 JSON만 반환하세요.

{
  "summary": "시황 요약 (2-4문장)",
  "key_points": [
    {"title": "포인트 제목", "description": "포인트 설명"},
    ...
  ],
  "risks": ["리스크 항목 1", "리스크 항목 2", ...],
  "outlook": "단기 전망 (1문장)"
}

분석 원칙:
- 과장 없이 데이터 기반으로 설명
- 수급, 파생, 가격 흐름을 분리해서 설명
- 개인 투자자 관점에서 핵심 포인트를 요약
- 확실하지 않은 인과관계는 추정으로 표현
"""


class LLMClient:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Please set it in the .env file or as an environment variable."
            )
        self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_report(self, prompt: str) -> dict:
        response = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return json.loads(response.choices[0].message.content)
