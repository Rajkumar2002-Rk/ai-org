# Autonomous AI Engineering Organization — CONTEXT.md

This file is Claude Code's memory between sessions. Read this
fully before doing anything else in this project.

---

## WHAT THIS PROJECT IS

A platform where non-technical users describe a software idea
in plain English and receive a fully built, tested, secured,
and deployed application automatically. 15 specialized AI
agents handle every stage — from requirements to ongoing
maintenance.

## MISSION STATEMENT

"An AI engineering partner that remembers the entire product,
understands business intent, protects your work, explains its
decisions, collaborates with the team, and safely evolves an
application from idea to production."

This is NOT another AI website generator. Every other AI
builder is great at generating a first draft. This platform is
great at everything that comes after — consistency, ownership,
maintainability, scalability, transparency, and trust.

---

## CORE RULES — NEVER BREAK THESE

- Users never see code, agent names, or LLM names. Ever.
- BA is the only agent that talks to users directly.
- Security review always uses Claude Opus 4.8. No exceptions,
  regardless of project size or cost.
- Platform owns the hosting — users never need an AWS account.
- Animation character replaces all technical progress
  indicators. No raw logs or technical stage names shown.
- Mobile app detection and explanation happens at the BA stage,
  not at deployment time.
- No agent can ever delete a file — only mark as deprecated.
  User-deleted files go to a 30-day recovery bin first.
- Every change takes a snapshot before touching anything
  (Safe Mode — always on, cannot be disabled).
- No agent marks a task complete without proof it works.
- Every fix must have a documented root cause — no random
  fixes or guessing.
- Agents only touch files inside their current ticket's scope.
  Out-of-scope changes are auto-reverted.
- All package imports and API calls are verified to actually
  exist before use — no hallucinated dependencies.
- No prompt-credit pricing. Monthly hosting includes unlimited
  changes.
- Full code export is always available to the user — no
  vendor lock-in, ever.

---

## THE 15 AGENTS

| #   | Agent                 | Talks to user?      | Model                         | Job                                                          |
| --- | --------------------- | ------------------- | ----------------------------- | ------------------------------------------------------------ |
| 1   | BA Agent              | Yes — only one      | GPT-4o mini                   | Requirements + competitive intelligence + design preferences |
| 2   | Product Intelligence  | Before build only   | GPT-4o                        | UX review + business goal alignment + PM recommendations     |
| 3   | Architect             | Never               | GPT-4o                        | Technical blueprint + API detection + LLM routing map        |
| 4   | Backend Developer     | Never               | GPT-4o                        | Server logic, database, API endpoints                        |
| 5   | Frontend Developer    | Never               | Claude Sonnet                 | Premium UI, animations, responsive design                    |
| 6   | Mobile Developer      | Never               | Claude Sonnet                 | React Native screens if mobile chosen                        |
| 7   | Integration Developer | Never               | GPT-4o mini                   | Third-party API connections                                  |
| 8   | Design Review         | Never               | Claude Sonnet                 | UX evaluation, consistency, interaction completeness         |
| 9   | Code Reviewer         | Security cert only  | GPT-4o mini + Claude Opus 4.8 | Code quality + security (Opus always)                        |
| 10  | QA Agent              | Test report only    | GPT-4o mini                   | 5 levels of testing + root cause tracing                     |
| 11  | DevOps                | Live link only      | GPT-4o mini                   | Deploy, SSL, domain, Safe Mode, version timeline             |
| 12  | Documentation         | Final summary       | GPT-4o mini                   | User guide, demo script, handoff summary                     |
| 13  | Monitoring            | Weekly summary      | GPT-4o mini                   | Health, performance, error tracking                          |
| 14  | Auto-fix              | Level 3 issues only | GPT-4o                        | Self-healing, snapshot safety, rollback                      |
| 15  | Cost Tracker          | Monthly dashboard   | GPT-4o mini                   | Spend tracking, optimization, budget alerts                  |

---

## LLM ROUTING — LOCKED

- BA conversation: GPT-4o mini
- Architect decisions: GPT-4o
- Code generation (general): GPT-4o
- Frontend UI code specifically: Claude Sonnet (always — better
  React/Tailwind output than GPT-4o)
- Design Review: Claude Sonnet
- Security review: Claude Opus 4.8 — ALWAYS, hardcoded, never
  changes regardless of cost or project size
- QA, DevOps, Docs, simple tasks: GPT-4o mini
- Product Intelligence: GPT-4o

## UPDATED ROUTING — apply from Week 4 onwards:

- Integration Developer: Gemini 2.5 Flash-Lite
  ($0.10/$0.40 per MTok — cheapest option)
- QA Agent: Gemini 2.5 Flash-Lite
- Documentation: Gemini 2.5 Flash-Lite
- Cost Tracker: Gemini 2.5 Flash-Lite
- Competitive Intelligence: future refactor to
  Gemini 3.5 Flash with native grounding

## TEMPERATURE SETTINGS — LOCKED

- BA conversation: 0.7 (needs to feel natural)
- Architect: 0.2 (consistent decisions)
- Code generation: 0.1 (consistent code, not creative)
- Security review: 0.0 (pure analysis, zero creativity)
- QA testing: 0.1 (consistent test cases)
- Documentation: 0.5 (readable but consistent)
- Product Intelligence: 0.4 (analytical but insightful)
- Design Review: 0.3 (consistent UX evaluation)

---

## TECH STACK — LOCKED

- Backend: FastAPI + Python (async)
- Agent orchestration: LangGraph
- Database: PostgreSQL + SQLAlchemy (async)
- Cache / pub-sub: Redis
- Vector store: Qdrant
- File storage: AWS S3
- Frontend: React + Next.js
- Styling: Tailwind CSS
- Components: Shadcn UI
- Animations: Framer Motion
- 3D elements: Spline API
- Icons: Lucide
- Character animation: LottieFiles
- Containers: Docker + docker-compose
- Cloud: AWS (account already exists)
- IaC: Terraform
- CI/CD: GitHub Actions
- Monitoring: Prometheus + Grafana
- SSL: Let's Encrypt
- Competitor data: Google Places API + Yelp Fusion API

---

## PROJECT STATUS

### Completed weeks

**Week 1 — Foundation scaffold — DONE**

- Week 1 — Foundation scaffold. FastAPI backend (port 8000) with
  /health and stubbed POST /conversation, PostgreSQL via async
  SQLAlchemy + Alembic (projects, conversations tables), Redis,
  Next.js frontend (port 3000), and docker-compose running all four
  services together. Verified end-to-end via `docker compose up`.

### What I learned — Week 1

Claude Code fills this in after every week

---

WEEK 1 — Foundation:

- FastAPI is an async Python web framework. We use it because
  it handles multiple AI agent requests simultaneously without
  blocking — critical for a pipeline that runs parallel agents.
  The app uses a lifespan handler to verify the DB and Redis
  connections on startup, so the service fails fast if a
  dependency is unreachable.
- SQLAlchemy is an ORM — it lets Python talk to PostgreSQL
  without writing raw SQL. We use the async version (asyncpg
  driver) because our agents run asynchronously. Models are
  defined as Python classes (Project, Conversation) that map
  to tables.
- Alembic handles database migrations — versioned scripts that
  build/alter the schema. Migration 0001 creates the projects
  and conversations tables, and it runs automatically when the
  backend container starts (alembic upgrade head before uvicorn),
  so the schema is always in sync with the code.
- Redis is an in-memory database. We use it for two things:
  caching frequent data so we don't hit PostgreSQL every time,
  and pub-sub messaging so agents can send real-time updates
  to the frontend as the pipeline runs. This week we just
  connect and ping it to prove the wiring works.
- Next.js (React) is the frontend. One page sends the user's
  idea to POST /conversation and shows the reply. CORS is
  enabled on the backend so the browser on :3000 can call :8000.
- Docker packages everything into containers so it runs
  identically on your Mac, on AWS, and on any interviewer's
  machine. docker-compose.yml starts all four services
  (backend, frontend, postgres, redis) with one command, with
  healthchecks so the backend only starts once postgres and
  redis are ready.

---

**Week 2 — Enhanced BA Agent — DONE**

- Deterministic BA conversation driven by a LangGraph per-turn graph
  (ingest → advance → compose) with a Python controller owning the locked
  question order. GPT-4o mini handles only phrasing, extraction, complaint
  analysis, safety, and validation — never the flow itself.
