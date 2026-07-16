from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/ai_org"
    redis_url: str = "redis://redis:6379/0"

    # Optional API keys. When absent, the BA agent and competitive
    # intelligence fall back to local mock providers so the full flow
    # still works end-to-end without external services.
    openai_api_key: str | None = None
    google_places_api_key: str | None = None
    yelp_api_key: str | None = None
    # Extra code-gen providers (Week 4). Absent -> fall back to OpenAI.
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    # LLM routing for the BA agent (locked per CONTEXT.md).
    ba_model: str = "gpt-4o-mini"
    ba_temperature: float = 0.7

    # Architect agent uses the bigger model at low temperature (locked).
    architect_model: str = "gpt-4o"
    architect_temperature: float = 0.2

    # Code-gen cost mode: "real" honours the blueprint's locked routing
    # (Claude for UI etc). "cheap" overrides every code-gen call to a budget
    # model — same pipeline, pennies instead of dollars, for testing.
    codegen_mode: str = "real"
    codegen_cheap_model: str = "gemini-2.5-flash-lite"

    # Product Intelligence: analytical but insightful (locked per CONTEXT.md).
    pi_model: str = "gpt-4o"
    pi_temperature: float = 0.4

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()   
