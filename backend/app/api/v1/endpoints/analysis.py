from fastapi import APIRouter, Depends

from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis_service import AnalysisService

router = APIRouter()


def get_analysis_service() -> AnalysisService:
    return AnalysisService()


@router.post("/generate", response_model=AnalysisResponse)
def generate_analysis(req: AnalysisRequest, service: AnalysisService = Depends(get_analysis_service)):
    return service.generate_analysis(req)
