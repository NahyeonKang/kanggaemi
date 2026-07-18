from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"

load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    PROJECT_NAME: str = "KangGaeMi Backend"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    DATABASE_URL: str

    KIS_BASE_URL: str = "https://openapi.koreainvestment.com:9443"
    KIS_APPKEY: str = ""
    KIS_SECRETKEY: str = ""

    FRED_API_KEY: str = ""
    ECOS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        extra="ignore",
    )


settings = Settings()
