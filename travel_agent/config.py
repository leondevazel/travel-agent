from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./travel_agent.db"
    # MOCK_MODE=1 skips every agent and returns a canned trip, so working on
    # the UI costs nothing. Never enable it in a real deployment.
    mock_mode: bool = False
    metrics_log_path: str = "logs/metrics.jsonl"


settings = Settings()
