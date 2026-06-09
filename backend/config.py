from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Google Gemini
    gemini_api_key: str = ""
    gemini_model:   str = "gemini-2.5-flash"   # swap to "gemini-3.5-pro" for higher quality

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model:   str = "meta-llama/llama-3-8b-instruct"

    # Database
    database_url: str = "sqlite+aiosqlite:///./meetings.db"

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
