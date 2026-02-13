"""App configuration from env."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    moleculoids_base_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://postgres:postgres@localhost:5432/molecule_explorer",
            ),
            moleculoids_base_url=os.getenv("MOLECULOIDS_BASE_URL", "http://localhost:8001"),
        )


settings = Settings.from_env()
