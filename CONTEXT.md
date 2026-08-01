# Autonomous AI Engineering Organization — CONTEXT.md

This file is Claude Code's memory between sessions. Read this
fully before doing anything else in this project.

---

# ⏭️ RESUME HERE — Week 7 DevOps COMPLETE & VERIFIED, local AND live on AWS (2026-07-31)

**Start the next session with:** "Read CONTEXT.md. Week 7 DevOps is complete and
verified — local path AND a real live AWS deploy (since torn down). Week 8 next."
Week 7 is CLOSED; this is its closing record. Do NOT re-open it. The AWS shakeout
proved the driver end-to-end on a real EC2 instance and found+fixed four real
bugs (see "AWS SHAKEOUT" below). All shakeout infra was torn down by tag; only the
`apps.rajkumarai.dev` hosted zone is kept (for future deploys).

## WEEK 7 — DevOps Agent (#11) — DONE (local proven AND live-on-AWS verified)

The DevOps agent deploys a tested, security-certified project silently: read
cloud_config → size the server → assemble the generated code into real Docker
images → deploy an ISOLATED per-project stack → create the DB schema → inject
secrets → stand up HTTPS → health-check the live URL (10s × 2min, one infra-only
auto-fix). It never talks to the user; the API exposes a live URL + counts only.

### The five design questions, answered structurally (not by intention)
- **Per-user isolation** is a pure function of `project_id` (`devops/naming.py`):
  every container/network/database/subdomain name is derived from the id, no code
  path takes a caller-supplied name, each app runs on its OWN docker network with
  its OWN DB credentials. Proven by CROSSING it: the live test shows A's network
  cannot reach B's database container, and the offline test shows the two name
  sets are disjoint.
- **Secrets out of logs, structurally**: Fernet-encrypted at rest (`secrets`
  table); injected only via a `0600 --env-file` deleted after `up` (never CLI
  args, never image layers); a `SecretRedactingFilter` on the log sink replaces
  live values. Proven BOTH ways (redacted with the filter on; reappears with it
  off). Secret VALUES never enter the deployments row or any API payload — proven
  live with a sentinel value.
- **Cost estimate** is computed from the CONCRETE resources chosen
  (`devops/cost.py`), not parroted from the blueprint; `cost_basis` records
  `projected_aws_<tier>` (local) vs `billed_aws_<server>` (aws); a dated rate
  table has a staleness tripwire the suite asserts.
