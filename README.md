# Autonomous AI Engineering Organization

An autonomous "AI engineering org": you describe an app idea in plain language,
and a pipeline of specialized LLM agents interviews you, designs the system,
writes the code, security-reviews it, tests it on an ephemeral instance, and
deploys a working, isolated app — end to end.

The core engineering idea is a **Code Integrity Engine**: rather than trusting
the LLMs, the platform validates generated code with **deterministic, no-LLM
gates** at every stage (syntax, import resolution, schema adherence, endpoint
completeness, duplicate routes, hallucinated packages, frontend truncation, …).
Each gate flags a precise problem, feeds a targeted repair back to the agent,
and retries — so a one-off LLM mistake is caught and self-healed instead of
shipping. Dozens of these gates were each grounded in a real captured failure.

> Status: research / portfolio project. The pipeline reliably reaches a **live
> local deploy** (isolated per-project Docker stack over HTTPS). The AWS deploy
> path is scaffolded but local is the supported target.

## The pipeline

```
BA interview → Product Intelligence → Architect → Developers (build)
   → smoke-boot gate → Code Reviewer (Opus security) → QA → DevOps deploy → Docs
```

- **BA agent** — conversational interview that captures the idea, audience,
  budget, design vibe, and (for food businesses) menu setup; runs live
  competitive research.
- **Product Intelligence** — a review gate that reads the captured requirements
  and returns a product read + recommendations before any build.
- **Architect** — turns the requirements into a blueprint: tech stack, database
  schema, API endpoints, and a wave-scheduled set of sprint tickets. Deterministic
  Python owns the fixed rules; an LLM fills the creative parts.
- **Developer agents** — generate the actual application code, ticket by ticket,
  behind the Code Integrity Engine's build gate.
- **smoke-boot gate** — assembles the generated app in a throwaway venv and
  boots it (no LLM). A build that can't start never reaches the paid review.
- **Code Reviewer** — a general pass plus a real **Opus security review** that
  must certify the code (fail-closed) before deploy.
- **QA** — provisions an ephemeral DB, boots the app, and runs real HTTP tests.
- **DevOps** — assembles images, deploys an isolated per-project stack with
  HTTPS, injects secrets, and health-checks the live URL.
- **Documentation** — generates a user guide and demo material from the build.

**Owner onboarding** is a first-class feature: the platform provisions the
operator-facing integrations at build/deploy time — Stripe Connect (click-to-
connect OAuth), per-project Auth0 apps (Management API), and email (SMTP) — and
wires the generated app to consume them.

## Stack

- **Backend:** FastAPI (async) + SQLAlchemy async + Alembic — port 8000
- **Database:** PostgreSQL · **Cache/queue:** Redis
- **Frontend:** React + Next.js (App Router) — port 3000
- **LLMs:** OpenAI, Anthropic (incl. Opus for security review), Google Gemini —
  routed per stage for cost
- **Containers:** Docker Compose; generated apps deploy as isolated Docker stacks
  fronted by Caddy (HTTPS)

## Run it

```bash
cp .env.example .env   # then fill in the API keys you have
docker compose up -d
```

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health → `{ "status": "ok" }`
- API docs: http://localhost:8000/docs

The backend runs `alembic upgrade head` on startup. Real code generation and the
Opus security review require the corresponding API keys in `.env`
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …). See `.env.example`
for the full list; **never commit your real `.env`** (it is gitignored).

## Project structure

```
backend/app/
  main.py            FastAPI app: conversation + /pipeline/* stage endpoints
  config.py          Settings from env
  llm.py, codegen.py, providers.py, usage.py   LLM routing, generation, cost tracking
  models.py          DB models (projects, blueprints, generated_files, deployments, …)
  ba/                Business Analyst interview agent
  product_intel/     Product Intelligence review gate
  competitive_intel.py   Live competitive research
  architect/         Blueprint builder (stack, schema, endpoints, sprint tickets)
  developers/        Developer agents + the Code Integrity Engine build gate
  qa/                Ephemeral assemble-boot-and-test (smoke-boot + QA)
  reviewer/          Code review + Opus security certification (fail-closed)
  devops/            Deploy: manifest, sizing/cost, isolated stack, HTTPS, secrets
  onboarding/        Owner onboarding: Stripe Connect, Auth0 provisioning, email
  documentation/     User guide + demo generation
  background/        Monitoring, cost checks, summaries
  design_explain.py  Design rationale
  alembic/           Migrations
frontend/            Next.js App Router UI
docker-compose.yml   backend, frontend, postgres, redis
```

## Pipeline API (per project)

`POST /conversation/start` → `/conversation/message` (BA interview) →
`POST /pipeline/review` → `/pipeline/start` (architect) → `/pipeline/build` →
`/pipeline/secure` → `/pipeline/qa` → `/pipeline/deploy` → `/pipeline/document`,
each with a matching `GET /pipeline/{id}/…-status`.

## Testing

The Code Integrity Engine is covered by deterministic, LLM-free offline suites
(architect, developers, qa, devops, onboarding, menu onboarding, smoke-boot,
venv pinning, …). Example:

```bash
docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
    backend python tests/test_developers_offline.py
```
