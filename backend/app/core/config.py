import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "KangGaeMi Backend"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    APP_ENV: str = "local"
    DEBUG: bool = True

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    SCRAPER_TIMEOUT_SECONDS: int = 15

    KIWOOM_BASE_URL: str = "https://api.kiwoom.com"
    KIWOOM_APPKEY: str = ""
    KIWOOM_SECRETKEY: str = ""

    KIS_BASE_URL: str = "https://openapi.koreainvestment.com:9443"
    KIS_APPKEY: str = ""
    KIS_SECRETKEY: str = ""

    FRED_API_KEY: str = ""
    NEWS_API_KEY: str = ""

    ECOS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()


def get_env(name: str) -> str:
    """Return the value of an environment variable, or an empty string if unset."""
    return os.getenv(name, "")