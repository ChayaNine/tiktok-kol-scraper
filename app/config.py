from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APIFY_API_TOKEN: str
    DATABASE_URL: str = "sqlite:///./tiktok_kol.db"

    class Config:
        env_file = ".env"


settings = Settings()
