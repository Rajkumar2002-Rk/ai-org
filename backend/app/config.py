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
    # Output-token ceiling for a single generated file. The old hardcoded 8192
    # truncated large files (the Stripe-payment page repeatedly), producing
    # unparseable JSON that was silently converted to a placeholder stub.
    # claude-sonnet-5 / claude-opus-4-8 both support up to 128K output tokens;
    # this is a generous headroom well under that ceiling. A cap is free — you
    # are billed for tokens actually produced, not the ceiling.
    codegen_max_tokens: int = 64000

    # Product Intelligence: analytical but insightful (locked per CONTEXT.md).
    pi_model: str = "gpt-4o"
    pi_temperature: float = 0.4

    # QA agent (Week 6). Gemini 2.5 Flash-Lite per the UPDATED ROUTING in
    # CONTEXT.md ("apply from Week 4 onwards"); 0.1 = consistent test cases.
    qa_model: str = "gemini-2.5-flash-lite"
    qa_temperature: float = 0.1
    # Ephemeral test environment limits (seconds) — every step is bounded so QA
    # can never hang the pipeline.
    qa_install_timeout: int = 180
    qa_boot_timeout: int = 45
    qa_request_timeout: int = 10
    # Max retries per failing issue before it is escalated (never infinite).
    qa_max_retries: int = 3
    # Full `npm install && next build` for generated UI. Off by default: it
    # downloads hundreds of MB and takes minutes per run. When off, the frontend
    # check still validates imports, hallucinated deps and structure.
    qa_frontend_full_build: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()   
