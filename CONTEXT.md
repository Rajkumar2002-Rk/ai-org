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

| # | Agent | Talks to user? | Model | Job |
|---|-------|-----------------|-------|-----|
| 1 | BA Agent | Yes — only one | GPT-4o mini | Requirements + competitive intelligence + design preferences |
| 2 | Product Intelligence | Before build only | GPT-4o | UX review + business goal alignment + PM recommendations |
| 3 | Architect | Never | GPT-4o | Technical blueprint + API detection + LLM routing map |
| 4 | Backend Developer | Never | GPT-4o | Server logic, database, API endpoints |
| 5 | Frontend Developer | Never | Claude Sonnet | Premium UI, animations, responsive design |
| 6 | Mobile Developer | Never | Claude Sonnet | React Native screens if mobile chosen |
| 7 | Integration Developer | Never | GPT-4o mini | Third-party API connections |
| 8 | Design Review | Never | Claude Sonnet | UX evaluation, consistency, interaction completeness |
| 9 | Code Reviewer | Security cert only | GPT-4o mini + Claude Opus 4.8 | Code quality + security (Opus always) |
| 10 | QA Agent | Test report only | GPT-4o mini | 5 levels of testing + root cause tracing |
| 11 | DevOps | Live link only | GPT-4o mini | Deploy, SSL, domain, Safe Mode, version timeline |
| 12 | Documentation | Final summary | GPT-4o mini | User guide, demo script, handoff summary |
| 13 | Monitoring | Weekly summary | GPT-4o mini | Health, performance, error tracking |
| 14 | Auto-fix | Level 3 issues only | GPT-4o | Self-healing, snapshot safety, rollback |
| 15 | Cost Tracker | Monthly dashboard | GPT-4o mini | Spend tracking, optimization, budget alerts |

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
- The blueprint still records the *intended* model; only the call is swapped.
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

### Current phase
**Week 5 — Code Reviewer (#9) (see Weekly Claude Code Prompts v2).**
Code quality + security; security review ALWAYS Claude Opus 4.8. It should catch
hallucinated imports, insecure CORS, and cross-file inconsistencies.

### What NOT to touch next session
- Do NOT modify the BA, Product Intelligence, Architect, or Developer agents
  unless the new week requires it — all tested and locked.
- Do NOT change existing schemas or migrations (0001–0005), the Redis
  conversation/pipeline/build state formats, or the /conversation/* and
  /pipeline/* endpoint contracts.
- Do NOT weaken the BINDING PROJECT CONTRACT or the foundation-first ordering —
  it is what keeps generated files consistent.
- Do NOT change CODEGEN_MODE defaults (`real` must stay the default) or the
  locked routing; security review stays Claude Opus 4.8.
- Do NOT build Design Review, QA, DevOps, Documentation, Monitoring, Auto-fix,
  or Cost Tracker agents until their week.

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


## REFERENCE — NOT FOR CLAUDE CODE TO RE-READ EVERY SESSION

The full Master Blueprint v2 document (mission, all 15 agents in
full detail, every market problem solved, full interview
preparation, complete tech stack reasoning) is kept separately
on the builder's computer. It is not uploaded into this project.
This CONTEXT.md is the condensed version Claude Code needs.
