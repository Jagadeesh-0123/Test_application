from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Enterprise Inventory Orchestrator"
    DATABASE_URL: str = "sqlite+aiosqlite:///./enterprise_inventory.db"
    API_KEY_SECRET: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
