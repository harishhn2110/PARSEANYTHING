"""Runtime settings for ParseAnything Atlas."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    max_upload_bytes: int = 64 * 1024 * 1024
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'atlas.db').as_posix()}"
    object_dir: Path = ROOT / "data" / "objects"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "parseanything"
    s3_region: str = "us-east-1"
    
    # Confidence thresholds
    confidence_verified_threshold: float = 0.85
    confidence_review_threshold: float = 0.60

    # Optional LLM integration
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_provider: str = "auto"  # auto, openai, gemini, local

    # Worker behavior
    inline_jobs: bool = False
    max_processing_time_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
