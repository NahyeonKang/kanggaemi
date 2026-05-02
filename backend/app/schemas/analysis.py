from typing import Optional, List
from pydantic import BaseModel


class AnalysisRequest(BaseModel):
    symbol: str
    market: str = "KRX"
    report_type: str = "daily"
    tone: str = "professional"
    user_prompt: Optional[str] = None


class KeyPoint(BaseModel):
    title: str
    description: str


class AnalysisResponse(BaseModel):
    symbol: str
    summary: str
    key_points: List[KeyPoint]
    risks: List[str]
    outlook: str
    raw_prompt: Optional[str] = None