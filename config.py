from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/telegram_erp"
    REDIS_URL: str = "redis://localhost:6379/0"
    ADMIN_IDS: List[int] = []

    @property
    def async_database_url(self) -> str:
        """
        Railway injects DATABASE_URL as postgresql://...
        SQLAlchemy async requires postgresql+asyncpg://...
        This property fixes it automatically.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Sync URL for Alembic migrations."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if "+asyncpg" in url:
            url = url.replace("+asyncpg", "")
        return url

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
