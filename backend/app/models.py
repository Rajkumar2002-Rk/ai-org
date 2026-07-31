from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created")
    # Full confirmed BA summary (JSON string) — the Architect's input.
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    design_preferences: Mapped[list["DesignPreference"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    blueprints: Mapped[list["Blueprint"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    product_reviews: Mapped[list["ProductReview"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    generated_files: Mapped[list["GeneratedFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pipeline_stages: Mapped[list["PipelineStatus"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    code_reviews: Mapped[list["CodeReview"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    qa_results: Mapped[list["QAResult"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    secrets: Mapped[list["Secret"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="conversations")


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    # source: user_stated | competitor_insight | platform_suggested
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # Locked once the user confirms — cannot be changed without approval.
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="requirements")


class DesignPreference(Base):
    __tablename__ = "design_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    style_vibe: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_sites: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="design_preferences")


class Blueprint(Base):
    __tablename__ = "blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # The full technical blueprint produced by the Architect (JSON string).
    blueprint_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="blueprints")


class ProductReview(Base):
    __tablename__ = "product_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # The Product Intelligence review (recommendations, priorities…) as JSON.
    review_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="product_reviews")


class GeneratedFile(Base):
    __tablename__ = "generated_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[str] = mapped_column(String(50), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filepath: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # generated | needs_review
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="generated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="generated_files")


class PipelineStatus(Base):
    __tablename__ = "pipeline_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    # running | done | error
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="pipeline_stages")


class QAResult(Base):
    """One row per QA test (final state after any retries).

    `blueprint_id` pins the result to the exact blueprint version that was
    tested — BA/Architect classification is non-deterministic on borderline
    inputs, so a QA run is a snapshot of THAT blueprint, not a permanent
    guarantee. A future re-test can be compared against the same version.
    """

    __tablename__ = "qa_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # Groups every row written by ONE QA pass. A project is re-tested repeatedly
    # and blueprint_id does NOT disambiguate those re-runs (they share a
    # blueprint), so without this the only way to separate runs is by matching
    # created_at timestamps by hand.
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # The blueprint version these results describe (nullable: assembly may fail
    # before a blueprint is resolvable).
    blueprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("blueprints.id", ondelete="SET NULL"), nullable=True
    )
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 1 = user interaction, 2 = security attack, 3 = root cause tracing
    test_level: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # developer_fix | developer_rework | architect_rework | ba_rework
    root_cause_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="qa_results")


class CodeReview(Base):
    __tablename__ = "code_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("generated_files.id", ondelete="CASCADE"), nullable=False
    )
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_fixed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    security_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviewed_by_model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="code_reviews")


class LLMUsage(Base):
    """One row per LLM call — the measured basis for any cost figure.

    `run_id` is the SAME id a QA pass writes onto its qa_results rows
    (migration 0008), so "what did this QA cycle cost" is a join, not a
    timestamp-matching exercise.

    NULL token counts are meaningful and are NOT zero: they mean the provider
    returned no usable usage block and `capture_ok` is false. Totals computed
    without excluding those rows understate real spend — see app/usage.py.
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: calls made outside a tagged pass (ad-hoc, BA conversation) still
    # get recorded rather than dropped.
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Which pipeline stage spent this — "qa", "reviewer", "developers", ...
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # What routing asked for vs the concrete model id actually billed. These
    # differ under CODEGEN_MODE=cheap and on provider fallback.
    model_requested: Mapped[str] = mapped_column(String(100), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL when no confirmed rate exists for model_used. Recomputable from the
    # token counts above once a rate is confirmed.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8), nullable=True)
    # False = the provider gave us no usable usage block. Such a row must never
    # be read as a free call.
    capture_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fell_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Secret(Base):
    """A user-connected API key / credential for ONE project's generated app.

    DevOps (Week 7) reads these and injects them into the deployed container as
    environment variables. The VALUE is stored encrypted (Fernet) and never
    returned to any API/dashboard payload — only `key_name` and a count are ever
    surfaced. See app/devops/secrets_store.py.

    ⚠️ KNOWN GAP, deliberately logged (like `requirements.txt` was for Week 7):
    no onboarding stage populates this table with REAL user-supplied secrets yet.
    A proper "connect your API keys" onboarding UI is scoped future work. For now
    the table is real, encrypted, and read by DevOps; it is seeded directly (e.g.
    in tests) until that UI exists. Stripe deliberately never lands here — the
    business owner connects their own Stripe account via Stripe's hosted OAuth
    from inside the generated app, so the platform never stores a Stripe token.
    """

    __tablename__ = "secrets"
    __table_args__ = (
        # One value per key name per project — a re-connect updates in place.
        UniqueConstraint("project_id", "key_name", name="uq_secrets_project_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The env var name the generated app expects, e.g. "OPENAI_API_KEY".
    key_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Fernet ciphertext of the secret value. NEVER the plaintext, NEVER logged,
    # NEVER placed in an API response.
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="secrets")


class Deployment(Base):
    """One deployment attempt for a project's generated app (Week 7, DevOps).

    Columns beyond the original spec exist to keep the record HONEST rather than
    reassuring — the standing principle of this project:

    - `auto_fixed` + `fix_description`: a deployment that only came up after an
      infra auto-fix is a DIFFERENT state from a clean first-pass success and is
      shown as such, never laundered into looking pristine (cf. QA's
      `recertified_after_qa`).
    - `ssl_type`: 'lets_encrypt' (real, on AWS) vs 'self_signed_local' (local
      proof) vs 'none'. `ssl_enabled=True` is never claimed for a cert we did not
      actually stand up, and the ISSUER is recorded so the two are never confused.
    - `cost_basis`: whether `monthly_cost_estimate` is a projection for the sized
      AWS tier ('projected_aws_<tier>'), an actually-billed AWS deployment
      ('billed_aws_<server>'), or a local $0 run ('local_zero'). A number without
      its basis is not a measurement.
    - `security_certified`: whether a valid Opus certificate covered EXACTLY the
      files that were deployed (drift re-checked at deploy time). FAILS CLOSED.
    """

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Groups every row/LLM call this deploy pass writes (joins to llm_usage.run_id).
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # The exact blueprint version whose cloud_config was deployed.
    blueprint_id: Mapped[int | None] = mapped_column(
        ForeignKey("blueprints.id", ondelete="SET NULL"), nullable=True
    )
    # local | aws — which driver produced this deployment.
    target: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    live_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subdomain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Human + concrete server descriptor, e.g. "EC2 t3.micro" / "local docker".
    server_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # deploying | live | failed | torn_down
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="deploying")
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # lets_encrypt | self_signed_local | none
    ssl_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    monthly_cost_estimate: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    # projected_aws_<tier> | billed_aws_<server> | local_zero
    cost_basis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # A deployment that needed an infra auto-fix is flagged, never silently clean.
    auto_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fix_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether the Opus certificate covered EXACTLY the deployed files (fail-closed).
    security_certified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Snapshot for the "X tests passed" badge (from the latest QA pass).
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # How many health probes it took to come up (0 = never came up).
    health_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Registry references for the built images (ECR URI or local image tag).
    image_backend_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_frontend_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="deployments")