- **Auto-fix is infra-only and fail-closed**: the ONE remedy is
  `driver.restart()` (cycle processes); it has NO path to edit generated code or
  security config (the defect-#6 lesson). App 5xx / missing-secret / security
  refusals ESCALATE, never get "fixed". A recovered deploy is a DISTINCT dashboard
  state (`auto_fixed=true` + `fix_description`), never laundered as pristine. And
  DevOps refuses to deploy unless the Opus certificate covers EXACTLY the files
  shipping (drift re-checked at deploy time, `reviewer.drifted_files`), extending
  the defect-#6 guarantee to the deploy edge.
- **Teardown**: local resources are `docker rm/network rm/volume rm` by name (the
  isolation names are the only handle needed), proven before→during→after. Every
  AWS resource is TAGGED (`Project=ai-org`, `project_id`, `ephemeral`,
  `created_by`); `devops/teardown_aws.py` reclaims by tag and LISTS before acting
  (dry-run by default; `--yes` to act, `--terminate` for ephemeral instances).

### What was built (all new under `backend/app/devops/`)
`naming.py` (isolation), `sizing.py` (STEP 1), `manifest.py` (STEP 2: assemble +
generate requirements.txt via QA's AST import-scan + Dockerfiles + Caddyfile +
bootstrap + compose), `secrets_store.py` (STEP 5), `cost.py`, `health.py`
(STEP 7: probe + deterministic infra/app/security classifier), `drivers/base.py`
+ `drivers/local.py` (real docker) + `drivers/aws.py` (ECR + EC2 + Caddy/LE +
Route53, real but unrun), `orchestrator.py` (STEP 0–7 wiring), `graph.py`,
`teardown_aws.py`. Plus: `Secret` + `Deployment` models (migrations 0010, 0011),
config additions, `boto3`+`cryptography` in requirements, Docker CLI + socket +
`~/.aws` wired into the backend container, `POST /pipeline/deploy` +
`GET /pipeline/{id}/deploy-status`, and the frontend CLIMAX screen (deploying
animation → "Your app is ready!" + big live URL + Security/tests badges + honest
running cost).

### Verification (all green, 2026-07-30)
- **`test_devops_offline.py` — 46 checks, 0 failures** (free; sizing, isolation,
  manifest, secret redaction both-ways, cost tripwire, health ordering, fail-closed
  cert gate, AWS pure functions).
- **`test_devops_local_live.py` — 18 checks, 0 failures** (real Docker: two real
  deploys go LIVE over HTTPS, DB schema created, secret injected + not leaked,
  network isolation proven by crossing, teardown before/during/after). NOT in the
  free suite — needs the Docker socket, like `test_qa_classification` is excluded.
- **All 6 prior free suites still pass** (no regression).
- **A real defect the live test caught** (very much the project's spirit): the
  local Caddy site was `:443` with `tls internal`, which has no hostname to mint a
  cert for → the TLS handshake failed with an internal-error alert. Fixed by
  naming the site `localhost, host.docker.internal`. The mechanism proof caught a
  bug the offline tests structurally could not.

### ⭐ AWS SHAKEOUT — PROVEN LIVE on real EC2, then torn down (2026-07-31)
The AWS driver is no longer "real but unrun". DNS was delegated (Namecheap NS →
Route53, confirmed propagated), and a synthetic backend-only fixture (project 357)
was deployed for real via `DEPLOY_TARGET=aws` onto a tagged t3.micro. **Verified
LIVE, independently from the host:** `https://shakeout-3c155f.apps.rajkumarai.dev`
served `/openapi.json` (200), `/` and `/config-check` (`has_demo_secret:true` —
secret injected via SSM Parameter Store), with a **real, trusted Let's Encrypt
certificate** (issuer `Let's Encrypt`, valid Jul 31 → Oct 29; confirmed in
Chrome's security panel too). All 7 steps exercised on real AWS; the fail-closed
security gate also fired for real (it blocked the deploy when the cached cert had
expired, until re-established).

**Four real bugs the shakeout found and fixed (all in `drivers/aws.py` +
`backend/Dockerfile`) — this is why a live shakeout mattered:**
1. **DNS created AFTER bring-up** → Caddy's first ACME attempt had no record to
   validate against, and the health window missed the backoff retry. Fixed:
   upsert the Route53 A record BEFORE `_deliver_and_up`.
2. **Cross-arch mismatch** → images built on the arm64 Mac crash-looped on the
   x86_64 instance (`exec format error`); the multi-arch postgres ran fine, which
   is what pointed at arch. Fixed: cross-build `linux/amd64`.
3. **`docker buildx` missing** in the backend image (only cli + compose plugins
   were installed) → `docker build --platform` can't load a cross-arch image into
   the arm64 store. Fixed: add `docker-buildx-plugin`; build+push via a
   uniquely-named `docker-container` builder (removed in a `finally`, no leak).
4. **Secret silently not injected** → the instance role lacked
   `ssm:GetParametersByPath` AND the bring-up's `aws … | awk > deploy.env` pipe
   had no `pipefail`, so the AccessDenied was swallowed and a MISSING SECRET read
   as a successful deploy — this project's signature "absence of evidence =
   success" anti-pattern, caught live. Fixed: scoped SSM-read inline policy on the
   role, plus `set -euo pipefail` so a failed fetch aborts the bring-up loudly.

**Teardown was run and VERIFIED clean** (`teardown_aws.py --yes --terminate` +
extras): 0 tagged instances, 0 ai-org ECR repos, 0 A records, 0 security groups,
0 SSM params, the `ai-org-ec2` role/profile deleted, local project-357 rows/keys
removed. The `apps.rajkumarai.dev` hosted zone (`Z02777111O69NKZ136VS`) is KEPT.
Nothing paid is left running.

**To run a live AWS deploy again** (all shakeout infra was torn down, so it must
be recreated — logged as a known gap below):
1. DNS is already delegated (zone `Z02777111O69NKZ136VS`, NS at Namecheap).
2. Create a role+profile with SSM + ECR-read + `ssm:GetParametersByPath`/`kms:Decrypt`
   on `/ai-org/*`, a security group (80/443), and launch ONE t3.micro tagged
   `Project=ai-org` (AL2023; user-data installs docker + compose). Per the cost
   plan: STOP (not terminate) between tests; teardown by tag when done.
3. `DEPLOY_TARGET=aws` and deploy. **Cost reality:** always-on t3.micro ≈ **$12/mo**
   (t3.micro ~$7.59 + the ~$3.65 public-IPv4 charge + EBS + $0.50 zone); a short
   shakeout torn down promptly is a few cents. SSL is Let's Encrypt via Caddy on
   the instance (ACM needs a paid ALB → would break the budget).

### Carried forward / known-open (Week 7)
- **No onboarding stage populates the `secrets` table with real user secrets yet**
  — a "connect your API keys" UI is scoped future work; the store is real and
  read by DevOps today, seeded directly (tests). Same explicit gap as
  requirements.txt. Stripe still never lands here (hosted OAuth inside the app).
- **The AWS driver assumes the instance + IAM role/profile + SG already exist**
  (`_find_instance` errors if none is tagged); it does NOT provision them. The
  shakeout created them by hand and tore them down, so a future live deploy must
  recreate them (see steps above). Auto-provisioning them (with the exact SSM
  `GetParametersByPath`/`kms:Decrypt` perms bug #4 needed) is a clean future
  enhancement.
- **Both proofs used a backend-only synthetic app.** A full FRONTEND deploy
  (Next `npm run build` in the image) is wired but not yet exercised end-to-end —
  do that with a known-good generated project (the D4 SSG-prerender quality issue
  from Week 6 would surface at image-build time here, honestly).
- Docker-out-of-docker: the backend container builds via the host socket
  (acceptable for this dev platform; a real product would use a build service).

---

# (Week 6 verification history below — superseded as the resume point by Week 7)

# ⏭️ Week 6 VERIFICATION COMPLETE (2026-07-30)

## VERDICT: every pipeline MECHANISM is proven with hard evidence

Across **9 real paid baseline runs** and the offline suites, every QA/pipeline
mechanism has been exercised on real generated code and shown to work:

| Mechanism | Proven by |
| --- | --- |
| Retry-and-escalate loop (cap 3, then escalate) | Step 2; real rows 145–148; run 342 hit cap 3 and escalated |
| Root-cause classification (5 tiers) + reasoning | Step 3; `environment_fault` correctly fired on run 332's fail-fast |
| Teardown (temp dir / DB / uvicorn, incl. crash path) | Step 4; `test_qa_teardown` 37 checks, before→during→after |
| Cost instrumentation (per-call tokens, run_id join) | Step 6; 9 runs, **0 capture failures** ever |
| Fail-closed recertification (defect #6) | Project 142 + run-time recerts; missing-cert blocks |
| Naming + collision resolution | Runs 308/342: conventional paths, `order_be_3.py` handled |
| Truncation handling (stream + stop_reason) | `codegen._via_anthropic`; ended the 8192 stub |
| Environment-fault detection + env auto-discovery | `assembly._discover_required_env`; S5 real-boots a fail-fast app |
| Stub gate + targeted retry | `test_developers_offline` S2/S3 |
| Suspend-aware driver + abort-on-unfinished-stage | `verify_pipeline.py`; simulated 3h-jump test |

**Total spend: $18.2252** measured across all instrumented runs (id > 40),
0 capture failures. **The verification goal — proving the pipeline works — is
fully met.** All six verification steps (1–6) are CLOSED.

## Why we stopped chasing a fully-green synthetic build (deliberate)

Every STRUCTURAL and HARNESS defect is fixed and genuinely exhausted. What blocked
a green *boot* by attempt #9 was the **generated-code-QUALITY tail** — the LLM
occasionally writing imperfect application code, which QA correctly catches (that
IS QA working). Chasing green from here is a codegen-quality pursuit, open-ended
and separate from verification. The user's call (2026-07-30): declare verification
complete, log the residual quality defects, move to Week 7.

## KNOWN-OPEN — generated-code QUALITY defects (for a later dedicated pass; NOT QA/structural)

- **FastAPI `response_model` set to a SQLAlchemy ORM model** (run 342, backend
  did-not-start). A router used `response_model=List[MenuItem]` (an ORM model),
  which FastAPI rejects at app construction: *"Invalid args for response field …
  is [not] a valid Pydantic field type."* Fix (later): a Backend-Developer prompt
  rule — response_model must be a Pydantic schema, never an ORM model (omit it, or
  define a response schema). Same shape as the existing anti-workaround prompts.
- **Flaky SSG prerender (D4)** (runs 274 fail / 283 pass / 342 fail on `/integrate`).
  `next build` compiles and static-generates, but prerendering one page throws at
  SSG export — nondeterministic. Fix (later): opt generated pages into dynamic
  rendering (`export const dynamic = "force-dynamic"`) so `next build` stops
  prerendering, rather than per-page patching.
- **D3 residual — wrong SYMBOL from a correctly-pathed module.** The module-PATH
  family is closed (module map + conventional names); a file can still import a
  wrong *name* from the right module. Surfaces as a clear ImportError caught by QA
  retry, never a silent failure.

All three are the LLM writing imperfect app code. None is a QA/pipeline mechanism
bug. A dedicated code-quality pass (prompt tuning + a rendering-strategy decision)
is the right venue, not verification.

## Also carried forward into Week 7
- **`requirements.txt` is not generated.** QA boots fine (assembly import-scans and
  pip-installs), but a REAL deploy can't import-scan itself — DevOps must generate
  a manifest. Logged during the Step-5 audit.
- Do NOT start Week 7 on top of unverified mechanisms — they ARE verified now.

**Working tree:** clean, all pushed (HEAD `34daa9b` before this final doc commit).
Regression, measured 2026-07-30 (verify by exit code + RESULT line, NOT the [PASS]
count — a crashed suite still prints its earlier PASS lines):
**75 / 226 / 19 / 35 / 70 / 16 = 443 checks, 0 failures** across `test_qa_offline`,
`test_architect_offline`, `test_qa_retry_loop`, `test_qa_teardown`,
`test_token_instrumentation`, `test_developers_offline`. (`test_qa_classification`
is excluded from the free set — it makes real Gemini calls.)

---

# WEEK 6 VERIFICATION SESSION (2026-07-21) — six defects found and fixed

## STATUS: COMMITTED AND PUSHED ✓

All six fixes are committed as **`d438366`** ("Week 6 verification: fix six
defects found by running QA for real") and pushed to `origin/master`. **The
working tree is clean.** Nothing here is at risk.

```
d438366  Week 6 verification: fix six defects found by running QA for real
7035a8d  CONTEXT.md: correct QA agent reference data after Week 6
1ae9b7e  Week 6 - QA Agent (#10): three-level testing on an ephemeral instance
```

Committed in `d438366` (10 files, +985/-63):
```
 backend/app/architect/builder.py          +44   APP-1 entrypoint ticket
 backend/app/developers/agents.py          +5/-1 filepaths in the prompt
 backend/app/qa/assembly.py               +242   AST imports, alias hook, endpoint diff, _TEST_ENV
 backend/app/qa/orchestrator.py           +177   _recertify, stale-failure clearing, targeting
 backend/app/qa/outcome.py                  +3   TestOutcome.evidence
 backend/app/qa/root_cause.py              +13   architect_rework classification
 backend/app/reviewer/orchestrator.py     +104   file_hashes, drifted_files, review_subset
 backend/tests/test_architect_offline.py   +11   APP-1 invariants
 backend/tests/test_qa_offline.py         +147   section F regression
 CONTEXT.md                               +302   this handoff
 backend/tests/verify_pipeline.py         (new)  real end-to-end pipeline driver
```

Regression at commit time: **226 checks, 0 failures** (174 Architect / Weeks 3-5,
52 QA / Weeks 5-6). Container md5s matched the tree on all 7 changed modules;
0 leftover temp dirs, 0 orphaned `qa_test_*` databases.

`_verify_cert.py` and `_verify_run.log` were deleted; `_verify_pipeline.py` was
kept and renamed **`backend/tests/verify_pipeline.py`** — it drives a real
BA→PI→Architect→Developers→CodeReviewer→QA run and Steps 5-6 will need it.

## THE ONLY GENUINELY OPEN WORK: verification Steps 2-6

Step 1 (real pipeline run) is **done** — it is what produced the six defects
below. Steps 2-6 were never started:

| Step | What it asks for | Needs fresh pipeline spend? |
| --- | --- | --- |
| 2 | ~~Trigger the retry-and-escalate loop for real~~ **CLOSED 2026-07-21** — see "STEP 2 RESULT" below | No (none used) |
| 3 | ~~Root-cause classification quality~~ **CLOSED 2026-07-21** — see "STEP 3 RESULT" below | No (a few Gemini Flash-Lite calls, fractions of a cent) |
| 4 | ~~Prove teardown directly: temp dirs + Postgres databases before/after~~ **CLOSED 2026-07-21** — see "STEP 4 RESULT" below | No (none used) |
| 5 | ~~Run with `qa_frontend_full_build=true`~~ **CLOSED 2026-07-22** — the build never executed; see "STEP 5 RESULT" | Yes (spent) |
| 6 | ~~Real token usage and dollar cost~~ **CLOSED 2026-07-22** — measured; see "STEP 6 RESULT" | Yes (spent) |

**ALL SIX VERIFICATION STEPS ARE NOW CLOSED.**

Steps 2-4 are CLOSED and cost **$0.00** between them. **Steps 5 and 6 are all
that remain, and both need fresh pipeline spend** — Step 6 also needs token
instrumentation built first.

### STEP 2 RESULT — retry-and-escalate loop: CLOSED (2026-07-21)

Analysis of the real data found the loop's **safety** properties proven (cap
never exceeded 3, escalation marked, loop terminates) but its **usefulness**
properties unproven: every retry in the database came from PRE-fix code, and the
three post-fix runs recorded **zero retries**. Two defects were fixed, then a
synthetic driver closed the gaps:

- **Gap 5 fixed** — `assembly: designed features are missing from the running
  app` was classified `developer_rework` (auto-fixable) but could never be
  attributed to a file, so it sat at `retry_count=0` forever: labelled fixable,
  silently never fixed. `qa/orchestrator._resolve_owner()` now routes it to the
  ENTRYPOINT file (missing routes almost always mean the entrypoint failed to
  register the router). Every unretried failure now also states WHY, via three
  markers: `[escalated after retries]`, `[escalated — needs Architect/BA, not
  auto-fixable]`, `[escalated — could not be traced to a specific file]`.
- **`run_id` added** (migration `0008`, indexed, **historical rows backfilled**
  by `(project_id, created_at)`). `blueprint_id` does NOT separate re-runs of one
  project — project 142's 17 rows were three stacked runs that had to be split by
  hand. They now group by key.
- **`backend/tests/test_qa_retry_loop.py`** (new) drives the REAL
  `qa.orchestrator.run()` — real assembly, venv, temp Postgres, uvicorn, L1/L2,
  persistence — against synthetic projects. **Zero LLM spend**: `codegen.generate`,
  `dev_agents.build_ticket` and `reviewer.review_subset` are patched, and the
  Developer returns a *scripted* repair so retries are deterministic.

Evidence (real `qa_results` rows, projects 145-148):

| proj | retry | passed | root_cause | what it proves |
| --- | --- | --- | --- | --- |
| 145 | 1 | **true** | — | retry was PRODUCTIVE (app booted, 8 L1/L2 tests then passed) and the resolved failure CLEARS: `resolved after 1 repair attempt(s)` |
| 146 | 0 | false | **architect_rework** | tier boundary respected — Developer never invoked |
| 147 | 3 | false | developer_rework | cap holds under fixed code: exactly 3 Developer calls, then escalate and stop |
| 148 | 1 | **true** | — | gap 5 fixed — missing-routes finding is retried, not a silent no-op |

Project 146 is the first `architect_rework` row ever written to this database.

### STEP 3 RESULT — root-cause classification quality: CLOSED (2026-07-21)

Probe: `backend/tests/test_qa_classification.py`. Reports the classification
PATH (which deterministic rule fired, by name, or "model" plus the model's own
stated reason) — the question was whether the classifier REASONS or
pattern-matches.

**Audit of the 9 real classified rows: 4 of 6 `developer_rework` labels were
wrong in reality** — they were faults in QA's own harness (`ModuleNotFoundError:
'backend'`, missing `AUTH0_*`, the dual-path double-import), not Developer bugs.
Every one of Step 1's six defects surfaced as a Developer-blamed failure.

**Two fixes (both authorised):**

1. **The `"server error" + level 1` rule was swallowing the most common failure
   class.** `level1.py` emits `"Server error {code} — ..."` for EVERY 5xx
   endpoint failure, so that whole class was labelled `developer_fix` by
   substring match, with no reasoning — even when the same text said the column
   was *"not present in the blueprint's database schema"*. Now narrowed: it only
   short-circuits when the text carries no architect-level signal
   (`blueprint`, `schema`, `designed`, `not defined`); otherwise the model
   decides. Effect: that case went from `developer_fix` (no reasoning) to
   `architect_rework` — *"The database schema lacks the required customer_email
   column referenced across multiple application files."*
2. **New fifth category `environment_fault`** — the code is fine, QA's own
   harness is broken. Never auto-retried, escalates straight to a human with its
   own message (`[escalated — QA's own test environment is at fault, the
   generated code is not]`). This gap caused the AUTH0 security regression: the
   app correctly refused to boot without config, QA called it a Developer bug,
   and the "repair" hardcoded fake credentials. Detection is deliberately
   high-precision — a false `environment_fault` would HIDE a real bug:
   - `No module named 'backend'` (exact top-level package, which is on disk) →
     environment. `No module named 'backend.app.payments'` (dotted) → Developer,
     a file was never generated. `No module named 'stripe'` → Developer.
   - "refusing to start" / "missing required ... environment variable" →
     environment (the app is behaving correctly).
   - `"is already defined for this metadata"` → environment (double import via
     harness `sys.path`).
   Verified in both directions, including a guard that a genuine `NameError` at
   startup is still `developer_rework` and never excused.

**Model quality when consulted:** good on clear cases — the blatant domain
mismatch, the typo dressed in architect vocabulary, and the missing-validation
case were all reasoned correctly. **No over-escalation** was found in either
probe: trivial Developer bugs stuffed with the words "schema", "blueprint" and
"architecture" still came back `developer_fix`.

### ⚠️ KNOWN GAP — classification is NOT repeat-stable on ambiguous input

**Category: an LLM reliability limit, not a code bug.** Nothing here is fixable
by editing a rule — it needs dedicated design thought, and was explicitly NOT
solved as part of Step 3's closeout.

The same failure, classified 5 times with identical input (borderline case B3,
"an undeclared dependency between two tickets"):

```
run 1 (Step 3 first pass) : architect_rework   x1
runs 2-5 (stability probe): ba_rework          x3
                            developer_rework   x1
```

Three different labels across five identical calls, spanning all three
escalation tiers. For contrast, the other two borderline cases WERE stable
(`B1 architect_rework ×4`, `B2 developer_fix ×4`), so this is specifically about
genuinely ambiguous input, not general flakiness.

It is also mostly WRONG, not merely unstable: the model's own stated reason for
`ba_rework` was *"a required module and endpoint were never generated"* — that
describes an Architect ticket gap, not a misunderstood requirement. The correct
answer (`architect_rework`) came up 1 time in 5.

**Blast radius:** `ba_rework` and `architect_rework` both escalate to a human, so
the routing outcome is accidentally right ~3 times in 4. The `developer_rework`
outcome is the harmful one — roughly 25% of the time an unfixable-by-Developer
failure gets auto-retried instead of escalated, burning retries on work that
cannot succeed. That is a milder version of the Step 1 defect.

**Options to consider when this is designed properly (none implemented):**
- **Majority vote** on ambiguous classifications — classify N times, take the
  mode. Cheap on Flash-Lite, but N× the calls and it does not help when the model
  is *consistently* wrong.
- **A confidence signal that forces escalation regardless of label** — have the
  model return a confidence, and escalate anything below a threshold rather than
  auto-retrying it. Fails safe: uncertainty routes to a human instead of
  spending retries.
- **Restrict auto-retry to deterministically-classified failures only** —
  anything the model decided escalates by default. Most conservative; costs
  autonomy on cases the model actually gets right.

**Operating rule until then: do not treat a single classification as
authoritative on a genuinely ambiguous failure.**

**Known gap, deliberately NOT fixed (new scope): `ba_rework` is unreachable in
production.** The label works when evidence of a requirements mismatch is in the
failure text, but nothing in QA produces such evidence — `summary` reaches QA
only inside `root_cause.classify()` (`root_cause.py:128`); no Level 1 or Level 2
test compares the built app against `summary_json`. **An app that flawlessly
implements the WRONG product passes every QA test and produces no failure to
classify.** Closing it needs comparison testing against the requirements.

**Known gap, deliberately NOT fixed (new scope, not a defect): retry
productivity is not auditable from `qa_results`.** Only the final state per test
is stored — `retry_count=3` says three attempts happened, not what differed
between them. Productivity was proven here by instrumenting the driver (counting
`build_ticket` calls), not by reading the table. Making it auditable in
production needs a per-attempt record; decide that deliberately rather than
bolting it on.

### STEP 4 RESULT — teardown: CLOSED (2026-07-21)

Probe: `backend/tests/test_qa_teardown.py`. Every resource is sampled at three
points — **BEFORE → DURING (must genuinely EXIST) → AFTER (gone)** — and the real
listings are printed, because "zero before, zero after" is also exactly what a
run that did nothing produces.

**The test was audited before it was trusted, and four of its own checks turned
out to be the same defect this whole verification pass keeps finding** — checks
that could only ever return the reassuring answer:

1. **S4's headline check proved nothing.** It asserted `report["total"] > 0`, but
   `total` is `len(final)` (`qa/orchestrator.py:437`), the count of distinct test
   NAMES — `> 0` for any pass producing a single outcome, including one that
   assembled exactly once and never retried. S4 is the ONLY scenario covering
   accumulation *across* cycles. The cycles are now **counted**: `assembly.assemble`
   and `dev_agents.build_ticket` are wrapped with counters, and `retry_count` is
   read back from the persisted `qa_results` rows as independent confirmation.
2. **Three checks accepted "never created" as "cleaned up"** — the pattern
   `X is None or X not in after[...]`. `teardown()` deliberately does not null
   `env.root` / `env.db_name` / `env.process` (`qa/assembly.py:589`), so each
   resource is now proven **created AND then gone**, as two separate checks.
3. **S2 had no DURING sample at all**, despite that being the file's stated
   thesis. `assemble()` provisions the database (`assembly.py:532`) BEFORE
   launching uvicorn (`:553`), so a never-booting app genuinely does leave both
   resources behind — they are now sampled while they exist.
4. **S3's crash check was diluted by an `or`** — `any("unexpected error" in o.name
   or not o.passed ...)` passed on ANY failing outcome for any reason, including a
   swallowed crash accompanied by an unrelated failure. Now strictly the crash.

Also hardened: the temp-dir listing uses `tempfile.gettempdir()` instead of a
hardcoded `/tmp` (`mkdtemp` honours `TMPDIR`, and a listing that silently matches
nothing is the exact bug that helper had already been rewritten **twice** for),
and S4 restores its patches in a `finally` so a later scenario can't be poisoned.

**Result under the tightened checks: 35 checks, 0 failures — run twice, byte-identical.**
Zero LLM spend, confirmed at the seam rather than assumed: the only spend path is
`root_cause.classify()` (`root_cause.py:210`), which does `from app import codegen`
and calls `codegen.generate`, so patching that module attribute covers it.

Evidence — real listings, not assertions about listings:

```
S1 DURING   /tmp/qa-build-qf8fxv4s
            qa_test_1b1f2e842b3b
            pid 17  .../.qa-venv/bin/python -m uvicorn backend.app.main:app
S1 AFTER    (none) / (none) / (none)

S2 DURING   /tmp/qa-build-r4fch9lk   qa_test_7d8e525f9d28   (app never booted)
S2 AFTER    (none) / (none)

S4          assemble() calls=2   build_ticket() calls=1
            max retry_count in qa_results=1
            retry_count=1  assembly: app did not start
```

All three resource types are proven created-then-gone across four scenarios:
temp directory, throwaway Postgres database, uvicorn child process — including
when the app never boots (S2) and when an exception is thrown mid-test (S3,
proving the orchestrator's `finally` fires).

### ⚠️ STANDING PRINCIPLE — "absence of evidence" is not "evidence of success"

**Every verification step so far has found the same failure pattern, and in each
one it WAS the finding.** These are not unrelated bugs; they are one recurring
design error, and it is worth watching for by name rather than rediscovering it
each time:

| Step | Where it hid | What it did |
| --- | --- | --- |
| 1 | The Opus security certificate | A certificate with no fingerprint could not be *proven* to match disk — and "we can't tell" resolved to "it's fine." Fixed by failing CLOSED. |
| 3 | `root_cause` short-circuits | `"server error" + level 1 → developer_fix` fired before any reasoning, so the most common failure class got a confident label nobody had actually thought about. |
| 3 | `environment_fault`'s absence | QA's own broken harness had no category to land in, so it scored as a Developer bug — and the "repair" hardcoded credentials. |
| 4 | The teardown checks themselves | `X is None or X not in after[...]` — a resource that was never created reported a clean teardown. |
| 6 | The usage rows that were never written | `usage.record()` swallows write errors by design, so instrumentation can never break a pipeline run. A systematic failure therefore produced a "successful" run holding **zero** usage rows. **A low cost total and a missing cost total are indistinguishable without checking the ROW COUNT for the `run_id`.** |
| 6 | A promotional rate going stale | Claude Sonnet 5's introductory pricing expires 2026-08-31. A rate that quietly lapses still produces a confident-looking number and nothing announces it stopped being true — so `_RATE_EXPIRY` is an active tripwire the suite asserts on, and the suite also proves the tripwire itself can fire. |
| 5+6 | **A missing certificate reading as "certified"** | A host restart mid-run destroyed `security_cert:201` in Redis while Postgres still said `status='secured'`. `drifted_files()` returns `[]` when there is no certificate — correct in itself, since drift is meaningless without a baseline — but that flowed through `_recertify()` as `{}` and landed on `certified = True`. QA would have marked the build **`tested` with no security certificate ever verified against the final code**. Same shape as defect #6, different trigger: **data loss, not code drift.** |

**On that seventh entry — the symptom was the code path; the ROOT CAUSE was
storage.** `docker-compose.yml` declared a volume for Postgres and **none for
Redis**, so the store holding the security certificate was pure cache while the
store holding `status='secured'` was durable. The two disagreed after a restart
and the disagreement resolved in the unsafe direction. Fixing only `_recertify()`
would have left a system that still loses certificates and merely complains more
loudly about it. Both are fixed: a `redis_data` volume **with `appendonly yes`**
(RDB snapshotting is exactly what dropped the writes — everything since the last
snapshot is lost on an ungraceful kill), plus the fail-closed default.

**The fix needed a fix, and the existing suite caught it.** The first version
emitted the blocking result as a failing test with `retry_count=0` and **no
escalation marker** — reintroducing precisely the silent no-op Step 2 closed
(a failure that never says why it was not retried). `test_qa_retry_loop` failed on
`no silent retry_count=0 failure left behind`. There is now a fifth marker,
`ESCALATED_CERT_PREFIX` — *"[escalated — no security certificate, this build
cannot be certified]"* — because no agent can fix a missing certificate; it is
operational, not a defect in anyone's output.

Related and still true: `_recertify()` writes the certificate with `ex=86400`, so
a certificate **expires after 24 hours**. Under the fail-closed fix that now
BLOCKS rather than silently passing — correct, but it means a project QA'd more
than a day after certification legitimately needs re-certifying. Deliberate, and
recorded so it is not mistaken for a bug later.

The shape is always identical: **a check whose passing condition is satisfiable
by nothing happening.** A missing fingerprint, an unreasoned label, an
unrepresented category, an uncreated resource — every one of them read as
success.

**The rule: every check must be able to FAIL for the reason it exists.** State
what would have to be true for it to fail; if the answer is "nothing observable,"
the check is decorative. In practice: assert the positive FIRST — the resource
EXISTED, the model REASONED, the certificate COVERS these files — and only then
assert the property under test.

**Apply this to Steps 5 and 6 specifically.** Step 5 must prove `next build`
actually built something — a build that silently no-ops also produces zero
errors. Step 6 must prove the token instrumentation actually captured usage — a
counter that never increments also reports a number under budget.

**Operating rule for every cost figure from here on: check the ROW COUNT for the
`run_id` before reading the total.** `SELECT count(*), count(*) FILTER (WHERE NOT
capture_ok) FROM llm_usage WHERE run_id = '…'` — a cheap run and a run whose
usage writes failed produce the same small number, and only the row count tells
them apart. Quote the row count alongside any dollar figure; a total without one
is not a measurement.

### STEP 6 INSTRUMENTATION — BUILT AND PROVEN (2026-07-21); measurement pending

**Sequence deliberately changed to 6-before-5.** `codegen.generate()` captured
nothing, so instrumentation had to exist BEFORE the paid run: building it
afterwards would mean a silent capture failure costs a SECOND paid run to
discover. The one remaining paid run now yields the frontend-build evidence and
the first measured cost number together.

**What was built**
- `app/usage.py` — per-provider token extraction, pricing, persistence.
- `llm_usage` table, migration **0009**. One row per LLM call. No backfill is
  possible; historical spend stays an estimate.
- `codegen.py` — each `_via_*` helper now returns
  `(text, tokens, concrete_model_id)`. **`generate()`'s public signature is
  unchanged** (`(text, model_used)`), so not one call site was touched.
- `qa/orchestrator.run()` — sets a contextvar carrying the pass's **existing
  `run_id`** (migration 0008). No second identifier invented, no argument
  threaded through the agent layers. "What did this QA cycle cost" is now a join
  between `llm_usage.run_id` and `qa_results.run_id`.

**Two rules encoded in the schema, both from the standing principle above**
1. **A failed capture is never zero.** No usable usage block ⇒ `capture_ok=false`
   and **NULL** tokens. A silent `0` would understate spend and read as good
   news. Any total MUST exclude — and report — the `capture_ok=false` rows.
2. **Tokens are the durable fact; cost is derived.** `cost_usd` is NULL when no
   confirmed rate exists and is recomputable later from the stored counts.

**Rates — all confirmed 2026-07-21**, USD per MTok (in / out), in
`app/usage._PRICING`:

| model id (as billed) | in | out | 1M+1M |
| --- | --- | --- | --- |
| `claude-opus-4-8` | $5.00 | $25.00 | **$30.00** |
| `gpt-4o` | $2.50 | $10.00 | $12.50 |
| `claude-sonnet-5` | $2.00 | $10.00 | $12.00 — ⏳ **intro, expires 2026-08-31** |
| `gpt-4o-mini` | $0.15 | $0.60 | $0.75 |
| `gemini-flash-lite-latest` | $0.10 | $0.40 | **$0.50** |

Opus is **60×** Flash-Lite per token and reviews EVERY file ignoring
`CODEGEN_MODE` by design, so it dominates unit economics — which is why the Step
5+6 cost report splits the security review out from everything else rather than
quoting one total.

`claude-sonnet-5` is on introductory pricing. `_RATE_EXPIRY` makes that an
**active tripwire**: `usage.stale_rates()` is asserted by the test suite, which
starts FAILING after 2026-08-31 and names the fix. The suite also proves the
tripwire itself fires (`stale_rates(today="2099-01-01")`), because a staleness
check that never triggers is the same bug one level up.

**Proof: `backend/tests/test_token_instrumentation.py` — 66 checks, 0 failures.**
Each provider is handed a mocked response with a KNOWN, deliberately asymmetric
token pair, and the exact numbers are asserted back out of the database:

| provider | reported | stored (p/c/total) | model id recorded | cost |
| --- | --- | --- | --- | --- |
| openai | 1234 / 567 | 1234 / 567 / 1801 | `gpt-4o` | $0.00875500 |
| anthropic | 2345 / 678 | 2345 / 678 / 3023 | `claude-sonnet-5` | $0.01147000 |
| google | 3456 / 789 | 3456 / 789 / 4245 | `gemini-flash-lite-latest` | $0.00066120 |

Mocked on purpose: a real call returns an UNKNOWN count, so the only assertable
property would be "nonzero" — which a hardcoded constant also satisfies. A known
ground truth is what proves the extraction reads the RIGHT field, and the
asymmetric pairs mean a swapped prompt/completion pair fails loudly. The real
`openai` / `anthropic` / `google.generativeai` modules are installed, so the
genuine import paths inside `_via_*` are exercised; only the network client is
replaced.

**Negative control — the check that makes the rest mean anything:** all three
providers, given a response with the usage block stripped, record
`capture_ok=false` with NULL tokens (never 0), and the aggregate reports
`captured=3, capture_failed=3` instead of a clean-looking total.

**⚠️ THERE ARE TWO LLM PATHS, and the first instrumentation only covered one.**
Caught during pre-flight for the paid run, before any money was spent.
`app/llm.py` holds a **separate** `AsyncOpenAI` client used by **BA, Product
Intelligence, the Architect**, competitive intel and design explanations —
none of which go through `codegen.generate()`. Instrumenting only `codegen`
would have produced a pipeline total **with the Architect missing from it**: a
low number that looks entirely plausible. Both paths now record.

`llm.moderate()` is deliberately NOT recorded — OpenAI's moderation endpoint is
free and returns no usage block, so recording it would emit a stream of
`capture_ok=false` rows and bury genuine capture failures. Intentional
exclusion, documented so it is not mistaken for a gap.

Service-path pre-flight (real GPT-4o-mini calls through the running backend, not
mocks) — **4 rows, all `capture_ok=true`**, one BA message costing $0.00020070:
```
gpt-4o-mini  p=412 c=25  $0.00007680
gpt-4o-mini  p=222 c=31  $0.00005190
gpt-4o-mini  p=72  c=6   $0.00001440
gpt-4o-mini  p=256 c=32  $0.00005760
```
Known limitation: BA / PI / Architect rows carry `stage=NULL` because those
layers have no `project_id` at the call site. **The Opus-vs-rest split does not
depend on stage tagging** — it filters on `model_used`. `developers` and
`reviewer` stages ARE tagged.

**⚠️ Found while building this — a real limit, logged not fixed.** The first
version of the proof used a fabricated `project_id`; every insert was rejected by
the foreign key, and `usage.record()` swallowed the error **by design** — so the
run reported success having written **zero rows**. That swallow must stay:
instrumentation may never break a pipeline run. But it means **a systematic write
failure loses all usage silently, with only a log line to show for it** — the same
shape as everything else in the STANDING PRINCIPLE table, one level up.
**Before trusting any cost total, check that the expected NUMBER OF ROWS landed
for that `run_id`.** A low total and a missing total look identical otherwise.

### STEP 5 RESULT — frontend full build: CLOSED (2026-07-22), and it never ran

Run on project **201** with `qa_frontend_full_build=true`. **The answer to "what
does a real `next build` catch" is: it cannot execute at all.** Zero bytes
downloaded, zero build time. That is a finding, not a missing result — and it
must not be recorded as "the frontend build passed", because no build happened.

**Two independent blockers, either one sufficient:**

1. **The Architect never commissions a `package.json`.** 16 files were generated,
   5 of them under `frontend/` (`app/page.tsx`, `app/menu/page.tsx`,
   `app/orders/new/page.tsx`, `app/orders/[order_id]/confirm/page.tsx`,
   `app/settings/page.tsx`) — and **no project manifest.** `_full_frontend_build`
   correctly reports "No package.json was generated" and never reaches
   `npm install`. This is **defect #2 all over again on the frontend side**: the
   Architect commissions parts and no thing to assemble them into.
2. **The frontend build is gated behind BACKEND assembly succeeding.**
   `_full_frontend_build` lives inside `level1.run()`, and `_run_round` only calls
   Level 1 `if env.ok`. The backend failed to boot, so Level 1 never ran and the
   frontend was never even attempted. **Frontend buildability does not depend on
   the backend booting, but the check does.** Any project whose backend fails to
   start gets zero frontend coverage — silently, because nothing reports a test
   that was never attempted.

⚠️ **Latent silent-skip, related:** `_full_frontend_build` opens with
`if not os.path.isdir(fe): return []` — a build with no frontend directory at all
produces **no outcome whatsoever**, not even a skip notice. Here the directory
existed so the failure was reported, but the `return []` is the same
absence-of-evidence shape and should become an explicit "not applicable" outcome.

**FIXES from the follow-up runs (projects 240/241), all with regression proof:**
- **Root layout (`FND-4`).** The first *complete* build's real `next build`
  failed: *"build_the_main_ui/page.tsx doesn't have a root layout"*. The Next.js
  App Router requires `frontend/app/layout.tsx` (the `<html>`/`<body>` wrapper)
  before ANY page can build, and no feature ticket owned it — the exact FND-3 /
  APP-1 shape. New deterministic `_frontend_layout_ticket()` (FND-4, first wave)
  commissions it. Proven in `test_architect_offline` (FND-4 exists, owns the
  path, first wave, mandates `<html>`/`<body>`, server-only).
- **Stub gate — a build with placeholder files must not be certified.** The
  OpenAI quota outage on the first end-to-end attempt made all 8 backend tickets
  fall back to `_stub()` (`// TODO ...` in a `.py` file), yet the build reported
  `done`, Opus "certified" the TODO text, and only QA caught it via syntax
  errors. Now `_stub` carries `STUB_STATUS` (distinct from `needs_review`, which
  means a real-but-questionable file), `developers/orchestrator.run()` returns
  `build_failed` if ANY ticket stubbed, and `_run_build` sets the build status to
  `error` so the driver's `require_done` aborts before the security review.
  Proven in `test_developers_offline` (real orchestrator, temp Postgres: one
  stubbed ticket ⇒ `build_failed`, project never `built`, files still persisted).
  This is the same rule as the driver abort — an empty/unknown state must never
  read as success — now enforced at the build→review boundary.

**SECOND baseline attempt (project 252, 2026-07-27) — first COMPLETE real run,
still not green; two more of the same defect family, and an audit for the rest:**
- **Entrypoint imported guessed router names (a regression from the filepath
  fix).** `main.py` imported `backend.app.routes.menu/orders/stripe` while the
  generated files were title-slugs (`routes/implement_menu_retrieval_endpoint.py`
  …). The unique-filepath fix killed collisions but produced names the entrypoint
  couldn't guess. Fixed by **content-based** router detection:
  `developers/agents._router_modules()` scans already-built files for a
  `= APIRouter` assignment and injects the EXACT module paths into the entrypoint
  ticket's prompt (flagged `is_entrypoint`). Files that define no router (models,
  scaffolding, integrations) are correctly excluded, so the entrypoint never
  imports a `router` that isn't there.
- **`layout.tsx` imported `./globals.css`, which no ticket generated.** Next's
  root-layout convention makes the model write that import unprompted, so rather
  than fight it, guarantee the file: new `FND-5` commissions
  `frontend/app/globals.css`. Third missing foundation file after FND-3 and FND-4.
- **AUDIT (free, by inspection) — are other required foundation files missing the
  same way?** Checked the generated project against what Next.js / FastAPI
  actually need to build and boot:
  - `tsconfig.json` — **auto-generated by `next build`** when typescript is
    present (it is, in FND-3's devDeps). Not a blocker; left to Next.
  - `next.config.js` — **optional** in Next 14. Not needed.
  - Tailwind/PostCSS configs — the generated pages use **no** Tailwind classes,
    so no config is needed for the build. (The "premium Tailwind UI" stack claim
    is unmet — a QUALITY gap, not a build blocker; out of scope for green.)
  - `requirements.txt` — **not needed by QA**: assembly scans imports and pip-
    installs them, and the backend booted past dependency import (it failed on an
    internal module). ⚠️ **Week 7 / DevOps WILL need it** for a real deploy — a
    deployed container can't import-scan itself. Logged for Week 7, not a
    baseline blocker.
  Conclusion: globals.css was the only remaining build-blocking omission; the
  other conventional files are either auto-created or genuinely optional.

**THIRD baseline attempt (project 274, 2026-07-27) — both prior fixes CONFIRMED
working (main.py imported the real slug router paths; globals.css resolved), two
NEW defects, and the root fix for the whole family:**
- **D3 — the cross-file import mismatch, generalized.** With the entrypoint now
  importing routers correctly, the next layer surfaced: the Stripe *router* did
  `from backend.app.integrations.stripe import StripeOAuth`, but the real file
  was the slug `integrations/integrate_stripe_connect_for_payments.py`. Same root
  as D1 (the title-slug names from `_assign_filepaths` are unguessable), but a
  *router→helper* edge rather than *entrypoint→router*. Per-edge patching is
  unbounded, so this was fixed at the ROOT: `developers/orchestrator._contract_text`
  now emits a **GENERATED MODULE MAP** — every ticket's exact dotted import path,
  built from the filepaths the Architect already assigned — with the rule "NEVER
  import a path not in this map; if what you need isn't here, implement it inline."
  The old contract only said "integrations/ -> wrappers" generically, which is
  what left the path to a guess. This closes the D1/D3 family by construction:
  no agent has to guess another module's path. (Residual, smaller risk: a file
  can still guess the wrong SYMBOL from a correctly-pathed module; that surfaces
  as a clearer ImportError and is caught by QA retry. Not yet closed.)
  Proven in `test_architect_offline` TEST 8 (`_contract_text` declares the exact
  slug integration path, forbids the wrong guess by name, drops the generic line).
- **D4 — frontend prerender runtime error (SEPARATE family, still open).** With
  globals.css fixed, `next build` compiled and static-generated, but prerendering
  one page threw a runtime error during SSG export. This is a *code-quality* bug
  in a generated page, not a missing file — handled separately based on what the
  next run shows (likely a rendering-strategy decision, e.g. force-dynamic, rather
  than per-page fixes). NOT fixed yet.

### STEP 6 RESULT — measured cost: CLOSED (2026-07-22)

**⭐ THE REFERENCE NUMBER — one real build, `CODEGEN_MODE=real`, project 201:**

## **$0.953857 across 86 captured calls, 0 capture failures**

| | cost | rows | share |
| --- | --- | --- | --- |
| **Opus security review** | **$0.168260** | 7 | **17.6%** |
| **Everything else** | **$0.785597** | 79 | **82.4%** |
| **TOTAL** | **$0.953857** | **86** | |

By model:

| model | rows | tokens | cost |
| --- | --- | --- | --- |
| `claude-sonnet-5` (frontend codegen) | 12 | 90,173 | **$0.667482** |
| `claude-opus-4-8` (security) | 7 | 13,700 | $0.168260 |
| `gpt-4o` (backend codegen) | 13 | 21,744 | $0.108990 |
| `gpt-4o-mini` (BA/PI/review pass 1) | 30 | 23,892 | $0.006329 |
| `gemini-flash-lite-latest` (QA/integration) | 24 | 23,704 | $0.002796 |

**⭐ THIS OVERTURNS THE STANDING ASSUMPTION.** CONTEXT.md said spend was
"overwhelmingly Claude Opus 4.8". It is not. **Frontend code generation on
Claude Sonnet is 70% of a real build; Opus is under a fifth.** The old belief was
an artefact of `CODEGEN_MODE=cheap`, where codegen is nearly free and Opus is all
that is left. Any optimisation aimed at the security review is aimed at the wrong
17.6%.

**Scope of that number:** BA → PI → Architect → Developers → Opus security review.
It does NOT include a completed QA cycle, because QA failed at assembly (below).

#### Recovery overhead — NOT part of build economics

A host restart killed the original run mid-QA and destroyed the certificate, so
the security review and QA were re-run. **$1.609656 across 81 rows** (Opus
$1.562260 / 37 rows / 97.1%). **This is a crash-recovery artefact and must never
be folded into cost-per-build.** Session total on project 201 was $2.563513;
the build cost is $0.953857.

**⚠️ Buried in that recovery number is a real economic finding: the SAME 16 files
reviewed twice cost $0.168260 and then $1.562260 — a 9× swing.** Review #1 found
37 issues and fixed 22; review #2 found 109 and fixed 109 (fixing costs calls).
CONTEXT.md already noted "the Opus security pass is strict and non-deterministic";
this is the first time that variance has been priced. **Security-review cost is
not a stable per-build constant** — do not budget it as one.

#### Why QA failed (honest escalation, working as designed)

One result row, `retry_count=3`, escalated:
```
ImportError: cannot import name 'OrderItem' from 'backend.app.models'
  backend/app/routes/orders.py line 4
```
`orders.py` imports `OrderItem`; `models.py` never defines it — a **cross-ticket
contract violation**. Classified `developer_rework`, retried the full 3 times on
GPT-4o, never fixed, then escalated with `[escalated after retries]`. The loop
behaved exactly as Step 2 verified.

**Likely upstream cause — the known duplicate-filepath gap, now with a count.**
Of 16 generated files only ~13 distinct paths survive: **3 tickets all wrote
`backend/app/main.py`** and **2 wrote `backend/app/routes/orders.py`**. Whichever
ticket lands last wins, so the surviving `orders.py` can reference a `models.py`
written against a different ticket's assumptions. This is the Architect/Developer
defect already logged as known-open — it is now implicated in a real build
failure, not just theoretically wasteful.

#### ✅ Defect #6's recertification mechanism CONFIRMED in a real run

QA rewrote 2 files during its repair rounds. The certificate caught it by
fingerprint and re-reviewed exactly those:
```
recertified_after_qa: files_rechecked=2, drifted_from_certificate=[326, 327],
                      rewritten_by_qa=[326, 327], issues_found=9, issues_fixed=9,
                      passed=true
```
Project ended `qa_failed` — **not** `security_blocked` — which is correct: tests
failed, security re-check passed. First real-world confirmation that the Week-6
defect-#6 fix works outside a synthetic fixture.

#### Instrumentation coverage — verified from this run's own rows

| stage | rows | cost |
| --- | --- | --- |
| `reviewer` | 84 | $1.677781 |
| `developers` | 47 | $0.764513 |
| `qa` | 15 | $0.104541 |
| **`NULL` = `app/llm.py`** | **21** | **$0.016679** |

**21 rows with `stage=NULL` — `gpt-4o-mini` ×19 (BA, Product Intelligence) and
`gpt-4o` ×2 (Architect).** Every `codegen.generate()` call happens inside a
stage-tagged orchestrator, so these can ONLY be the `app/llm.py` path. Had the
second-path gap not been caught, that count would be zero and the build total
would have excluded the Architect entirely. **167 rows total, `capture_ok=false`
on 0 of them.**

## What this session was

A **verification session** for Week 6 (QA Agent). Not feature work. The goal was
independent confirmation of six things via real pipeline runs, not a re-summary
of what Week 6 claimed. Steps 2–6 of that verification are **still outstanding**.

It found **six real defects**. Five were in Week 6's own code; two of those were
introduced by earlier fixes *within this same session*. The headline finding is
#6: the Opus 4.8 security certificate — the platform's core trust guarantee —
could describe code that no longer existed on disk.

---

## THE SIX DEFECTS, in the order they were found

### 1. Import scanner fabricated "hallucinated dependency" findings
**File:** `backend/app/qa/assembly.py` · `_third_party_imports()`
**Wrong:** the regex `import\s+([A-Za-z0-9_.,\s]+)` put `\s` inside the character
class, so newlines matched and a leading `import os` greedily swallowed the whole
following import block. On a real generated `auth.py` it returned six garbage
strings such as `'os\nimport time\nimport logging\nimport httpx\nfrom fastapi import Depends'`
and `'HTTPException'` instead of `{fastapi, httpx, jose}`. QA then tried to
`pip install 'HTTPException'`, the install failed, and QA reported *"the generated
code imports a package that does not exist"* — **a false accusation against the
Developer agent** that consumed all 3 retries on a bug that never existed.
**Fix:** parse with `ast.parse()` and walk `ast.Import` / `ast.ImportFrom`;
skip relative imports (`node.level`). Correctly handles multi-line and
parenthesised imports. A file that won't parse returns `set()` because
`_syntax_check` already reports the syntax error separately.
**Why it was missed in Week 6:** the synthetic fixture's only bare `import` was
the last line, so there was nothing left to swallow.

### 2. The Architect never commissioned an application entrypoint
**File:** `backend/app/architect/builder.py` · new `_entrypoint_ticket()`
**Wrong:** on a real blueprint (project 141) **not one of 15 generated files
created a FastAPI application.** Verified directly: `content LIKE '%FastAPI%'`
was false for all 15. The Architect commissioned five routers (`BE-1`..`BE-5`)
and no app to mount them on. Searching every ticket title+description:
`'main.py': False, 'entrypoint': False, 'fastapi app': False, 'include_router': False`.
Weeks 3/4/5 all passed it — the Architect only checks blueprint sections exist,
each Developer ticket builds fine in isolation, and the Code Reviewer reviews
files individually (a router file is valid code on its own). QA is the first
stage that *runs* the thing, so it caught it immediately. **This bug had been
shipping since Week 4.**
**Fix:** deterministic `APP-1` ticket appended LAST in `build_blueprint()`, with
`dependencies = every other ticket id` so the wave scheduler puts it in the final
wave. **Deliberately NOT named `FND-3`**: `developers/orchestrator.py::_waves()`
runs every `FND-*` ticket in the FIRST wave, but an entrypoint must import
routers that don't exist yet.
**Authorised by the user** as a defect fix in otherwise-locked Week 3 code.

### 3. "no runnable app found" was classified `developer_rework`
**File:** `backend/app/qa/root_cause.py` · `_deterministic()`
**Wrong:** no Developer can fix a missing blueprint ticket by rewriting a router.
QA sent it back 3 times and burned three rounds of real Gemini spend on a
structurally unfixable task.
**Fix:** `"no runnable app found"` → **`ARCHITECT_REWORK`** (not auto-fixable →
escalates immediately, no wasted retries). `"app did not start"` stays
`DEVELOPER_REWORK` — the app exists but crashes, which *is* the Developer's code.

### 4. Dual-path PYTHONPATH caused double module execution *(self-inflicted)*
**File:** `backend/app/qa/assembly.py` · `_python_path()`, new `_write_alias_hook()`
**Wrong:** the fix for absolute imports put **both** `root` and `root/backend` on
`sys.path`. Generated code genuinely mixes styles — `APP-1`'s `main.py` used
`from app.…` while every router used `from backend.app.…` — so the same
`models.py` loaded under two module names, executed twice against the same
`Base`, and the app died with
`sqlalchemy.exc.InvalidRequestError: Table 'users' is already defined for this MetaData instance`.
Confirmed the generated code was *correct*: exactly one file defined `users`,
exactly one declared `Base`.
**Fix:** `_python_path()` returns the root ONLY. A generated `sitecustomize.py`
(auto-imported at interpreter start, root is on `sys.path`) installs a meta-path
finder aliasing `app.*` → `backend.app.*` so both styles resolve to **one module
object**. Verified: module body executes once, `app.models is backend.app.models`
is `True`.

### 5. Silent partial boot reported "13/14 passed" on a crippled app
**Files:** `backend/app/qa/assembly.py` (`_check_designed_endpoints()`,
`_norm_path()`, `assemble(files, expected_endpoints)`) ·
`backend/app/qa/orchestrator.py` (passes blueprint endpoints in)
**Wrong:** `APP-1` originally told the agent to wrap router imports in
`try/except ImportError` so one bad module couldn't stop boot. The agent wrote
`except (ImportError, AttributeError): pass` over *guessed* module paths;
`orders.py` failed to import and was silently skipped. QA tested the surviving
2 endpoints and reported near-success. **Never tested: `POST /api/orders`,
`GET /api/orders/{order_id}`, and all three `/admin/stripe/*` endpoints** — the
flagged security-critical Stripe Connect feature got zero Level 2 coverage.
**Fix:** `assemble()` now takes the blueprint's designed paths and diffs them
against the booted app's `/openapi.json` (params normalised via `_norm_path`).
Any missing route ⇒ `env.ok = False` — a crippled app reads as **assembly
failed**, never "mostly passing". `APP-1`'s description now forbids hiding
import errors.
**Proven on the same project (142)** that previously said 13/14: it now reports
`assembly: designed features are missing from the running app — The app started
but 5 of 6 designed endpoints are not there: /api/orders, /api/orders/{order_id},
/admin/stripe/connect, /admin/stripe/callback, /admin/stripe/status`.

### 6. ⭐ The Opus security certificate could describe code that no longer existed
**This is the most serious finding of the session.**
**Files:** `backend/app/reviewer/orchestrator.py` (new `_hash()`, `file_hashes()`,
`drifted_files()`, `review_subset()`; `run()` now stamps `file_hashes`) ·
`backend/app/qa/orchestrator.py` (new `_recertify()`, always invoked)
**Wrong:** QA's repair loop rewrites files **after** the Code Reviewer issues the
certificate, and nothing re-reviewed them. Observed on project 142: Opus
certified `passed: true` at `16:52:09`, then QA regenerated code at `16:52:10+`.
Worse, the regeneration actively **defeated a security control** — the generated
`auth.py` correctly refused to boot without Auth0 config, so under retry pressure
the Developer "fixed" it by hardcoding fake credentials into `main.py`:
```python
if not os.getenv("AUTH0_DOMAIN"):
    os.environ["AUTH0_DOMAIN"] = "mock-domain.auth0.com"
```
and reintroduced `allow_origins=["*"]` with `allow_credentials=True` — the exact
insecure-CORS bug the binding contract was built to eliminate. None of it was
security-reviewed, because the review had already happened.
**Fix (structural, not instance-specific):**
- The certificate now carries `file_hashes` — a sha256-per-file fingerprint of
  **exactly** the code it attests to, written by `reviewer/orchestrator.run()`.
- `drifted_files(project_id, cert)` compares recorded hashes against disk, so
  drift is detectable **no matter which stage caused it** — it does not depend on
  that stage declaring its own edits.
- **FAILS CLOSED:** a certificate with no fingerprint cannot be *proven* to match
  disk, so every file is treated as drifted and re-reviewed. "We can't tell" must
  never resolve to "it's fine" for a security certificate.
- `qa/orchestrator._recertify()` runs **unconditionally** at the end of every QA
  pass (not only when QA thinks it changed something), re-reviews drifted files
  through `review_subset()` (full two-pass, always-Opus), folds the result into
  the certificate, adds a `recertified_after_qa` block, and **re-fingerprints**.
- If the re-check fails the project becomes **`security_blocked`**, never
  `tested`.

---

## PROJECT 142 — the before/after evidence for defect #6

Project 142 was the live witness: its certificate claimed `passed: true` over a
`main.py` that contained fake credentials and wildcard CORS.

| | BEFORE | AFTER |
| --- | --- | --- |
| certificate `passed` | **`true`** (a lie) | **`false`** (the truth) |
| certificate `file_hashes` | **0 files** | **15 files** |
| `main.py` `mock-domain.auth0.com` | **present** | **gone** |
| `main.py` `allow_origins=["*"]` | **present** | **gone** |
| project status | `qa_failed` | **`security_blocked`** |
| Opus issues found / fixed | 62 / 50 | 136 / 108 (74 / 58 added by re-review) |

Fail-closed recertification flagged all 15 files as drifted (file ids 196–210),
re-reviewed them, and rewrote 11. Final verification:

```
certificate covers : 15 files
files on disk now  : 15 files
mismatched hashes  : []
drifted_files()    : []
CERTIFICATE DESCRIBES EXACTLY WHAT IS ON DISK: True
certificate verdict: False
```

## Verification projects in the database (do not delete — Step 2+ uses these)

| project | status | qa_results | note |
| --- | --- | --- | --- |
| 140 | `qa_failed` | 2 rows, 0 passed | OpenAI quota was exhausted; BA/PI/Architect fell back to mocks. Not a valid sample. |
| 141 | `qa_failed` | 1 row, 0 passed | First genuinely-real run. Exposed defect #2 (no entrypoint). |
| 142 | `security_blocked` | **17 rows, 13 passed** | **Richest sample.** L1+L2 actually executed. Now the defect-#6 evidence. |
| 143 | `qa_failed` | 1 row, 0 passed | Exposed defect #4 (`Table 'users' is already defined`). |
| 144 | `security_blocked` | 0 rows | Opus gate blocked legitimately (9 of 14 files had unresolved criticals) → QA correctly did NOT run. Confirms the production-flow gate. |
| **145-148** | mixed | 20 rows | ⚠️ **SYNTHETIC VERIFICATION FIXTURES — NOT REAL USAGE, NOT REAL SPEND.** Created by `tests/test_qa_retry_loop.py` with all LLM calls patched out (`codegen.generate`, `dev_agents.build_ticket`, `reviewer.review_subset`). They cost **$0.00**. **Step 6's cost analysis must EXCLUDE them** — counting them as real pipeline runs would badly overstate spend. Keep them: they are the only post-fix evidence that the retry loop is productive. |

## Also fixed along the way (smaller, same session)

- `qa/orchestrator._file_for_target()` — used to pick whichever *shortest file
  containing the substring*; for the assembly target `"app"` that was effectively
  random and regenerated innocent files. Now: exact path match → quoted-route
  match (`"/api/orders"` as a real route declaration) → traceback attribution via
  `_TRACEBACK_FILE_RE` for assembly failures → `None` rather than a guess.
- `qa/outcome.TestOutcome.evidence` (new field) — carries the **full untruncated**
  startup log for attribution. The culprit's stack frame sat above the 800-char
  truncation in `failure_reason`, which is why one real failure got
  `retry_count = 0` and no repair attempt. `reason` stays the human-readable
  summary that is persisted.
- **Stale failures now clear.** Each round's outcomes replace the previous state;
  a test that failed earlier and no longer appears is recorded as passed with
  `resolved after N repair attempt(s)`. Previously a fixed problem stayed marked
  failed forever and wrongly set the project to `qa_failed`.
- `assembly._TEST_ENV` — supplies `AUTH0_DOMAIN`, `AUTH0_API_AUDIENCE`,
  `AUTH0_ISSUER`, `AUTH0_CLIENT_ID/SECRET`, `STRIPE_CLIENT_ID`,
  `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_TOKEN_ENC_KEY`,
  `SECRET_KEY` to the app under test. Obviously-fake loopback-only values. Without
  these, correct fail-fast behaviour was misdiagnosed as a Developer bug — which
  is what triggered the credential-hardcoding in defect #6.
- **Anti-workaround prompts.** `APP-1`'s description forbids hiding import
  errors, forbids setting/defaulting/mocking ANY environment variable, and
  requires an explicit CORS origin list (never `allow_origins=["*"]` with
  credentials). `qa/orchestrator._regenerate()`'s repair prompt says never make a
  test pass by weakening security — no hardcoded secrets, no removing fail-fast
  checks, no widening CORS, no dropping authorization; *"if the environment is
  missing configuration, LEAVE IT AS IS."*
- `developers/agents.py::_base_prompt()` — the already-generated file list now
  shows **filepaths**, not bare filenames, so `APP-1` can import routers by real
  module path (and duplicate-path collisions become visible to the agent).

## Regression coverage added (locks all of the above)

`backend/tests/test_qa_offline.py` — new section F: partial-boot must fail
assembly; `_file_for_target` no longer guesses (incl. traceback attribution);
mixed import styles execute a module exactly once; certificate drift detection +
fail-closed; test env supplies provider config; entrypoint ticket forbids silent
skips and fake secrets. Plus a root-cause case asserting
`"no runnable app found"` → `architect_rework`.
`backend/tests/test_architect_offline.py` — asserts across all 8 gating
scenarios: exactly one `APP-1`, it is **last**, it depends on every other ticket,
and its description demands `FastAPI` + `include_router`.

**Both suites passed at the end of the session**, as did the Weeks 3–5
8-scenario gating suite.

## Cost so far — and why Step 6 matters

⚠️ **SUPERSEDED — do not use these figures for decisions.** The measured
reference number is **$0.953857 per real build** (see "STEP 6 RESULT" above).
Everything in this section predates instrumentation, was run under
`CODEGEN_MODE=cheap`, and its central claim — that spend is "overwhelmingly
Opus" — was **measured to be wrong**: Opus is 17.6% of a real build, and
frontend codegen on Sonnet is 70%. Kept for history only.

Roughly **$3.50–4.50** of real spend: 5 full pipeline runs (140–144) plus 2
recertifications, overwhelmingly Claude Opus 4.8 (the security pass ignores
`CODEGEN_MODE` by design and runs on every file).

**Projects 145-148 cost $0.00** — synthetic fixtures with every LLM seam patched.
Exclude them from any cost calculation; only 140-144 represent real spend.

**That number is an ESTIMATE, not a measurement**, and it permanently stays one:
until 2026-07-21 `app/codegen.py::generate()` returned `(text, model_used)` and
captured no token usage anywhere, so the counts for runs 140-148 were never
recorded and **cannot be backfilled**. Instrumentation now exists (see "STEP 6
INSTRUMENTATION" above); only calls made from migration `0009` forward are
measured. Do not retro-fit a number onto the historical runs.

---

## NEXT STEPS for whoever resumes this

Review, regression, and commit are **done** (see STATUS at the top). What remains:

1. **Re-run the regression suites before trusting the tree**, if any time has
   passed or anything was touched:
   ```
   docker compose build backend && docker compose up -d backend
   for t in test_qa_offline test_architect_offline test_qa_retry_loop \
            test_qa_teardown test_token_instrumentation test_developers_offline; do
     docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
         backend python tests/$t.py
   done
   ```
   All six must print `RESULT: ALL CHECKS PASSED ✓`. Counts **measured
   2026-07-30**, not estimated: **75 / 226 / 19 / 35 / 70 / 16 = 443 checks.** (An
   older note here said 52 for `test_qa_offline`; that predated the Step 3
   root-cause cases.) All six are free — every LLM seam is patched or mocked.
   **Check the RESULT line AND the exit code, not the `[PASS]` count** — a suite
   that crashes mid-run still prints its earlier PASS lines, so counting them
   alone reports a false green (this exact mistake hid a `TypeError` in a new
   test; the non-zero exit is the authoritative signal).
   NOTE: `test_qa_classification.py` is deliberately NOT in this list — it makes
   real Gemini Flash-Lite calls (fractions of a cent, but not free).
2. **Steps 5 and 6 are the only work left, and they run TOGETHER as ONE paid
   run.** Step 6's instrumentation was deliberately built FIRST (see "STEP 6
   INSTRUMENTATION" above), so that single run produces the `next build` evidence
   AND the first measured cost number at the same time. Steps 2, 3 and 4 are
   CLOSED. Before greenlighting the run:
   - ~~Confirm the missing pricing rates~~ **DONE 2026-07-21** — all five rates
     are in `app/usage._PRICING` and verified to compute real costs. Sonnet 5's
     intro rate is time-bound (expires 2026-08-31) with an active tripwire.
   - **Apply the standing principle to both halves**: prove `next build` actually
     built something (a silent no-op also produces zero errors), and check the
     ROW COUNT in `llm_usage` for the run_id (a lost write and a cheap run look
     identical in a total).
   `tests/test_qa_retry_loop.py` is the pattern to copy for orchestrator-level
   scenarios (all LLM seams patched, deterministic, free);
   `tests/test_qa_classification.py` is the pattern for probing decision paths;
   `tests/test_qa_teardown.py` is the pattern for proving a resource was created
   before proving it was cleaned up.
3. **Steps 5 and 6 need fresh runs.** Use `backend/tests/verify_pipeline.py`.
   Budget ~$0.50-0.70 per full run (Opus reviews every file and ignores
   `CODEGEN_MODE` by design). **Build token instrumentation before Step 6** —
   `codegen.generate()` still captures no usage, so any cost figure today is a
   guess.
4. ~~Do not start Week 7 until verification is closed~~ — **VERIFICATION IS NOW
   CLOSED (all six steps, 2026-07-22).** Week 7 (DevOps #11) is unblocked. The
   point of the exercise stands: "built" and "verified" are different states, and
   six steps produced seven instances of one failure pattern plus a measured cost
   number that overturned the standing assumption about where spend goes.
   **Carry forward into Week 7:** the three known-open defects below are now
   implicated in a real failed build, not just theoretical — duplicate filepaths
   caused a cross-ticket `ImportError`, and no `package.json` is ever
   commissioned. Both are Architect defects and both block a working deliverable.

Permanent rules that still apply: **no `Co-Authored-By` line, ever**; never
commit `.env`; keep the repo private.

### Known-open, NOT yet fixed (deliberately logged, not actioned)
- ~~**Duplicate filepaths from the Architect/Developers.**~~ **FIXED 2026-07-22**
  — stopped being theoretical when it caused project 201's build to fail
  (`ImportError: cannot import name 'OrderItem'`; 3 tickets wrote
  `backend/app/main.py`, 2 wrote `routes/orders.py`, only ~13 of 16 paths
  survived). Fixed in three layers: `architect/builder._assign_filepaths()`
  gives every ticket one explicit unique path (deterministic disambiguation —
  a colliding `page.tsx` MOVES DIRECTORY rather than being renamed, since Next
  routes on the filename); `developers/agents._pin_path()` enforces it against
  the model's own choice; and `developers/orchestrator.run()` keeps an
  `owner_of` map so a residual collision is logged and relocated, never a silent
  overwrite. Historic sightings: `BE-2`+`BE-3` (142/143), `PAY-1`+`SEC-1` (140),
  `PAY-1`+`BE-3` (144).
- **No single fresh run has yet gone green end-to-end.** Every mechanism is
  verified, but run 144's gate blocked legitimately and 142 now correctly reports
  `passed: false`. That may say more about generated-code quality than about the
  QA agent. Worth establishing an all-green baseline at some point.
- **The Opus security pass is strict and non-deterministic** — 141/142 passed the
  gate; 144 blocked with 9 of 14 files failing. Expect variance between runs.

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
- **Every check must be able to FAIL for the reason it exists.** A test,
  gate, or classifier whose passing condition is satisfiable by *nothing
  happening* is decorative. Assert the positive FIRST — the resource
  EXISTED, the model REASONED, the certificate COVERS these files — and
  only then assert the property under test. "Absence of evidence" must
  never resolve to "evidence of success." (Added 2026-07-21 after this
  same pattern turned out to BE the finding in all four of verification
  Steps 1-4 — the fail-open certificate, two short-circuit
  classifications, and the teardown checks themselves. See STANDING
  PRINCIPLE above.)
- **Any agent whose output BRANCHES BEHAVIOUR must be tested for
  repeat-run consistency** — classification, routing, and gating
  decisions get run N times on identical input, and disagreement
  is a finding, not noise. A single correct-looking answer proves
  nothing about the next one. (Added 2026-07-21 after Step 3
  verification caught the QA classifier returning three different
  tiers across five identical calls — and caught it BY ACCIDENT,
  because a repeat run happened to disagree with the first.)
  Untested this way so far, and worth doing: **BA
  `understanding.classify()`** (decides which questions to skip,
  whether to run competitive research, and platform/mobile
  routing) and **Architect ticket generation** (decides what gets
  built at all). Both branch behaviour on LLM output; neither has
  ever been run twice on the same input to see if it agrees with
  itself.

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
| 10  | QA Agent              | No — counts only    | Gemini 2.5 Flash-Lite         | 3 levels of testing + root cause tracing (built Week 6)      |
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
- DevOps, Docs, simple tasks: GPT-4o mini
  (QA was here originally — SUPERSEDED by UPDATED ROUTING below: QA runs on
  Gemini 2.5 Flash-Lite as of Week 6, in code and in the blueprint's llm_routing)
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

---

**Week 6 — QA Agent (#10) — DONE**
Three levels of testing against a REAL, temporarily running instance of the
generated app. Verified against synthetic good/bad/broken apps: 5 classes of
planted vulnerability caught, 0 false positives on well-built code (34 tests),
assembly failure handled as a finding rather than a crash. QA never talks to the
user. Week-5 Architect gating suite still passes.

### New agent / layer (Week 6)
- **Ephemeral test environment** (`app/qa/assembly.py`) — the prerequisite that
  made live testing possible. Pulls files from `generated_files`, writes them to
  a temp dir in the binding-contract module layout (path-traversal safe), creates
  a venv with `--system-site-packages` (so fastapi/sqlalchemy are reused, not
  refetched), installs only genuinely missing deps, provisions a THROWAWAY
  Postgres database, launches uvicorn on a random free port bound to 127.0.0.1,
  waits for health, and **always** tears everything down in a `finally`.
  Deliberately minimal: no AWS, no SSL, no domain, no persistence — full
  deployment stays scoped to DevOps (#11, Week 7).
  **Assembly failure is a QA FINDING, not a crash**: `assemble()` never raises;
  it returns failures that are logged as Level 1 issues with root-cause tracing.
- **LEVEL 1 — user interaction** (`app/qa/level1.py`) — endpoints discovered from
  the RUNNING app's own `/openapi.json` (tests what was actually built, not what
  was intended). Per endpoint: happy path, empty inputs, wrong data types,
  double-click (two concurrent identical requests), very long inputs (2000
  chars), missing required fields one at a time, and network interruption
  (client abort, then verify the app still responds). Rule: **5xx = failure,
  4xx = pass** (rejecting bad input is the app working). Generated UI files get a
  static pass: relative/alias imports must resolve to files that were actually
  generated, and pages must export a component.
- **LEVEL 2 — security attack simulation** (`app/qa/level2.py`) — actively
  exploits the running instance: access without login, invalid credentials, SQL
  injection through **every** input (declared body fields, free-form bodies,
  query strings, path params), IDOR by changing IDs in the URL, negative payment
  amounts, malicious file names (only if an upload endpoint exists).
  **Scope guard:** `_assert_local()` runs before every request — QA can only ever
  attack the throwaway loopback instance, never an external host.
- **LEVEL 3 — root cause tracing** (`app/qa/root_cause.py`) — labels each failure
  `developer_fix` / `developer_rework` / `architect_rework` / `ba_rework`.
  Deterministic rules decide first (free + reliable); the QA model (Gemini 2.5
  Flash-Lite @ 0.1) is consulted only when they are ambiguous.
- **Bounded repair loop** (`app/qa/orchestrator.py`) — developer-level failures
  are grouped by the responsible file and sent back to the **Developer agent**
  with the QA evidence appended to the ticket, then re-assembled and re-tested.
  Max 3 retries per issue; still failing → marked escalated, logged, run
  CONTINUES. The round counter is the only loop driver — it cannot run forever.

### ROUTING POLICY (decided this session)
Only `developer_*` causes are auto-routed back. `architect_rework` and
`ba_rework` are classified, logged and **escalated for a human** — re-running the
Architect regenerates the whole blueprint (invalidating the built code and the
Week-5 security certificate), and BA rework needs the user, which QA must never
talk to.

### Files created / changed in Week 6
- `app/qa/assembly.py`, `level1.py`, `level2.py`, `root_cause.py`,
  `orchestrator.py`, `graph.py`, `outcome.py`, `__init__.py` (all new)
- `app/models.py` — QAResult table
- `alembic/versions/0007_qa_results.py` — qa_results
- `app/config.py` — qa_model (gemini-2.5-flash-lite), qa_temperature (0.1),
  bounded timeouts (install/boot/request), qa_max_retries (3),
  qa_frontend_full_build (default False)
- `app/architect/builder.py` — blueprint `llm_routing.qa` was a stale
  `gpt-4o-mini`; corrected to `gemini-2.5-flash-lite` per CONTEXT UPDATED ROUTING
- `app/main.py` — POST /pipeline/qa, GET /pipeline/{id}/qa-status, `_run_qa`
- `app/schemas.py` — QAStatusResponse (counts only)
- `frontend/app/page.tsx` — secure→QA handoff; "Testing every button and
  screen…" → "X tests run. Everything passed. ✓" (no test names, no agent or
  model names)
- `backend/tests/test_qa_offline.py` (new) — QA verification suite

### New database (Week 6)
- `qa_results` (id, project_id, **blueprint_id**, test_name, test_level, passed,
  failure_reason, root_cause_agent, retry_count, created_at)
- `blueprint_id` pins every result to the exact blueprint version tested. BA/
  Architect classification is non-deterministic on borderline inputs, so **a QA
  run is a snapshot of THAT blueprint, not a permanent guarantee** — a future
  re-test can be compared against the same version.

### What now works end to end
**BA → PI review-gate → Build it → Architect → design explanation → Developers →
Code Reviewer (Opus security) → QA (Testing every button and screen…) → "X tests
run. Everything passed. ✓"** Redis `qa:status:{id}` + `qa_report:{id}`; project
status `tested` / `qa_failed`.

### Scope note — frontend "build check"
A real `npm install && next build` per QA run downloads hundreds of MB and takes
minutes, so it is **opt-in** via `settings.qa_frontend_full_build` (default
False). With it off, UI files are still checked for imports that resolve to real
generated files (the cross-file drift bug) and for pages that actually export a
component. Turn it on for a demo if a full UI compile is wanted.

### Cost note (Week 6)
QA is nearly free: test generation is **deterministic Python**, not LLM. The only
model call is Level 3 root-cause classification, on Gemini Flash-Lite, and only
when the deterministic rules are ambiguous. The expensive part is wall-clock
(venv + boot per round), not tokens.

### Scope note — 3 levels built, not the 5 in the Master Blueprint
The original agent table said "5 levels of testing"; the Week 6 spec defined
THREE (user interaction, security attack simulation, root cause tracing) and
that is exactly what was built. The agent table has been corrected to say 3.
Not a gap to silently fix later — if the remaining two levels are still wanted
(candidates: load/performance testing and cross-browser/responsive testing),
they are NEW scope and need their own spec. Do not assume they exist.

### Current phase
**Week 7 — DevOps agent (#11) — UNBLOCKED. Week 6 verification is COMPLETE
(2026-07-30); see the RESUME HERE block at the top.** Real deployment: AWS, SSL,
domain, Safe Mode snapshots, version timeline — the thing that turns generated
files into a hosted app with a live URL. Note Week 6 deliberately built only a
throwaway LOCAL test instance; none of that assembly logic is a deployment
pipeline. **Week 7 must generate a `requirements.txt`** (QA import-scans, but a
real deploy can't). Also still pending: Design Review (#8), Qdrant vector store,
code export to disk. Residual generated-code-QUALITY defects (FastAPI
response_model, flaky SSG prerender, wrong-symbol imports) are logged known-open
for a later dedicated code-quality pass — NOT Week 7's job.

### What NOT to touch next session
- Do NOT modify the BA, Product Intelligence, Architect, Developer, Code
  Reviewer, or QA agents unless the new week requires it — all tested and locked.
- Do NOT change existing schemas or migrations (0001–0007), the Redis
  conversation/pipeline/build/secure/qa state formats, or the /conversation/* and
  /pipeline/* endpoint contracts.
- Do NOT weaken the BINDING PROJECT CONTRACT or the foundation-first ordering.
- Security review is ALWAYS claude-opus-4-8 and must always keep bypass_cheap.
- Do NOT let QA auto-rerun the Architect or BA (see ROUTING POLICY above), and do
  NOT remove `_assert_local()` — the attack simulation must stay loopback-only.
- Do NOT remove the `finally: teardown()` — a leaked test container/DB/temp dir
  per run would pile up fast.
- Do NOT build Design Review, DevOps, Documentation, Monitoring, Auto-fix, or
  Cost Tracker agents until their week.

### What I learned — Week 6
- **You cannot test what you cannot run.** The three test levels were the easy
  part; the real prerequisite was assembly — turning code stored as TEXT in a
  database back into a running process. Most of the difficulty in "add testing"
  was environment plumbing, not test logic.
- **Assembly failure IS the test result.** The instinct is to treat "the app
  won't start" as an error that aborts QA. It is actually the single most
  valuable finding QA can produce, and it deserves the same root-cause tracing as
  any other bug. Designing `assemble()` to never raise — to return findings
  instead — is what made that possible.
- **4xx is a pass, 5xx is a failure.** The whole of Level 1 collapses to one
  rule. An app that *rejects* bad input is working correctly; an app that
  *crashes* on it is not. Getting that rule right up front removed almost all
  ambiguity about what counts as a bug.
- **Deterministic tests beat generated tests.** Empty input, wrong types, long
  strings, double-clicks and missing fields are all mechanically derivable from
  the OpenAPI schema. Generating them in Python made QA free, fast, repeatable,
  and immune to model non-determinism — the LLM is reserved for the one genuinely
  judgement-shaped task, root-cause classification.
- **Test the tester with a known-bad fixture.** A QA agent that reports "all
  passed" is indistinguishable from a QA agent that is silently broken. Running
  it against a deliberately vulnerable app proved it catches real bugs, and
  running it against a well-built app proved it does not invent them. That second
  half matters just as much — a noisy tester gets ignored.
- **Coverage gaps hide in the "untyped" case.** The planted SQL-injection bug was
  initially missed because the endpoint took a free-form dict body, so OpenAPI
  declared no fields to attack — exactly the endpoints most likely to be unsafe.
  Anything that iterates over *declared* inputs needs an explicit answer for
  inputs that were never declared.
- **Autonomy needs a blast radius.** "Send it back to the right agent
  automatically" sounds good until you notice that re-running the Architect
  would discard a passing Opus security certificate. Auto-fixing at the Developer
  level is safe and useful; anything that invalidates upstream work should stop
  and ask a human.

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
- **The generated app is NOT deployed.** Generated code is stored as TEXT in
  `generated_files`. There is NO live/hosted URL for a generated app — that is
  the **DevOps agent (#11)**, Week 7. localhost:3000 is the PLATFORM, not any
  generated app.
  **Updated in Week 6:** the QA agent DOES now write those files to disk and run
  them, but only as a **throwaway local instance** (temp dir + venv + random
  loopback port + temp Postgres DB), torn down the moment testing finishes. That
  is test scaffolding, NOT deployment: no AWS, no SSL, no domain, no persistence,
  no Safe Mode, no versioning. Do not mistake `app/qa/assembly.py` for a deploy
  pipeline.
- **No code export to disk** yet (core rule says "full code export always
  available") — not implemented.
- **Absolute imports** in generated code (`backend.app.models`) may not resolve
  when packaged — flagged for the Code Reviewer / a future assembly step.
- **Qdrant vector store** (in the locked tech stack) — not added.
- **Agents built:** BA(#1), Product Intelligence(#2), Architect(#3),
  Developers(#4–7), Code Reviewer(#9), QA(#10 — Week 6).
  **NOT built:** Design Review(#8),
  DevOps(#11), Documentation(#12), Monitoring(#13), Auto-fix(#14),
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