- Full flow verified end to end: greeting → 6 questions (+ business name &
  location) → mobile detection → competitive intelligence → plan → design →
  edit-a-field → confirmation → requirements + design_preferences locked in
  the database. Runs live with real Google Places + GPT-4o mini, and against
  built-in mocks when keys are absent.

### Files created / changed in Week 2

Backend (`backend/app/`):

- `config.py` — added optional OPENAI / GOOGLE_PLACES / YELP keys + BA model/temp
- `models.py` — added Requirement and DesignPreference tables
- `schemas.py` — start / message / research-status request+response models
- `main.py` — /conversation/start, /conversation/message, research-status;
  logs turns, persists on confirm, marks rejected on safety block
- `llm.py` — async GPT-4o mini wrapper: chat, complete_json, moderate (all
  return None/fallback when no key)
- `providers.py` — competitor data: live Google Places + Yelp, realistic mock
  fallback, Google Maps links per place
- `competitive_intel.py` — gathers reviews, mines complaint themes, converts
  each to an APP/WEBSITE feature suggestion, builds sources + attribution
- `ba/state.py` — BAState + stage order, Redis persistence of in-progress convo
- `ba/graph.py` — LangGraph turn processor (validation, safety, mobile
  interrupt, edit flow, confirm gate)
- `ba/controller.py` — stage questions/UI, ingest, mobile & plan & design
  options, edit menu, category derivation, idea paraphrase, DB persist
- `ba/validation.py` — answer sanity checks (re-ask up to 3x, then accept)
- `ba/safety.py` — content guardrail (moderation API + LLM policy classifier +
  keyword fallback)
- `alembic/versions/0002_ba_tables.py` — requirements + design_preferences
- `requirements.txt` — added langgraph, openai, httpx
  Frontend (`frontend/app/`):
- `page.tsx` — chat UI: message bubbles, quick-choice buttons, mobile/plan/
  design/CI cards, "Researching your market" indicator, competitor source
  links, edit + start-over, blocked state
- `globals.css` — pulse animation for the research indicator
  Docs / config:
- `docs/SAFETY_POLICY.md` — full prohibited-use policy and rationale
- `.env` / `.env.example` / `docker-compose.yml` — pass the three API keys

### New database tables (Week 2)

- `requirements` (id, project_id, requirement, source, is_locked, created_at)
  source = user_stated | competitor_insight | platform_suggested
- `design_preferences` (id, project_id, style_vibe, reference_sites,
  brand_color, created_at)

### What now works end to end

- Natural chat: greets back on small talk, asks ONE question at a time in the
  locked order, never uses technical words, remembers earlier answers.
- Answer validation: vague/gibberish answers get re-asked (max 3), then
  accepted so a user is never trapped; brief real ideas ("a coffee shop") pass.
- Mobile detection: interrupts on phone/app words, offers the 3 plain-English
  options, resumes where it left off.
- Competitive intelligence: derives a clean business category, pulls real
  nearby competitors + reviews (Google live / mock fallback), mines complaint
  themes with GPT-4o mini, shows anonymized themes as app-feature suggestions
  plus a "real places we looked at" list with Maps links + attribution.
- Plans (Quick / Production / Scale), design preferences (vibe, references,
  color), full plain-English confirmation summary.
- Edit-a-field flow from the summary; persist-once on confirm.
- Safety guardrail on the idea, every free-text answer, and the final summary;
  blocks disallowed ideas, marks the project rejected, offers start-over.

---

