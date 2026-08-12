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
    # Platform-held vision key for menu PDF extraction, injected by DevOps ONLY
    # into deployed apps that shipped the menu PDF-upload feature (Week 10). This
    # is a SCOPED, single-purpose platform key — deliberately separate from the
    # master anthropic_api_key, and distinct from the still-open owner-facing
    # secrets-onboarding UI. Absent -> scanned-menu extraction is unavailable and
    # the app says so honestly (it never fakes an extraction).
    menu_extraction_api_key: str | None = None

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

    # ---------------------------------------------------------------- DevOps (Week 7)
    # DevOps runs on GPT-4o mini per the locked routing, but it is deliberately
    # deterministic-first (like QA's root_cause): the model is only consulted to
    # phrase a human-readable summary, never to decide isolation, cost, or whether
    # a health-check failure is auto-fixable.
    devops_model: str = "gpt-4o-mini"
    devops_temperature: float = 0.1

    # WHERE a deployment runs. "local" (default) builds and runs REAL Docker
    # containers on this machine — fully provable, $0, no teardown-of-paid-infra
    # risk. "aws" is the real EC2 path (ECR + t3.micro + Caddy/Let's Encrypt +
    # Route53); it costs money and is never touched by the offline test suite.
    deploy_target: str = "local"

    # Paid Opus security review. Default ON (real pipeline runs). Set False ONLY to
    # save money during a LOCAL codegen-quality / feature-debugging phase — each
    # iteration then costs ~$1 (generation) instead of ~$3 (generation + Opus). The
    # skip is IGNORED for `deploy_target == "aws"` (a real deploy is always reviewed),
    # and the certificate it produces is honestly marked `security_review_skipped`
    # so nothing can masquerade as certified. Re-enable before any real run/demo.
    security_review_enabled: bool = True

    # Real domain for generated apps. DNS for `apps.rajkumarai.dev` is delegated
    # to the Route53 hosted zone below; per-app subdomains live under it as
    # <slug>-<suffix>.apps.rajkumarai.dev.
    platform_domain: str = "rajkumarai.dev"
    apps_subdomain: str = "apps.rajkumarai.dev"
    route53_zone_id: str | None = "Z02777111O69NKZ136VS"
    aws_region: str = "us-east-2"
    aws_account_id: str | None = None            # discovered via STS when needed
    # Email Let's Encrypt uses for expiry notices (Caddy ACME account).
    letsencrypt_email: str = "rajkumarn2002@gmail.com"

    # AWS sizing: tier -> concrete EC2 instance type. "large" uses ECS in the
    # driver; small/medium run on a single EC2 instance (see devops/sizing.py).
    ec2_instance_small: str = "t3.micro"
    ec2_instance_medium: str = "t3.small"

    # Symmetric key (Fernet, urlsafe-base64, 32 bytes) that encrypts secret VALUES
    # at rest in the `secrets` table. Absent -> the secrets store refuses to
    # store/read (it will not silently hold plaintext). Tests supply an ephemeral
    # key; production sets SECRETS_ENC_KEY.
    secrets_enc_key: str | None = None

    # Health check (STEP 7): ping the live URL every N seconds for up to M seconds.
    devops_health_interval: int = 10
    devops_health_timeout: int = 120
    # Auto-fix is attempted at most this many times, and only for INFRASTRUCTURE
    # faults — never generated app code or security config.
    devops_autofix_max: int = 1
    # Bounded build/deploy steps so a deploy can never hang the pipeline.
    devops_build_timeout: int = 900
    devops_deploy_timeout: int = 600

    # ---------------------------------------------------------------- Documentation (Week 8)
    # Gemini 2.5 Flash-Lite per CONTEXT UPDATED ROUTING (locked through Week 8 —
    # the claude-haiku-4-5 switch is scheduled for AFTER Week 8). 0.5 = readable
    # but consistent (CONTEXT temperature table). The Documentation agent is
    # read-only: it reports real stored data and never fabricates.
    documentation_model: str = "gemini-2.5-flash-lite"
    documentation_temperature: float = 0.5

    # ---------------------------------------------------------------- Week 9 background agents
    # Routing stays CURRENT (the post-Week-8 model switch is a separate session).
    # All three are deterministic-first: restart, math and log-aggregation are
    # code; the LLM only polishes plain-English text, with deterministic fallbacks.
    monitoring_model: str = "gemini-2.5-flash-lite"       # #13 (unchanged)
    autofix_model: str = "gpt-4o"                          # #14 (unchanged)
    cost_tracker_model: str = "gemini-2.5-flash-lite"      # #15 (unchanged)
    monitoring_temperature: float = 0.4
    # Ping cadence + request timeout for the monitoring loop.
    monitoring_interval_seconds: int = 60
    monitoring_request_timeout: int = 10
    # A Level-1 self-heal that took longer than this to recover becomes a Level-2
    # (fixed, but notify the user after). Quicker than this stays silent.
    autofix_notify_downtime_seconds: int = 120
    # Budget alert fires when projected month cost exceeds budget by this ratio.
    cost_budget_alert_ratio: float = 1.20
    # Real AWS Cost Explorer polling is REAL code but OFF by default: CE data lags
    # 24-48h and costs ~$0.01/call, so testing uses recorded/synthetic readings.
    aws_cost_explorer_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()   