**Week 3 — Architect + Product Intelligence + Smarter BA — DONE**
Pipeline is now: **BA (collect + understand) → Product Intelligence (review-gate)
→ Architect (blueprint)**. Verified end to end with an 8/8 automated stress test
(new domains: B2B SaaS, internal staff tool, telehealth, native app, tipping,
budget mismatches, edit flow). Note: this week delivered BOTH the Architect
(agent #3) and the Product Intelligence agent (agent #2), plus a BA overhaul.

### New agents / layers (Week 3)

- **Architect Agent** (`app/architect/`, GPT-4o @ 0.2, never talks to user) —
  hybrid builder: deterministic rules own cloud sizing, LLM routing, third-party
  triggers (Stripe/email), mobile + security tickets; GPT-4o generates tech
  stack, database schema, API endpoints, sprint tickets. Emits a full blueprint
  incl. a `security` section (Opus 4.8 as the security review model) + SEC ticket.
- **Product Intelligence Agent** (`app/product_intel/`, GPT-4o @ 0.4) — the
  review-gate between BA and Architect. Deterministic budget-vs-scale reality
  check + GPT-4o for feature relevance/pruning, must/nice priorities, and
  missing-essentials. Never converses — one review card the user approves.
- **Smarter BA understanding layer** (`ba/understanding.py`) — classifies the
  idea (customer_facing, platform, is_local, kind) and extracts clean facts
  (real business name, "just me" → 1). The controller uses this to ADAPT the
  flow: ask "website/app/both?" only when unclear, skip "how many users" for
  single-user tools, and skip location + competitor research unless it's a
  LOCAL, customer-facing business.

### Files created / changed in Week 3

Backend (`backend/app/`):

- `architect/builder.py` + `architect/graph.py` — the Architect (blueprint +
  security + cloud tiers + llm_routing + setup steps)
- `product_intel/reviewer.py` + `product_intel/graph.py` — the PI review
- `ba/understanding.py` — LLM classify + extract (name, user-count, is_local)
- `ba/state.py` — added ASK_PLATFORM stage
- `ba/controller.py` — platform question, next_applicable (stage skipping),
  is_local/customer_facing gating of location + CI, budget-aware plan
  recommendation, summary_json builder
- `ba/graph.py` — runs classification/extraction, uses next_applicable
- `config.py` — architect_model/temp (gpt-4o/0.2), pi_model/temp (gpt-4o/0.4)
- `llm.py` — complete_json now accepts a `model` arg (Architect/PI use gpt-4o)
- `models.py` — Project.summary_json; Blueprint + ProductReview tables
- `main.py` — /pipeline/review, /pipeline/start (with plan_override),
  /pipeline/{id}/status, /pipeline/{id}/blueprint
- `schemas.py` — pipeline start/status/review models
- `alembic/versions/0003_architect.py` (summary_json + blueprints),
  `0004_product_reviews.py`
  Frontend (`frontend/app/`):
- `page.tsx` — PI review-gate card (budget verdict, recommendations, dropped
  features, priorities, missing essentials) with "Start smaller"/"Build it";
  Architect "Designing your app… → Design complete" handoff
- `globals.css` — spin animation for the designing spinner

### New database (Week 3)

- `projects.summary_json` — the full confirmed BA summary (Architect's input)
- `blueprints` (id, project_id, blueprint_json, created_at)
- `product_reviews` (id, project_id, review_json, created_at)

### What now works end to end (Week 3)

- On confirmation the frontend auto-runs the **Product Intelligence review-gate**
  (POST /pipeline/review): shows budget verdict, recommendations, set-aside
  features, must-have priorities, and missing essentials on one card.
- The review refines the summary (keeps only fitting features + adds priorities
  and missing essentials) that the Architect then reads.
- **Budget teeth:** a "Start smaller" button (plan_override) downgrades the plan
  before the Architect sizes the server; comfortable budgets show no nag.
- Clicking **Build it** runs the **Architect** (POST /pipeline/start) in the
  background; the UI shows "Designing your app… → Design complete" and the
  blueprint JSON is stored in the `blueprints` table.
- Blueprint always contains: tech_stack, database_schema, api_endpoints,
  third_party_apis (with plain-English setup steps), sprint_tickets, a `security`
  section, llm_routing (security_review = claude-opus-4-8), cloud_config.
- Payments mentioned (even implied, e.g. "tip") → Stripe added, user-handled,
  with plain-English steps. Mobile chosen → React Native + mobile tickets.
- Smarter BA: asks "website/app/both?" only when unclear; skips "how many users"
  for single-user tools; skips location + competitor research unless it's a
  LOCAL customer-facing business; extracts clean business name + user count.
- Verified by an 8/8 automated stress test AND the Week 3 testing checklist
  (BA confirm, auto-pipeline, "Designing your app…", blueprint stored with all
  required sections, Stripe on payments, plain-English steps, Opus for security).

---

**Week 4 — Developer Agents (+ multi-provider codegen & shared contract) — DONE**
Four Developer agents (Backend, Frontend, Mobile, Integration) build the
blueprint's sprint tickets in parallel and store real code in generated_files.
Verified across 3 domains (coffee/telehealth/SaaS); best run: 20/20 files,
0 needs_review, 0 fallbacks. The 8 Week-3 gating scenarios still pass 8/8.

### New agents / layers (Week 4)

- **4 Developer agents** (`app/developers/agents.py`) — each ticket runs the exact
  5-step process: read ticket → check already-generated work → write code in
  chunks (skeleton, logic, error handling) → self-review → store. Recovery:
  try 1 generate, try 2 different approach, try 3 minimal version, then flag
  `needs_review`. Never silently fails.
- **Parallel orchestrator** (`app/developers/orchestrator.py`) — asyncio
  dependency waves: independent tickets run simultaneously, dependents wait.
- **Multi-provider codegen** (`app/codegen.py`) — routes by model name:
  `claude-*`→Anthropic, `gemini-*`→Google, else OpenAI; graceful fallback to
  GPT-4o when a provider is unavailable, deterministic stub when none are.
- **BINDING PROJECT CONTRACT** (the key fix) — the Architect now emits
  foundation tickets (FND-1 models.py, FND-2 database.py) that build FIRST;
  their real code plus a frozen contract (exact tables/columns, exact endpoint
  paths, module layout, "FastAPI never Flask", "secrets from env", "only import
  packages that exist") is injected into every Developer prompt.
- **Design explanation** (`app/design_explain.py`) — plain-English "what we
  designed & why" for the user (no code, no jargon).

### Files created / changed in Week 4

- `app/codegen.py` (new) — multi-provider routing + fallback + CODEGEN_MODE
- `app/developers/agents.py`, `app/developers/orchestrator.py` (new)
- `app/design_explain.py` (new) — headline + plain-English design explanation
- `app/architect/builder.py` — foundation tickets, llm_routing (integration→Gemini)
- `app/models.py` — GeneratedFile + PipelineStatus tables
- `app/main.py` — /pipeline/build, /pipeline/{id}/build-status,
  /pipeline/{id}/design-explanation; design→explanation→build chaining
- `app/schemas.py` — BuildStatus + DesignExplanation models
- `app/config.py` — anthropic/gemini keys, codegen_mode, codegen_cheap_model
- `alembic/versions/0005_developers.py` — generated_files + pipeline_status
- `requirements.txt` — anthropic, google-generativeai
- `frontend/app/page.tsx` — design-complete message + collapsible "See what we
  designed & why" → "Building your app…" + file list + X of Y (no code shown)
- `.env.example` / `docker-compose.yml` — ANTHROPIC_API_KEY, GEMINI_API_KEY,
  CODEGEN_MODE

### New database (Week 4)

- `generated_files` (id, project_id, ticket_id, filename, filepath, content,
  agent_type, status, created_at) — status: generated | needs_review
- `pipeline_status` (id, project_id, stage, status, started_at, completed_at,
  error_message)

### What now works end to end

Full pipeline: **BA → Product Intelligence review-gate → "Build it" → Architect
(Designing your app…) → design-complete message + collapsible plain-English
explanation → Developer agents (Building your app… X of Y files) → ready.**
Files are stored in generated_files; the user never sees code.

### CODEGEN_MODE (cost control)

- `real` (default) — honours the locked routing (Claude for UI). ~$1.40/build.
  Use for demos.
- `cheap` — redirects every code-gen call to gemini-2.5-flash-lite. ~$0.02/build.
  Use while testing. Currently set to `cheap` in .env.
- The blueprint still records the _intended_ model; only the call is swapped.
- Self-review always runs on gemini-2.5-flash-lite (halves Claude calls).

### Measured findings (real builds)

- Claude Sonnet = best UI code (typed, validated, correct Next.js routing).
- Gemini Flash-Lite = clean, FastAPI-consistent integration code, very cheap.
- GPT-4o backend was fine ONCE the contract existed — the contract, not the
  model, fixed the bugs.
- The contract eliminated: cross-file field drift (total_amount vs price),
  redefined models, hallucinated imports (starlette.rate_limiting), Flask-in-
  FastAPI, insecure CORS. Verified across all 3 domains.
- Cost reality: Claude ≈ $0.14/call (400-500 line files); an all-Claude build
  ≈ $3-4. Hence CODEGEN_MODE.

### Known gaps (for later weeks)

- Generated code is a strong FIRST DRAFT, not a runnable app: nothing writes the
  files to disk, installs deps, assembles or runs them (that's DevOps #11).
- Absolute imports (`backend.app.models`) may need packaging fixes — Code
  Reviewer's job.
- No code export to disk yet (core rule: "full code export always available").

---


**Week 5 — Code Reviewer (#9) — DONE**
Two-pass review over every generated file, auto-chained after the Developer
build. Verified end to end (7/7 files secured, certificate issued) plus a
manually-planted SQL-injection test that was caught and fixed. Checklist 8/8.

### New agent / layer (Week 5)
- **Code Reviewer** (`app/reviewer/reviewer.py`) — per file:
  - PASS 1 general (mid-tier model from blueprint llm_routing.code_reviewer,
    respects CODEGEN_MODE): correctness, error handling, performance,
    scalability, readability.
  - PASS 2 security (**ALWAYS claude-opus-4-8, hardcoded, bypasses cheap mode**):
    auth bypass, SQL/code injection, cross-tenant data exposure, payment
    manipulation, exposed secrets, missing encryption, missing authorization.
  - Severity routing: minor/medium → auto-fix & continue; critical → STOP,
    fix with Opus, re-run the security review, only pass when clean.
  - The reviewer writes the fix directly (Opus fixes security issues); every
    issue is logged in code_reviews.
- **Reviewer orchestrator** (`app/reviewer/orchestrator.py`) — reviews all files
  (concurrency 3), records code_reviews, updates fixed file content, issues the
  security certificate, and sets project status `secured` / `security_blocked`.

### Files created / changed in Week 5
- `app/reviewer/reviewer.py`, `app/reviewer/orchestrator.py`, `app/reviewer/__init__.py` (new)
- `app/codegen.py` — added `bypass_cheap` param (security must never use a cheap model)
- `app/models.py` — CodeReview table
- `app/main.py` — /pipeline/secure, /pipeline/{id}/security-status; _run_review
  chains after build; stores security_cert in Redis
- `app/schemas.py` — SecurityStatusResponse
- `alembic/versions/0006_code_reviews.py` — code_reviews table
- `frontend/app/page.tsx` — build→secure handoff; "Making sure everything is
  safe and secure…" → "Security check passed ✓" + final message (NO model names)

### New database (Week 5)
- `code_reviews` (id, project_id, file_id, issues_found, issues_fixed,
  security_passed, reviewed_by_model, created_at)

### What now works end to end
Full pipeline: **BA → PI review-gate → Build it → Architect (Designing…) →
design explanation → Developers (Building… X of Y) → Code Reviewer (Making sure
everything is safe and secure…) → Security check passed ✓.** Security review
always runs on Opus 4.8; a security certificate JSON is issued
(`{passed, model_used: claude-opus-4-8, issues_found, issues_fixed,
files_reviewed, timestamp}`); the user never sees code, agent names, or model
names. issues_fixed is clamped so it can never exceed issues_found.

### Cost note (Week 5)
Security review runs Opus on EVERY file and ignores CODEGEN_MODE by design, so a
full build's security pass costs real Opus money (~$0.30-0.60 for ~7 files,
~$1-2 for a large build). Test on small ideas; the machinery is proven.

### Current phase
**Week 6 — (see Weekly Claude Code Prompts v2).** Likely QA Agent (#10) and/or
Design Review (#8). QA/Docs/Cost use Gemini 2.5 Flash-Lite per the updated
routing. Also still pending: Qdrant vector store, code export to disk, and the
DevOps deploy step that turns generated files into a running/hosted app.

### What NOT to touch next session
- Do NOT modify the BA, Product Intelligence, Architect, Developer, or Code
  Reviewer agents unless the new week requires it — all tested and locked.
- Do NOT change existing schemas or migrations (0001–0006), the Redis
  conversation/pipeline/build/secure state formats, or the /conversation/* and
  /pipeline/* endpoint contracts.
- Do NOT weaken the BINDING PROJECT CONTRACT or the foundation-first ordering.
- Security review is ALWAYS claude-opus-4-8 and must always keep bypass_cheap —
  never let CODEGEN_MODE or budget downgrade it.
- Do NOT change CODEGEN_MODE defaults (`real` stays the default) or the locked
  routing.
- Do NOT build QA, Design Review, DevOps, Documentation, Monitoring, Auto-fix,
  or Cost Tracker agents until their week.

### What I learned — Week 5
- Separation of concerns in review: one pass judges quality (cheap model), a
  second pass judges ONLY security (the expensive, best model). Keeping them
  separate means security is never diluted by or traded off against cost.
- A hardcoded, non-negotiable rule needs an escape hatch in the plumbing, not in
  the policy: the cheap-mode override had to gain a `bypass_cheap` flag so the
  security pass could always reach Opus even when everything else is downgraded.
- Detect-and-fix beats detect-and-flag: having the security model (Opus) both
  find AND fix the vulnerability, then re-review its own fix, is cheaper and
  safer than bouncing the file back to a cheaper Developer that might reintroduce
  the bug.
- Trust-but-verify loop: on a critical issue, don't just fix — re-run the review
  to confirm the fix, bounded by a retry cap, then block the pipeline if it
  still fails. Never silently pass security.
- Cost is a hard constraint even for security: Opus-on-every-file is expensive,
  so it must be reserved for what truly needs it and tested on small builds.

### What I learned — Week 4

### What I learned — Week 4

- Parallel agents need a dependency graph: asyncio runs independent tickets
  simultaneously while dependents wait — that's just a topological sort with
  `asyncio.gather` per wave.
- The biggest lesson: **LLM agents generating files in isolation will always
  drift** — each invents its own field names, imports and framework. The fix
  isn't a smarter model, it's a **shared contract**: freeze the schema, the
  endpoints and the module layout, build the foundation first, and feed that
  real code into every other agent's prompt. Swapping Claude in fixed less than
  the contract did — proven by backend going back to GPT-4o and staying clean.
- Multi-provider routing is worth it, but model ids rot fast (Gemini retired
  two ids on us; Claude deprecated `temperature`). Use "-latest" aliases and
  always degrade gracefully rather than crash.
- Cost is an engineering constraint, not an afterthought: an all-Claude build
  is ~$3-4 because output tokens dominate. Routing the cheap yes/no self-review
  to a budget model and keeping the premium model only where quality is visible
  (the UI) cut spend ~70% with no quality loss.
- Self-review + bounded retries (3 tries then flag `needs_review`) means the
  pipeline never silently ships broken work.

### What I learned — Week 3

- An AI agent shouldn't be a rigid form-filler. The big lesson was splitting
  UNDERSTANDING (LLM: classify the idea, extract clean facts) from CONTROL
  (deterministic rules: which question next, what to skip). Rules on top of LLM
  understanding gave us adaptivity (skip irrelevant questions, gate research)
  without the hallucination risk of a fully LLM-driven flow.
- The pipeline is three specialized agents with clear boundaries: the BA
  collects and understands, Product Intelligence reasons about the product
  (budget reality, relevance, priorities, gaps) as a safety net, and the
  Architect turns the clean spec into a concrete technical blueprint. Each has
  its own locked model/temperature — cheap model for chat, bigger models for
  design and analysis.
- Security is designed into the blueprint (auth, validation, rate limiting,
  encryption, secrets, OWASP), not bolted on later — and the plan still routes
  the actual security review to Claude Opus 4.8, per the core rule.
- Recommendations need teeth: Product Intelligence can flag "$5 can't run this",
  but it only matters if the user can act on it — hence the "Start smaller"
  action that actually downgrades the build before the Architect sizes it.

---

## END-OF-WEEK PROCESS — ALWAYS FOLLOW

After each week's build passes its testing checklist, run these
three prompts in order:

1. **Update memory** — mark the week done, list files created,
   list what works, set next phase, list what not to touch.
2. **Teach me** — explain what was built in plain interview-ready
   language I can say out loud to a technical interviewer.
3. **Next session start** — "Read CONTEXT.md. Week X done. Today
   building Week X+1 only."

---

---

## FUTURE OPTIMIZATIONS — after demo is complete

### 1. Competitive Intelligence refactor

Current: Google Places API + Yelp API + GPT-4o mini
Future: Gemini 3.5 Flash with native Google Search
grounding — one API call replaces all three
Reason: simpler architecture, fewer dependencies
Status: DO NOT TOUCH until demo is recorded

### 2. Gemini routing for Weeks 4 onwards

- Integration Developer: Gemini 2.5 Flash-Lite
- QA Agent: Gemini 2.5 Flash-Lite
- Documentation Agent: Gemini 2.5 Flash-Lite
- Cost Tracker Agent: Gemini 2.5 Flash-Lite
  Reason: $0.10/$0.40 per MTok — cheapest option
  for simple generation tasks

### 3. Native App Store submission automation (post-demo)

Researched: Apple App Store Guideline 4.2.6 explicitly forbids
app-generation platforms from submitting apps on clients' behalf
under a shared/platform-owned developer account. This is a hard
rule, not a gray area — violating it risks app rejection and
platform account bans. Confirmed via Apple's official guidelines
and how Bubble/GoodBarber/Adalo comply.

CORRECT approach (already matches our BA-stage design):

- Each user must have their OWN Apple Developer account ($99/yr),
  disclosed at BA stage — already implemented correctly.
- Future automation opportunity: once the user has their own
  account, automate build packaging + App Store Connect
  submission using THEIR OWN API keys (same pattern Bubble uses).
- Do NOT build a shared/platform-owned Apple Developer account
  submission pipeline. Explicitly against Apple policy.
  Status: Not needed for demo. Real DevOps feature for later,
  scoped correctly — automating the user's account, not replacing it.

## MODEL SWITCH — scheduled for after Week 8

Do NOT switch any model before Week 8 is complete.
All current routing (GPT-4o / GPT-4o mini / Gemini 2.5
Flash-Lite / claude-sonnet-4-6 / claude-opus-4-8) stays
exactly as-is through Weeks 4-8.

After Week 8 passes testing, switch to VERIFIED model
strings in one dedicated session, retest each agent
individually before moving to the next:

1. BA Conversation → GPT-5.6 Luna
2. Product Intelligence → GPT-5.6 Terra
3. Architect → claude-opus-4-8 (upgrade from GPT-4o)
4. Backend Developer → claude-sonnet-5 (upgrade from GPT-4o)
5. Frontend Developer → claude-sonnet-5 (from 4.6)
6. Mobile Developer → claude-sonnet-5 (from 4.6)
7. Integration Developer → GPT-5.6 Terra (from Gemini Flash-Lite)
8. Design Review → claude-sonnet-5 (from 4.6)
9. Code Reviewer (general) → GPT-5.6 Luna
10. Code Reviewer (security) → claude-opus-4-8 — UNCHANGED, never switch
11. QA Agent → claude-sonnet-5 (from Gemini Flash-Lite)
12. DevOps → GPT-5.6 Luna
13. Documentation → claude-haiku-4-5-20251001
14. Monitoring → Gemini 2.5 Flash-Lite — UNCHANGED
15. Auto-fix → claude-opus-4-8 (upgrade from GPT-4o)
16. Cost Tracker → Gemini 2.5 Flash-Lite — UNCHANGED

Always use full versioned model strings, never generic
aliases (e.g. claude-sonnet-5 not claude-sonnet).

---

## COST OPTIMIZATION — safe now vs test-before-trusting

Two categories. Do not treat them the same.

### SAFE TO IMPLEMENT ANYTIME — zero quality impact, pure savings

1. **Prompt caching on the BINDING PROJECT CONTRACT**
   The contract (schema, endpoints, module layout) is sent to
   every Developer agent ticket. Cache it. Cache hits bill at
   ~10% of normal input cost. Same content, same output quality,
   pure savings. Highest priority — implement first.

2. **Batch API for non-blocking agents**
   50% off both input and output, up to 24hr turnaround.
   Use for: Documentation, Monitoring, Cost Tracker, and any
   other background agent that isn't blocking a live user in
   a conversation. Do NOT use for BA conversation (user is
   waiting in real time).

3. **Context trimming — ONLY if genuinely irrelevant**
   Strip context an agent doesn't need for its specific job
   (e.g. don't send frontend styling details to Backend Dev).
   Requires care — trimming context the agent actually needs
   to make a good decision WILL hurt quality. Verify per agent
   before trusting.

### TEST BEFORE TRUSTING — has a real quality tradeoff, must verify

4. **Effort parameter (low/medium/high)**
   Lower effort = less internal reasoning = cheaper but can
   produce worse output on complex tasks. This is NOT free
   money like caching.
   - Keep HIGH effort: Architect, security review, any ticket
     requiring real judgment
   - Test LOWER effort only on: mechanical/repetitive tickets
     already fully constrained by the binding contract (little
     judgment left to exercise since contract dictates the
     structure)
   - Must compare output quality before locking in — same
     process as the Week 8 model switch testing.

5. **Finer-grained cheap/real routing (beyond current CODEGEN_MODE)**
   Current split is real vs cheap at the mode level. Next level
   is per-ticket-complexity: simple integration glue → cheap
   model, complex/high-stakes tickets (e.g. payment flow) →
   real model. Decide per ticket TYPE, not blindly. Risk: routing
   something important to the cheap model silently drops quality
   on that specific piece.

### CORE PRINCIPLE — never compromise on this

Cost optimization touches the HOW (caching, batching, routing
mechanics) — never the WHAT a model is capable of doing on
tasks that matter. Security review stays Claude Opus 4.8 at
full effort, no exceptions, regardless of any optimization pass.
Savings come from not paying for the same reasoning twice —
not from asking for less reasoning where it counts.

### Implementation priority when we get to it

1. Prompt caching on the contract (do this first — biggest win)
2. Batch API for background agents
3. Effort level testing (test-then-lock, not assume-then-ship)
4. Finer cheap/real routing granularity

Status: NOT YET IMPLEMENTED. Revisit after Week 8 model switch
testing, same session or the one right after.

## POST-REVIEW DESIGN DECISIONS — external review synthesis

Based on independent review from two AI models, converged
recommendations below. Confirmed decisions to implement.

### 1. Authentication — delegate, don't roll custom

Drop custom password hashing in generated apps. Architect
generates an auth ticket instructing Backend Dev to integrate
a third-party identity provider (Auth0 / Clerk / AWS Cognito)
instead of building auth from scratch.
Tiering logic stays as designed:

- Basic tier: standard provider auth (email/password via provider)
- 2FA required tier: triggered when payments, PII, or employee
  data are present in the app's feature set
- Passkey support: offered as a Scale-tier default
  Reason: non-technical users' apps should never have custom-built
  credential handling — a provider gives a secure, standardized
  baseline (OAuth2/OIDC, built-in MFA) without risking Developer
  Agent implementation flaws.

**STATUS: ✅ IMPLEMENTED — 2026-07-20.** Default provider = **Auth0**
(documented: standards-based OIDC works uniformly across ALL THREE targets the
platform generates — FastAPI backend, Next.js web, React Native mobile — with
built-in MFA + passkeys; Clerk / AWS Cognito kept as switchable alternatives via
`AUTH_PROVIDER` in `architect/builder.py`). The Architect now emits an **AUTH-1**
ticket on every build instructing Backend Dev to delegate auth (NO bcrypt/JWT
hand-rolling — validate provider JWKS tokens instead); the security section's
auth measure and SEC-1 wording were rewritten to match, and the Architect LLM
prompt now tells the model not to generate custom-auth tickets. Tiering wired to
the feature set (`_auth_tier()`): `basic` (provider auth) → `2fa_required` when
payments / PII / employee data are present → passkeys as the **Scale-tier
default**. Verified across 8 domains offline (see the implementation-session
section below).

### 2. Architect Agent — promote to top-tier model

Move Architect from GPT-4o to claude-opus-4-8 (already planned
in MODEL SWITCH section — this confirms and prioritizes it).
Reason: a flawed blueprint gets perfectly executed by downstream
agents. Security-tier reasoning is needed at the design stage,
not just at the code-review stage — a wrong schema or API
paradigm can't be patched by even the best security review later.

**STATUS: ⏳ STILL PENDING — deliberately NOT pulled forward.** In the
2026-07-20 implementation session, items §1 (auth) and §3 (Stripe Connect) were
pulled forward as an exception because they are FEATURE/ticket-template changes.
This item is a MODEL-ROUTING change, so it was intentionally left on the
post-Week-8 batch model switch (see "MODEL SWITCH — scheduled for after Week 8",
line item #3: Architect → claude-opus-4-8). Rationale for the split: do not mix
model-routing changes with feature changes in the same session — model swaps
need their own retest pass, agent-by-agent, per the Week-8 process. The Architect
remains **GPT-4o @ 0.2** for now (`config.py` `architect_model`), unchanged.

### 3. Stripe integration — in-app Connect flow, not platform-mediated

When Architect detects payment intent (explicit or implied,
e.g. "tip"), it generates a real Stripe Connect OAuth ticket
for the GENERATED APP itself — not a platform-side connection.

Flow:

- Business owner's own deployed app has a "Connect Stripe"
  action (e.g. in an admin/settings screen)
- Owner clicks it, gets redirected to Stripe's own hosted OAuth
  flow, connects their own Stripe account directly
- Token is stored in the app's own database, encrypted, never
  touches the platform or any Developer Agent's output directly
- Payment UI (e.g. "Pay Now" buttons) ships VISIBLE but DISABLED
  before Stripe is connected, showing: "Connect Stripe to start
  accepting payments" with a link to the connect flow
  (Option A — chosen over fully hiding payment UI pre-setup,
  for transparency)

Reason: platform never touches user payment credentials at all —
not even a token. Reduces platform liability significantly. Also
matches the "fully exportable, no vendor lock-in" core rule —
since the connection lives inside the generated app's own code,
exporting/self-hosting the app later doesn't break payments.

Tradeoff to track: this makes Stripe Connect a real generated
FEATURE (OAuth handler + secure token storage + settings screen),
not just a setup instruction. Code Reviewer's security pass
(Week 5) must specifically verify this ticket — encrypted token
storage, correct OAuth implementation, no credential leakage in
generated code.

Documentation Agent (Week 8) must cover "how to connect your
Stripe account" in the handoff guide, since the app ships in a
payments-visible-but-not-yet-connected state.

**STATUS: ✅ IMPLEMENTED — 2026-07-20.** When the Architect detects payment
intent (explicit or implied — "leave a tip" is caught via a word-boundary
regex), it now emits, for the GENERATED APP (never the platform):
- a **Stripe Connect** `third_party_apis` entry (`who_handles: user`,
  `connection: in_app_oauth`) — replacing the old plain-Stripe "paste your secret
  key" entry;
- an encrypted-token table **`stripe_accounts`** (`access_token_encrypted`, no
  plaintext token column) and **OAuth endpoints** (`/admin/stripe/connect`,
  `/admin/stripe/callback`, `/admin/stripe/status`) — injected into the blueprint
  schema/endpoints so they are frozen into the BINDING CONTRACT;
- a backend ticket **PAY-1** (OAuth handler + encrypted token storage in the
  app's OWN DB, token enc key from env, never logs/returns tokens) and a frontend
  ticket **PAY-2** (Settings "Connect Stripe" action + payment UI **VISIBLE but
  DISABLED** until connected, with the exact copy "Connect Stripe to start
  accepting payments" — Option A);
- a `security.payment_security` block flagging the feature, and
  `security_critical: true` + `security_focus` on the PAY tickets.

**No platform-side Stripe connection exists** — the platform never touches a
Stripe credential or token. The **Code Reviewer** was given a minimal, targeted
hook: `_is_payment_sensitive()` detects PAY-* / stripe-path files and appends a
payment-specific checklist to the ALWAYS-Opus security pass (verify encrypted
token storage, correct OAuth with signed state param, no credential leakage).
Verified offline (payment + non-payment domains + 8-scenario gating). Files:
`architect/builder.py`, `reviewer/reviewer.py`, `design_explain.py`.

### 4. Not changing (deliberate, despite feedback)

- Cheap-model self-review stays as-is: Week 4 data (20/20 files,
  0 needs_review) validates it works for contract-compliance
  checks specifically. Reviewer concern ("dumb boss problem")
  applies more to open-ended judgment review — relevant for the
  real Code Reviewer agent (Week 5), not self-review.
- Flat-fee unlimited changes stays as-is: deliberate differentiator
  against competitor credit-fatigue complaints identified in
  original market research. Not reversing without real usage data.

### 5. Open, not yet decided

- Regulatory compliance detection (HIPAA/PCI/GDPR) — only one
  reviewer raised this. Architect currently detects payments but
  not health-data or EU-user scenarios. Real gap, new scope,
  revisit before building anything in a regulated-data domain.
  (Note: after 2026-07-20, the Architect's `_auth_tier()` DOES now flag
  health/PII feature words to force 2FA — a partial step, but full
  HIPAA/PCI/GDPR compliance detection is still unbuilt.)

## POST-REVIEW IMPLEMENTATION SESSION (2026-07-20) — auth + Stripe Connect pulled forward

**This was NOT a numbered week.** A dedicated session to close a gap: three
POST-REVIEW DESIGN DECISIONS were *confirmed* in CONTEXT.md but never *built*
(they were decided after Week 5 was locked). Two of the three were implemented
here; the third was deliberately deferred.

### What was implemented
1. **Stripe → Stripe Connect (in-app OAuth)** — POST-REVIEW DECISION §3. See the
   ✅ marker there for the full behavior. Platform touches NO Stripe credential.
2. **Custom auth → delegated auth (Auth0 default)** — POST-REVIEW DECISION §1.
   See the ✅ marker there. Tiered: basic → 2FA (payments/PII/employee) →
   passkeys (Scale default).
3. **Architect model tier — DELIBERATELY NOT pulled forward** (POST-REVIEW
   DECISION §2). It is a model-routing change and stays on the post-Week-8 batch
   switch. Items 1 & 2 are feature/ticket-template changes and were safe to pull
   forward; mixing a model swap into the same session would break the "swap one
   model, retest, then the next" Week-8 discipline. Architect stays GPT-4o @ 0.2.

### Files created / changed
- `backend/app/architect/builder.py` — the bulk of the work:
  - `AUTH_PROVIDER` (Auth0) + `_auth_tier()` (basic / 2fa_required / scale from
    payments/PII/employee signals + plan) + `_auth_ticket()` (AUTH-1).
  - `_third_party_apis()` now emits **Stripe Connect** (in-app OAuth), not plain
    Stripe; `_mentions_payment()` + `_TIP_RE` catch implied payments ("leave a
    tip") without false positives ("multiple").
  - `_stripe_connect_schema()` (encrypted-token table) + `_stripe_connect_endpoints()`
    (OAuth routes), merged into the blueprint so they enter the BINDING CONTRACT.
  - `_payment_tickets()` (PAY-1 backend, PAY-2 frontend visible-but-disabled UI),
    both flagged `security_critical` + `security_focus`.
  - `_security_section()` rewritten: delegated-auth measure (no bcrypt), MFA /
    passkey measures, `payment_security` flag block; now takes `auth`.
  - `_security_ticket()` (SEC-1) reworded to authorization-only (auth is AUTH-1).
  - `_ARCH_SYSTEM` LLM prompt told NOT to generate custom-auth/payment tickets.
- `backend/app/reviewer/reviewer.py` — minimal, targeted: `_is_payment_sensitive()`
  + `_PAYMENT_SECURITY_FOCUS`; the ALWAYS-Opus security pass appends the payment
  checklist for PAY-*/stripe files. (No other Reviewer logic touched.)
- `backend/app/design_explain.py` — Stripe name check made substring-tolerant so
  "Stripe Connect" still lights up "protects_payments".
- `backend/tests/test_architect_offline.py` — NEW. Offline (zero-LLM-spend)
  gating test; monkeypatches `llm.complete_json`→None to force the deterministic
  path. Run: `docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" backend python tests/test_architect_offline.py`.

### What was tested (all PASS, zero LLM spend)
- **Payment domain** (coffee shop w/ online ordering + tips): Stripe Connect
  entry, PAY-1/PAY-2 tickets, `stripe_accounts` table w/ `access_token_encrypted`
  (no plaintext col), 3 OAuth endpoints, `payment_security` flag, PAY-2
  visible-but-disabled + exact copy, MFA required. No platform-side Stripe.
- **Non-payment domain** (personal recipe box, single user): no Stripe anything,
  auth tier `basic`, AUTH-1 still present, all blueprint sections intact, Opus
  security, no bcrypt. Nothing regressed for non-payment apps.
- **8-scenario gating suite** (reconstructed at the Architect layer — the prior
  suite was ad-hoc/LLM-driven and never committed): B2B SaaS, internal staff
  tool, telehealth, native mobile, tipping, budget-mismatch, personal tool,
  public newsletter. Invariants held for all 8: security ALWAYS Opus,
  foundation-first (FND-1/FND-2), exactly one AUTH-1, no custom-auth, valid cloud
  tier, payment/mobile detection matches expectation, MFA where sensitive.
- **Reviewer flag** unit checks: PAY-*/stripe/oauth paths flagged; ordinary files
  not.
- **Full-app boot**: `app.main` imports clean; backend rebuilt (`docker compose
  build backend`) and `/health` → 200 with the fresh code confirmed in-container.
- NOTE: tests run OFFLINE against the deterministic path (which is where 100% of
  these changes live). No live BA→PI→Architect LLM run was made — that costs real
  OpenAI money and exercises unchanged upstream logic. A real Architect call
  concatenates the same deterministic overlay onto real creative output (plain
  list/dict merges), so real-creative behavior matches the mock path.

### What I learned — Post-review implementation session (2026-07-20)
- **Liability is an architecture decision, not a checkbox.** Moving Stripe from
  "platform collects your secret key" to Stripe Connect in-app OAuth means the
  platform never holds a payment credential at all. The safest way to handle a
  secret is to design the system so you never receive it — the token lives
  encrypted in the generated app's own DB, and self-hosting later doesn't break
  payments (it aligns with the no-lock-in rule for free).
- **"Don't roll your own crypto" generalizes to "don't roll your own auth."** The
  fix wasn't a better password-hashing prompt — it was deleting custom auth
  entirely and delegating to a provider (OAuth2/OIDC + built-in MFA/passkeys).
  Removing the capability to get it wrong beats trying to get it right.
- **A flag is only useful if the consumer reads it.** Marking PAY tickets
  `security_critical` in the blueprint is inert unless the Code Reviewer acts on
  it. The closing move was the tiny `_is_payment_sensitive()` hook that turns the
  flag into an actual extra checklist on the Opus pass. Producer + consumer, or
  it's just decoration.
- **Sequencing changes by TYPE prevents debugging hell.** Pulling forward two
  feature changes while holding the model-routing change for its own session is
  deliberate: if the Architect blueprint later looks wrong, you want to know
  whether it was the new tickets or a new model — never both at once. Same
  discipline as the Week-8 "swap one model, retest, next" plan.
- **Keyword detection needs word boundaries, not substrings.** "leave a tip" must
  trigger payments; "multiple" must not. `\btip(s|ped|ping)?\b` does both; a bare
  `"tip" in blob` fails silently and expensively (a payment feature nobody asked
  for, or a missed one). Cheap offline tests caught this in one run.
- **Test where the change lives, for free.** All logic here is deterministic, so
  monkeypatching the LLM to None gave a fast, $0, fully-deterministic 8-domain
  suite — far more reliable than burning credits on non-deterministic LLM runs to
  test rules that never call the LLM anyway.

### What NOT to touch (carried forward + additions)
- Everything in the Week-5 "What NOT to touch" list still holds.
- Do NOT switch the Architect model (or any model) before Week 8 — §2 above is
  intentionally deferred.
- The delegated-auth mandate (no custom password hashing/JWT) and the
  platform-never-touches-Stripe rule are now core: do not reintroduce custom auth
  or any platform-side Stripe connection.

## REFERENCE — NOT FOR CLAUDE CODE TO RE-READ EVERY SESSION

The full Master Blueprint v2 document (mission, all 15 agents in
full detail, every market problem solved, full interview
preparation, complete tech stack reasoning) is kept separately
on the builder's computer. It is not uploaded into this project.
This CONTEXT.md is the condensed version Claude Code needs.


---
---

# COMPREHENSIVE SESSION HANDOFF — pick-up guide for a fresh engineer
_(Written at end of the session that built Weeks 3, 4, 5. Read this to resume
with zero prior context. The per-week sections above have the summaries; this
section adds the full "how it actually works, what's half-done, and the traps".)_

## 0. HONESTY NOTE on "auth / Architect-tier / Stripe Connect decisions"

> **UPDATE — 2026-07-20 (post-review implementation session):** two of these three
> are now BUILT. Auth (delegated identity provider) and Stripe Connect (in-app
> OAuth) were implemented in a dedicated session — see
> **"POST-REVIEW IMPLEMENTATION SESSION (2026-07-20)"** below and the ✅ IMPLEMENTED
> markers in POST-REVIEW DESIGN DECISIONS §1 and §3. The Architect model-tier
> upgrade (§2) was DELIBERATELY left for the post-Week-8 batch switch. The
> paragraph below describes the code as it stood at the end of the Weeks 3–5
> session and is kept for history; the auth/Stripe bullets are now superseded.

These were requested in the earlier handoff prompt, but that (Weeks 3–5) session
did NOT hold a distinct discussion or make explicit decisions on those three. To
avoid misleading a new engineer, here is what existed in the code AT THAT TIME
(behavior, not a debated decision):
- **Auth:** no real auth system exists on the PLATFORM itself (no login for the
  AI-org tool). The GENERATED apps' code includes auth (password hashing, JWT,
  Depends-based checks) because the Architect's security section mandates it and
  the Code Reviewer enforces it — but that is generated output, not platform auth.
- **Architect "tiers":** the Architect's cloud_config has three sizes —
  small ($15, 1 vCPU/1GB), medium ($50, 2 vCPU/4GB), large ($150, 4 vCPU/8GB +
  load balancer + autoscaling) — chosen deterministically from budget + plan +
  user count (see `app/architect/builder.py` `_decide_tier`/`_cloud_config`).
  These map to the BA "Quick/Production/Scale" plans.
- **Stripe:** the Architect adds plain **Stripe** (NOT Stripe Connect) to
  `third_party_apis` when payments are detected, marked `who_handles: user` with
  plain-English setup steps. Stripe Connect was never discussed or built.

## 1. HOW TO RUN / RESUME
```
cd "…/ai-org"
docker compose up -d           # after backend code edits: docker compose build --no-cache backend && docker compose up -d
```
- Platform UI (the AI-org tool): http://localhost:3000
- API: http://localhost:8000  · interactive docs: http://localhost:8000/docs
- 4 containers: backend (8000), frontend (3000), postgres (5432), redis (6379).
- Migrations auto-run on backend start (`alembic upgrade head`). Currently 0001–0006.
- `.env` holds real keys (OPENAI, GOOGLE_PLACES, YELP, ANTHROPIC, GEMINI) and
  `CODEGEN_MODE`. `.env` is gitignored; only `.env.example` (blank) is committed.
- GitHub: PRIVATE repo `Rajkumar2002-Rk/ai-org` (branch master). `.gitignore`
  excludes `.env` and `practice/` (the user's personal study notes). Commits use
  the user's identity only — **do NOT add a Co-Authored-By/Claude line** (user rule).

## 2. THE FULL PIPELINE (end to end, all verified this session)
User flow, each stage, and the endpoint/table behind it:
1. **BA conversation** (`app/ba/`) — deterministic LangGraph turn engine +
   Python controller owning question order; an LLM "understanding" layer
   classifies + extracts. Endpoints: POST /conversation/start,
   POST /conversation/message, GET /conversation/{id}/research-status. State
   lives in Redis (`ba:state:{id}`, 7-day TTL). On confirm it writes
   requirements + design_preferences, and the full summary JSON to
   `projects.summary_json`.
2. **Product Intelligence review-gate** (`app/product_intel/`) — POST
   /pipeline/review runs PI (GPT-4o @0.4 + deterministic budget check), returns
   recommendations, refines summary_json (prunes features, adds priorities +
   missing_essentials), writes `product_reviews`. Frontend shows a review card
   with a "Start smaller" downgrade button when budget is tight.
3. **Architect** (`app/architect/`) — POST /pipeline/start (optional
   `plan_override`) runs GPT-4o @0.2 hybrid builder → blueprint (tech_stack,
   database_schema, api_endpoints, third_party_apis+setup_steps, sprint_tickets,
   `security` section, llm_routing, cloud_config). Stored in `blueprints`.
   Redis `pipeline:status:{id}`. Also generates a plain-English design
   explanation (`app/design_explain.py`) stored at Redis `design_explain:{id}`,
   exposed via GET /pipeline/{id}/design-explanation.
4. **Developers** (`app/developers/`) — POST /pipeline/build runs 4 agents
   (backend/frontend/mobile/integration) in asyncio dependency waves. Foundation
   tickets (FND-1 models.py, FND-2 database.py) run FIRST; their real code + a
   BINDING CONTRACT are injected into every later agent. 5-step process per
   ticket (read→reuse→chunked code→self-review→store); recovery 3 tries then
   `needs_review`. Files → `generated_files`. Redis `build:status:{id}`. Progress
   via GET /pipeline/{id}/build-status (filenames + X of Y; NO code to user).
5. **Code Reviewer** (`app/reviewer/`) — POST /pipeline/secure auto-triggered by
   the frontend when build is done. Two passes PER FILE: Pass 1 general
   (mid-tier, respects CODEGEN_MODE), Pass 2 security (**ALWAYS claude-opus-4-8,
   bypasses cheap mode**). Fixes minor/medium automatically; critical → stop,
   fix with Opus, re-review, block if unresolved. Writes `code_reviews`, updates
   fixed file content, issues a security certificate (Redis `security_cert:{id}`),
   sets project `secured` / `security_blocked`. Status via GET
   /pipeline/{id}/security-status. UI shows only "Making sure everything is safe
   and secure…" → "Security check passed ✓" + a fixed user message. NO model names.

## 3. DATA MODEL (Postgres tables; models in `app/models.py`)
- `projects` (id, prompt, status, **summary_json**, created_at) — status flows:
  created→gathering_requirements→requirements_confirmed→reviewed→designed→
  built→secured (or rejected / security_blocked).
- `conversations`, `requirements` (source, is_locked), `design_preferences`.
- `blueprints` (blueprint_json), `product_reviews` (review_json).
- `generated_files` (ticket_id, filename, filepath, content, agent_type, status).
- `pipeline_status` (stage, status, started_at, completed_at, error_message).
- `code_reviews` (file_id, issues_found, issues_fixed, security_passed,
  reviewed_by_model).
Redis keys: `ba:state:{id}`, `ba:ci:{id}`, `pipeline:status:{id}`,
`design_explain:{id}`, `build:status:{id}`, `secure:status:{id}`,
`security_cert:{id}`.

## 4. MODELS / ROUTING / CODEGEN_MODE (important + non-obvious)
- Multi-provider layer: `app/codegen.py` — routes by model name: `claude-*`→
  Anthropic, `gemini-*`→Google, else OpenAI. Graceful fallback to GPT-4o if a
  provider errors; deterministic stub if none. `app/llm.py` is the SEPARATE
  BA/PI wrapper (OpenAI only: chat, complete_json, moderate).
- Blueprint llm_routing (current, matches CONTEXT locked routing): backend=gpt-4o,
  frontend=claude-sonnet, mobile=claude-sonnet, integration=gemini-2.5-flash-lite,
  code_reviewer=gpt-4o-mini, security_review=claude-opus-4-8.
- **Real model IDs actually called** (these ROT — Google/Anthropic retire ids):
  claude-sonnet→`claude-sonnet-5`; claude-opus-4-8→`claude-opus-4-8`;
  gemini-2.5-flash-lite→`gemini-flash-lite-latest` (use the -latest alias, dated
  ids get retired). Anthropic calls must NOT send `temperature` (newer models
  reject it). See `_ANTHROPIC_IDS`, `_GEMINI_IDS` in codegen.py.
- **CODEGEN_MODE** (`.env`): `real` (default) honors routing; `cheap` redirects
  every codegen call to gemini-flash-lite-latest (~$0.02/build). Currently set to
  `cheap`. Set to `real` for demos. `bypass_cheap=True` in codegen.generate
  disables the override — used ONLY by the security pass (Opus must never be
  downgraded). Self-review always runs on Gemini (REVIEW_MODEL in agents.py).

## 5. KEY DECISIONS MADE THIS SESSION (with reasoning)
- **Smarter BA = hybrid, not a rewrite.** Deterministic controller keeps flow
  control (one question, order, safety-first); LLM adds understanding
  (classify + extract). Rejected fully-LLM-driven (hallucination risk the user
  had hit before).
- **is_local gating.** Location question + competitive research only run when the
  app is a LOCAL, customer-facing business (`is_local && customer_facing`).
  Killed the "which city?" for gambling/SaaS apps and "business near Austin"
  nonsense. Internal staff tools skip both.
- **Added ASK_PLATFORM stage** — asks "website/app/both?" only when the idea
  doesn't make it clear; "X or Y" is treated as undecided → ask.
- **Product Intelligence = review-gate screen, not a chat** (respects "BA is the
  only conversational agent"). Does all four: budget-vs-scale reality check,
  feature pruning, must/nice priorities, missing essentials.
- **Budget teeth** — PI's "Start smaller" button actually downgrades the plan
  (plan_override) before the Architect sizes cloud_config.
- **Security by design** — every blueprint carries a security section; the
  actual review is Opus 4.8.
- **BINDING PROJECT CONTRACT (the big Week-4 fix)** — freeze schema/endpoints/
  module layout, build foundation (models.py/database.py) first, inject the real
  foundation code + contract into every Developer prompt. This, not model choice,
  fixed cross-file consistency.
- **Backend model = GPT-4o (kept locked).** We A/B tested GPT-4o vs Claude for
  the backend security file; Claude was more careful, but once the CONTRACT
  existed GPT-4o stayed clean too — proving the contract did the work. User
  briefly asked to move all codegen to Claude, then reverted to the locked
  routing after seeing cost.
- **Self-review on Gemini** (cheap yes/no) to halve Claude calls per ticket.
- **Code Reviewer fixes files directly** (Opus writes the security fix and
  re-reviews its own fix) rather than bouncing back to a cheaper Developer that
  could reintroduce the bug. Issues are still logged per file for accountability.
- **CODEGEN_MODE cost switch** added so testing is ~free; `real` reserved for
  demos. Security always ignores it.

## 6. BUGS FOUND + ROOT CAUSE + FIX (this session)
- **Competitive intel produced irrelevant features / asked location on
  non-local apps.** Root cause: CI ran on any business-type+city, and location
  was always asked. Fix: `is_local && customer_facing` gate in
  `app/ba/controller.py` `_needs_market_research`.
- **classifier read "website or app" as "both"** (built a mobile app nobody
  asked for). Fix: in `understanding.classify`, "or"/ambiguous → platform
  "unknown" → ask.
- **BA stored raw junk** ("yes my store name is raja" as the name; "bro its just
  me" as user count). Fix: LLM extraction in `app/ba/understanding.py`
  (extract_name, normalize_users) + is_single_user skip.
- **Budget question then ignored** (offered $150 plan to a $20 budget). Fix:
  budget-aware plan recommendation + "Start smaller" downgrade.
- **Cross-file drift in generated code** — files disagreed on field names
  (total_amount vs price), redefined Base, hallucinated `starlette.rate_limiting`,
  used Flask in a FastAPI project, insecure CORS (`*`+credentials). Root cause:
  each agent generated in isolation. Fix: the BINDING CONTRACT + foundation-first
  (verified gone across coffee/telehealth/SaaS builds).
- **LangGraph error 'review is already a state key'** — node name collided with
  the PIState key. Fix: renamed node to `analyze` in product_intel/graph.py.
- **Anthropic 400 "temperature is deprecated for this model."** Fix: removed
  `temperature` from the Anthropic call in codegen.py.
- **Gemini 404s** — `gemini-2.5-flash-lite`/`gemini-2.0-flash` retired for new
  users. Fix: use `gemini-flash-lite-latest` alias.
- **Gemini quota `limit: 0`** — free tier not enabled on the key's project. Fixed
  by the user adding billing; the key format `AQ.` also non-standard but works.
- **Docker layer cache didn't pick up Python edits** after `up -d --build`. Fix:
  `docker compose build --no-cache backend`. REMEMBER THIS TRAP.
- **issues_fixed > issues_found** in code_reviews — re-review fixes inflated the
  fixed count. Fix: count re-review issues into `found` + `min(fixed, found)`
  clamp in reviewer.py.

## 7. WHAT IS VERIFIED WORKING END TO END
- Full BA→PI→Architect→Developers→CodeReviewer chain, in the UI and via API.
- 8/8 Week-3 gating scenarios (BA/PI/Architect) — though 3 are LLM-non-
  deterministic on borderline classify() cases (see gaps).
- Developer builds across 3 domains (coffee/telehealth/SaaS), contract holds,
  0 fallbacks with all 3 real providers.
- Code Reviewer: real 7-file build fully secured + certificate; planted SQL
  injection caught and fixed by Opus; security always used claude-opus-4-8 even
  in cheap mode; UI leaks no model names (grep-verified).

## 8. WHAT IS NOT DONE / LEFT MID-TASK (critical for a new engineer)
- **The generated app is NOT runnable/deployed.** Generated code is stored as
  TEXT in `generated_files`. Nothing writes files to disk, installs deps,
  assembles, runs, or hosts them. There is NO live URL for a generated app.
  That is the **DevOps agent (#11)**, a future week. localhost:3000 is the
  PLATFORM, not any generated app.
- **No code export to disk** yet (core rule says "full code export always
  available") — not implemented.
- **Absolute imports** in generated code (`backend.app.models`) may not resolve
  when packaged — flagged for the Code Reviewer / a future assembly step.
- **Qdrant vector store** (in the locked tech stack) — not added.
- **Agents built:** BA(#1), Product Intelligence(#2), Architect(#3),
  Developers(#4–7), Code Reviewer(#9). **NOT built:** Design Review(#8),
  QA(#10), DevOps(#11), Documentation(#12), Monitoring(#13), Auto-fix(#14),
  Cost Tracker(#15).
- **8-scenario gating is non-deterministic** on borderline classifications
  (restaurant-staff internal vs customer-facing; "iPhone app" platform;
  "tip"→payment). Same code passed 8/8 before; a robustness gap in `classify()`,
  not a regression. Consider few-shot hardening.
- **The codebase-tour teaching activity with the user paused at
  `backend/app/database.py`** (a learning walkthrough, not code work) — resume
  the tour there if the user asks.
- **Cost caution:** full `real` builds cost real Claude money; the security pass
  costs real Opus money on EVERY file regardless of CODEGEN_MODE. Test on small
  ideas. The user has limited Claude/Gemini credit and watches it closely.

## 9. TRAPS / CONVENTIONS A NEW ENGINEER MUST KNOW
- After editing backend Python: `docker compose build --no-cache backend`
  (plain --build has silently served stale code).
- Never commit `.env`; never add a Claude co-author to commits (user rule).
- Security review is ALWAYS claude-opus-4-8 with bypass_cheap — never let budget
  or CODEGEN_MODE downgrade it (hard core rule).
- User-facing text must never contain code, agent names, or model names.
- Model IDs rot — prefer "-latest" aliases and keep graceful fallback.
- The user tests manually first, then asks for automation; be honest about cost
  before running expensive multi-model / Opus builds.

---

## GITHUB & COMMIT RULES (permanent — always follow)
- **Remote:** PRIVATE GitHub repo `Rajkumar2002-Rk/ai-org` (branch `master`).
  Keep it PRIVATE — CONTEXT.md contains the full product strategy.
- **NEVER add a co-author.** Do NOT add any `Co-Authored-By:` line, and never
  attribute commits to Claude/AI. Commits use the user's identity ONLY
  (Rajkumar2002-Rk <rajkumarn2002@gmail.com>).
- **Never commit secrets.** `.env` and `practice/` are gitignored — keep them
  that way. Before any push, verify `.env` is NOT staged and scan the diff for
  real keys (sk-proj / sk-ant / AIza / AQ. / sk_live / AKIA).
- **Push cadence:** commit + push at the end of each week (and whenever the user
  asks), so nothing is lost.
- Normal flow: `git add -A && git commit -m "…" && git push`.
