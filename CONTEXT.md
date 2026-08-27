# Autonomous AI Engineering Organization — CONTEXT.md

This file is Claude Code's memory between sessions. Read this
fully before doing anything else in this project.

---

# ⏭️⏭️⏭️ RESUME HERE — AUTHORITATIVE HANDOFF (2026-08-26 night). A FRESH CHAT STARTS FROM THIS BLOCK.
> Everything below this block (the old "RESUME HERE (2026-08-21)" and §1–§1bb) is HISTORY/detail. §1cc–§1mm are the
> current per-fix record for THIS session's work (Fixes #37–#48). Read THIS block first; drill into §1cc–§1mm as needed.

## 0-A. WHERE WE ARE RIGHT NOW (2026-08-26 night)
- **EVERYTHING IS TORN DOWN → $0 SPEND.** `docker compose down` done; all ephemeral generated-app stacks removed
  (`aiorg_p1843/1935/1936/1937/1950_*`). Nothing running, no scheduled tasks armed. **Restart with `docker compose up -d`.**
  Platform DB + secrets volumes PERSIST (safe). Generated-app stacks are ephemeral and gone; the `projects` rows
  (1934/1935/1936/1937/1948/1949/1950) remain in the platform DB as fixture sources.
- **ALL CODE COMMITTED + PUSHED. `HEAD == origin/master` (tip = the Auth0 tenant-cleanup commit), clean tree.**
  Git user Rajkumar2002-Rk, repo github.com/Rajkumar2002-Rk/ai-org (still PRIVATE — user chose to publish as-is when
  ready; see 0-E). **COMMIT RULE: NO Claude co-author line** (user asked repeatedly — never add `Co-Authored-By: Claude`).
- **2026-08-27 follow-up:** Auth0 tenant CLEANED (0-G #1 now DONE) via the new operator tool
  `backend/tools/auth0_cleanup.py` — deleted 8 stale `proj-*` clients + 9 `proj-*` APIs, tenant headroom restored,
  M2M delete-scopes confirmed. Still $0 spend / nothing running (used only auto-removed `docker compose run --rm` containers).
- **Config (.env):** `SECURITY_REVIEW_ENABLED=true` (Opus ON), `CODEGEN_MODE=real`, `DEPLOY_TARGET=local`. `.env`
  is gitignored and holds the REAL Stripe test keys / Auth0 Mgmt / SMTP creds — NEVER commit it.
- **This session = the Fix #37–#48 wave (2026-08-24 → 08-26), 12 fixes.** All grounded in REAL captured run bugs,
  each locked with a regression test. Detail per fix in §1cc–§1mm.

## 0-B. THE MILESTONES REACHED THIS SESSION (the payoff)
- 🏆 **Run 1935 (Opus OFF, ~$1):** FIRST fresh full run to a genuinely LIVE + CLEAN app end-to-end, QA 100/100. §1jj.
- 🏆🏆 **Run 1936 (Opus ON, ~$3):** FIRST LIVE + SECURITY-CERTIFIED app via the COMPLETE production flow —
  Build 19/19 → real Opus PASS (certified) → QA 93/93 → DEPLOY LIVE, with Stripe+Auth0+email provisioned. §1kk.
- 🏆🏆🏆 **Runs 1937 & 1950 (user's OWN HANDS-ON runs via the UI at localhost:3000):** the user personally drove the
  BA conversation → onboarding → build → deploy. 1937 went LIVE + certified (QA 90/90). 1950 the user COMPLETED the
  Stripe connect step (real acct_), Build/Opus/QA all perfect (103/103), deploy exposed 3 more bugs (all fixed). §1ll, §1mm.

## 0-C. EVERY FIX THIS SESSION — bug → how found → how fixed → where (all committed, tested, live)
- **#37 (§1cc)** — frontend Auth0 `NEXT_PUBLIC_AUTH0_AUDIENCE` empty at deploy (mapped only from `API_AUDIENCE`, run
  1843 stored it as `AUTH0_AUDIENCE`) → gated calls 401 post-login. Fix: `manifest.frontend_public_env` maps audience
  from EITHER alias. `devops/manifest.py`.
- **#38 (§1cc)** — generated apps looked "plain" (FND-5 globals.css said "keep minimal"). Fix: `builder._design_system_css`
  bakes a DETERMINISTIC themed globals.css from the BA's brand_color+vibe (tokens, styled native elements, animations,
  prefers-reduced-motion); `_brand_palette` maps free-text colours ('black'→#000, 'warm brown'→coffee). Boilerplate
  tickets with fixed `content` are written verbatim (no LLM). `architect/builder.py`. ALSO added menu-item PHOTOS
  (`image_url` column + MENU-1 persist + MENU-2 form + a frontend-prompt mandate to render `<img>`).
- **#39 (§1ee)** — a HALLUCINATED pip package (`starlette_limiter`) failed the whole install → boot_failed (run 1869).
  Fix: `assembly._nonexistent_pkgs` parses pip "No matching distribution" → `_missing_package_findings` maps to the
  importing file → boot-repair loop regenerates it. `qa/assembly.py` + prompt nudge (use `slowapi`).
- **#40 (§1ff)** — companion to #39: OFFLINE build-gate blocklist `agents.hallucinated_package_imports` +
  `_HALLUCINATED_PACKAGES={starlette-limiter}` catches KNOWN hallucinations before smoke_boot. `developers/agents.py`.
- **#41 (§1gg)** — frontend truncation gate FALSE-POSITIVE on an apostrophe in JSX text ("Stripe's") → failed a COMPLETE
  file (run 1887). Fix: in `_strip_code`, a `'`/`"` preceded by a word char is a contraction, not a string delimiter.
  `developers/agents.py`.
- **#42 (§1hh)** — 🔑 KEY ARCHITECTURAL FIX. The build gate certifies clean code, then Opus auto-fix + QA regen REWRITE
  files WITHOUT re-validation → reintroduce caught defects (run 1914: Opus wrapped get_db in the #24 swallow → a
  CERTIFIED app that 500'd on every DB endpoint; QA renamed `source`→`source_name`). Fix: `agents.rewrite_integrity_gate`
  (the full build-gate checks as a reusable fn) + `reviewer._accept_or_reject_fix` (rejects an Opus fix that reintroduces
  a defect, keeps the certified-clean original) + QA `_gate_regenerated` delegates to it. `reviewer/orchestrator.py`,
  `qa/orchestrator.py`, `developers/agents.py`.
- **#43 (§1ii)** — deploy startup crash: `security.py` fail-fasts at import on `ENCRYPTION_KEY`/`SECRET_KEY`, but the
  platform minted only `FERNET_KEY`/`TOKEN_ENCRYPTION_KEY`/`SESSION_SECRET_KEY` (run 1934). QA passed (auto-fills any
  var); deploy injects only the real set. Fix: add generic crypto/secret NAMES to `provisioning._CRYPTO_KEYS`
  (ENCRYPTION_KEY/TOKEN_ENC_KEY/APP_ENCRYPTION_KEY→Fernet; SECRET_KEY/APP_SECRET_KEY/JWT_SECRET_KEY→random). `devops/provisioning.py`.
- **#44 (top of §TODO, `3fcc089`)** — FRONTEND UI BUG (user's screenshot): the BA `connect_accounts` stage said "tap the
  button" but the frontend had NO handler for `ui.kind="connect_accounts"` → NO button rendered → owner could never
  connect Stripe. Fix: added a `connect_accounts` render block in `frontend/app/page.tsx` (a per-provider button opening
  `${API_URL}${provider.url}` = the Stripe OAuth flow, + next/skip). VERIFIED end-to-end (button payload + the endpoint
  307-redirects to connect.stripe.com).
- **#45 (§TODO, `1b09654`)** — a NOT-NULL datetime column with no default that no handler sets → 500 on EVERY create
  (run 1937 `created_at`). Fix: `agents.timestamp_not_null_no_default` AST detector (datetime-only = zero-FP) → repair
  adds `server_default=sa.func.now()`. Wired into `_collect_stubs` AND `rewrite_integrity_gate`. **PROVEN LIVE in run
  1950** — caught + auto-repaired 3 columns. `developers/agents.py` + `orchestrator.py`.
- **#46 (§1mm, `05939a3`)** — deploy startup: `stripe.py` fail-fasts on `STRIPE_STATE_SIGNING_KEY`, platform minted only
  `STRIPE_STATE_SECRET` (run 1950; #43 class). Fix: add STRIPE_STATE_SIGNING_KEY/STRIPE_STATE_SIGN_KEY/STATE_SIGNING_KEY
  to `_CRYPTO_KEYS`. `devops/provisioning.py`.
- **#47 (§1mm, `d9bb6b8`)** — Auth0 per-project provisioning 403 (tenant app-limit) KILLED the whole deploy (run 1950).
  Fix: `auth0_provision.placeholder_config` injects safe `.invalid` placeholder Auth0 config so the app BOOTS + goes LIVE
  (public features work, login degraded, reported as `auth_degraded`) instead of dying. `onboarding/auth0_provision.py`,
  `devops/orchestrator.py`.
- **#48 (§1mm, `0249df4`)** — the frontend half of #42: a post-build rewrite truncated `admin/menu/page.tsx` → `next build`
  failed at deploy (run 1950). `rewrite_integrity_gate` only re-checked backend `.py`. Fix: it now re-checks FRONTEND files
  (frontend_incomplete + frontend_css_leak → `frontend_repairs`); the reviewer rejects a truncating Opus frontend fix.
  `developers/agents.py`.

## 0-D. THE RUNS THIS SESSION (paid measurement runs — what each proved/surfaced)
1869 boot_failed → surfaced #39. 1887 build-error (false-pos) → #41; also confirmed #35/#38/menu-images landed.
1914 CERTIFIED-but-500s (Opus reintroduced the swallow) → #42. 1934 deploy startup crash → #43; QA 84/88.
**1935 LIVE+clean (Opus off) 🏆.** **1936 LIVE+CERTIFIED (Opus on) 🏆🏆.** **1937 user's run → LIVE+certified 🏆🏆🏆.**
**1950 user's run, Stripe connected → #45 proven live, then #46/#47/#48.** (1843 is the older LIVE-but-unusable run; §1w/§1x.)

## 0-E. NON-FIX WORK THIS SESSION (all committed)
- **README rewritten for RECRUITERS** (`fefc7ad` etc.) — hero screenshot `docs/demo.png`, badges, a rendered mermaid
  architecture diagram, a Code Integrity Engine gate table, tech-stack table, "what this demonstrates" skills section.
  **MIT LICENSE added** (`Copyright (c) 2026 Rajkumar` — user may swap full name). Purpose: the user is job-hunting and
  uses this repo as proof (they list it under Work History as an independent project; portable blurb was given).
- **Pre-public identifier scrub** (`9bfac76`): the working tree is scrubbed of the real infra identifiers
  (`rajkumarai.dev`→example.com, Auth0 tenant `dev-eldyvyvbd3kd2gnw`→dev-tenant, Route53 zone `Z027…`→placeholder) and is
  secrets-clean. Those identifiers STILL linger in OLD git history (NON-secret). A `git filter-repo --replace-text` history
  scrub is PREPARED (rules at `scratchpad/history-scrub-replacements.txt`; a backup bundle exists) but NOT run — the
  **classifier blocks the destructive rewrite**, so the USER must run it if they want it. User chose Option A = publish
  as-is (identifiers are non-secret). To make public: `gh repo edit Rajkumar2002-Rk/ai-org --visibility public --accept-visibility-change-consequences`.
- The full 133-commit history was scanned: NO real credentials/API keys/tokens/.env ever committed. `.gitignore` now
  also ignores `.claude/settings.local.json`.

## 0-F. HOW TO OPERATE THE PLATFORM (for the next session)
- **Start:** `docker compose up -d` (backend :8000, frontend :3000, postgres, redis). Health: `curl localhost:8000/health`.
- **A full run costs money** (real LLM). Opus ON ≈ $3, Opus OFF (skip-cert) ≈ $1 — flip `SECURITY_REVIEW_ENABLED` in
  `.env` + `docker compose up -d backend`. Opus OFF is enough to test codegen/deploy; Opus ON for the full certified flow.
  ALWAYS get the user's OK before a paid run.
- **Two ways to run:** (a) the UI — user opens localhost:3000, talks to the BA, does onboarding, watches stages;
  (b) the scripted driver `docker compose exec -T backend python tests/verify_pipeline.py` (a coffee-shop idea; walks
  BA→Architect→Build→smoke_boot→Opus→QA→Deploy). A conversation-only walkthrough (no build) is in
  `scratchpad/onboarding_walkthrough.py`.
- **Check a run's progress** (used constantly): query the DB/redis, e.g. `docker compose exec -T backend python -c "..."`
  reading `projects.status` + redis keys `build:status:<pid>` / `secure:` / `qa:` / `deploy:status:<pid>` +
  `qa_report:<pid>` / `deploy_report:<pid>`. Generated files live in `generated_files` (project_id, filepath, content, status).
  The newest `projects.id` is the user's latest run.
- **💡 CHEAP diagnosis without paying (§1cc):** (a) $0 — load a run's stored `generated_files` and run any deterministic
  gate against them offline; (b) near-$0 — DEPLOY existing files without codegen: mint `reviewer.skipped_certificate` into
  redis `security_cert:<pid>` then POST `/pipeline/deploy` (the classifier may block the direct cert write — ask the user).
  Do NOT re-run `/pipeline/build` to "redeploy existing files" — it REGENERATES everything (~$1 + variance).
- **Offline test suites** (deterministic, LLM-free, no $): `docker compose run --rm --no-deps -e PYTHONPATH=/app -v
  "$PWD/backend:/app" backend python tests/test_developers_offline.py` (also test_qa_offline, test_devops_offline,
  test_onboarding_offline, test_architect_offline, …). ALWAYS `docker compose build backend && docker compose up -d backend`
  after editing backend code so the running container has your change (the image is baked, not mounted).
- **Make a deployed app PLAYABLE** (throwaway, NEVER commit): seed `menu_items` into the app's DB (created_at may be
  NOT-NULL with no default → provide it or `ALTER … DROP NOT NULL`); add a plain-HTTP Caddy `:80` block (copy
  `scratchpad/Caddyfile_1935_http` into the caddy container, `caddy reload`) for a no-cert-warning URL; for admin, append a
  demo auth-bypass to the deployed `auth.py` + patch the frontend admin page's isAuthenticated gate + `npm run build`.

## 0-G. OPEN ITEMS / TODO FOR NEXT SESSION (priority order)
1. ✅ **DONE (2026-08-27) — Auth0 tenant cleaned, headroom restored.** The tenant had filled with 8 auto-provisioned
   `proj-*` clients + 9 `proj-*` APIs from our many runs (403 on create). Built an operator cleanup tool
   `backend/tools/auth0_cleanup.py` (read-only inventory by default; `--delete` to apply; never touches non-`proj-`
   apps — Default App / Mgmt M2M / Auth0 Management API are safe). Ran it via
   `docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" backend python tools/auth0_cleanup.py`
   → deleted ALL 8 clients + 9 APIs (a few 429 rate-limits cleared on a re-run). Successful deletes PROVE the M2M app
   holds `delete:clients`+`delete:resource_servers`. `create:*` scopes are separate (only proven by a live deploy) but
   were never removed. Fix #47 still keeps deploys LIVE (login-degraded) if the tenant ever refills; run the tool again.
2. **LOWER priority gate:** the run-1934 `MenuItemResponse` malformed-Pydantic-schema → `GET /menu` 500 is still ungated
   (a "response_model is a complete Pydantic schema" gate would harden it). LLM-variance; 1935/1936/1950 didn't hit it.
3. **Optional:** run the `git filter-repo` history scrub (0-E) if the user wants the non-secret identifiers gone from
   history before/after going public. Prepared, not run (classifier-blocked for me — user runs it).
4. **1950 itself** won't deploy without regenerating its already-broken `admin/menu/page.tsx` (Fix #48 prevents the class
   going forward, not that specific file).

## 🎯 30-SECOND ORIENTATION (older milestone note — superseded by 0-A/0-B above)
**🏆🏆🏆 NEWEST + BIGGEST MILESTONE (2026-08-26, run 1936): the FIRST fresh full run to reach a LIVE, SECURITY-
CERTIFIED, CLEAN app via the COMPLETE PRODUCTION FLOW (real Opus ON)** — BA → Architect → Build 19/19 →
smoke_boot → **real Opus PASS (claude-opus-4-8, 99 found/86 fixed, CERTIFIED)** → **QA 93/93 (zero fails)** →
**DEPLOY LIVE + security_certified=true at https://localhost:58171**, with **Stripe Connect + Auth0 + email +
crypto keys** all provisioned live at deploy. `/`, `/menu`, `/api/menu`, `/health` all 200. **Fix #42 HELD even
after Opus rewrote 86 issues** (no reintroduced defects — QA perfect). See §1kk.
Prior: run 1935 (2026-08-25) — same but Opus OFF (~$1, QA 100/100, §1jj); run 1614 (first LIVE deploy, not usable
end-to-end). The 2026-08-24/26 fix wave (#37–#43) is what got here — §1cc–§1kk. (The RESUME text below is the
STALE 2026-08-21 handoff; §1cc–§1kk are the current record.)

**Everything is COMMITTED + PUSHED. `HEAD == origin/master == 9114b0c`, clean tree.** All 15 offline suites
pass. Platform is TORN DOWN for the weekend (nothing running, $0 spend). Volumes persist (DB/secrets safe).
To restart Monday: `docker compose up -d`.

## WHAT WAS DONE THIS SESSION (2026-08-19 → 08-21), all committed
- **FIX #24** get_db swallows HTTPException→500 gate (§1k). Validated live on 1289 QA (103/1, all 500s fixed).
- **FIX #26** platform provisioning — mint+persist crypto keys, provision Redis, config defaults (§1m).
- **OWNER-ONBOARDING EPIC (slices 1–4)** — platform-held provider injection; Stripe click-to-connect (new BA
  `connect_accounts` stage + `/connect/stripe/*` OAuth); Auth0 per-project auto-provision (Mgmt API); codegen
  consumption contracts (`STRIPE_CONNECTED_ACCOUNT_ID`, `NEXT_PUBLIC_AUTH0_*`). §1n–§1q. **ALL 3 PROVIDERS
  VERIFIED LIVE** on free/test tiers: Stripe test-mode connect (real `acct_`), Auth0 tenant provision, Mailtrap
  SMTP send. `PLAN_owner_onboarding.md` = the design doc.
- **FIX #27** third-party import gate + BUILD SELF-HEAL (run 1496 `stripe.api_resources`); §1r. Later hardened
  (ground-truth `from X import Y` probe, no hasattr FP) + **FIX #29** pin broken `fastapi-limiter==0.1.6` (§1t).
- **FIX #28** endpoint-completeness self-heal (run 1557 missing `GET /orders/{order_id}`); §1s.
- **FIX #30** durable FRONTEND gates — npm-dep completeness (manifest auto-adds missing deps) + CSS-in-TSX (§1u).
- **FIX #31** provider env-var NAME contracts (Auth0/Stripe aliases: API_AUDIENCE+AUTH0_AUDIENCE,
  STRIPE_SECRET_KEY+CLIENT_SECRET+API_KEY) + missing in-project MODULE gate (`backend.app.catalog`); §1v/§1w.
- **FIX #32** frontend LOGIN completeness — Architect FND-7 ticket + `frontend_missing_login` gate + prompt (§1x).
- **FIX #33** duplicate-endpoint gate (run 1614 `POST /orders` in order.py AND orders.py); §1y.
- **FIX #34** frontend login QUALITY gate — `frontend_missing_login` now requires BOTH an `<Auth0Provider>`
  wrap AND a token attach (catches the partially-wired login, not just total absence); §1z. Backend rebuilt live.
- **FIX #35** Architect-level duplicate-route CURE — `_merge_duplicate_route_tickets` folds two sprint tickets
  that own the same resource (order.py+orders.py) into one BEFORE codegen, so the `POST /orders` split never
  happens; Fix #33's gate stays as the post-hoc backstop; §1aa. Backend rebuilt live.
- **FIX #36** Fix #33 FALSE POSITIVE (run 1843): `duplicate_endpoints` scanned NON-route .py files — the SEC-1
  security helper carried an illustrative `@app.post('/orders')`, invented a phantom `POST /orders` dup, told
  the REAL order.py to drop its route → BE-1 stubbed → build error. Now only route MODULES (`routes/` + main.py)
  are scanned; §1bb. Backend rebuilt live.
- **FIX #37** frontend Auth0 audience alias — `manifest.frontend_public_env` now maps `NEXT_PUBLIC_AUTH0_AUDIENCE`
  from EITHER `API_AUDIENCE` or `AUTH0_AUDIENCE` (1843 deploy had it empty → gated calls would 401 post-login);
  §1cc. Backend rebuilt; 1843 redeployed with the audience now flowing.
- **💡 CHEAP measurement method (§1cc):** $0 offline gate-replay + near-$0 deploy-of-existing-files (skip-cert +
  /pipeline/deploy, no codegen) replace most paid runs. Use these before paying for a fresh full run.
- **FIX #38** themed design-system globals.css — `_design_system_css` bakes a polished, brand-themed stylesheet
  (tokens + styled native elements + animations) deterministically; boilerplate tickets with fixed content are
  written verbatim (no LLM). Fixes the "plain website" feedback. §1dd. (Local 1843 app also made playable — hacks
  only, not committed.)
- Runs: 1496 (stripe import), 1557 (missing endpoint), 1614 (→ LIVE), 1843 (build error → Fix #36 fixed cause;
  deployed the existing files for $0 → Fix #34 login CODE verified good + Fix #37 audience bug found/fixed;
  Fix #35 CONFIRMED — single order.py, no split). All left in DB.
- ⚠️ Mid-session macOS revoked repo file access; some commits were made via the Docker daemon. NOW RESTORED.

## ⏭️ NEXT (Monday) — pick a GROUNDED build (regression-test against a REAL captured bug; NO speculation)
The pipeline reliably reaches a LIVE deploy. Remaining REAL, grounded gaps (in priority order):
1. **Frontend-auth QUALITY (the honest #1 frontier):** FIX #32 commissions FND-7 login + a gate for TOTAL
   absence; **FIX #34 (§1z) — DONE 2026-08-23** — upgraded the gate to require BOTH an `<Auth0Provider>` wrap
   AND a token attach, so the partially-wired login is now caught deterministically. STILL OPEN: whether a
   *generated* login actually WORKS end-to-end (right subtree wrapped, ALL protected calls carry the token) is
   only provable by running the app → option (b) a fresh run to MEASURE FND-7's login live (~$3, needs user OK).
2. **A fresh MEASUREMENT run** to surface the next real bug + verify #32's login live (~$3, ASK first).
3. ✅ DONE — FIX #35 (§1aa): the Architect-level cure. `_merge_duplicate_route_tickets` folds two tickets that
   own the same resource (order.py+orders.py) into one BEFORE codegen, so the split never happens; #33's gate
   stays as the post-hoc backstop.
- Other honest edges (LOW priority): pin ONE canonical provider var name in codegen (aliases already work);
  the Caddy sibling-container probe 000 is cosmetic (platform health gate + host-port URL work). §1w.
- ⛔ Deploy gap #1 SECRETS: the OWNER-account onboarding is now BUILT + live-verified (Stripe/Auth0/email).
  The operator's real creds live in `.env` (STRIPE_* test keys, AUTH0_MGMT_*, Mailtrap SMTP). Do NOT commit `.env`.

> This block is the AUTHORITATIVE resume point. §1k–§1y (most recent first, below §1) have full per-fix detail.
> A fresh session with zero memory should execute from here. Read this whole block first, then skim §1's fix
> list. The 31 deterministic fixes (thru #48; +#44 frontend Connect-Stripe button) + onboarding epic are ALL live in the committed code.

## 0. ONE-PARAGRAPH ORIENTATION
This platform is an autonomous "AI engineering org": a BA agent interviews the user →
Product Intelligence → Architect (blueprint) → Developer agents (generate the app's
code) → smoke_boot → Opus security review → QA (ephemeral boot + tests) → DevOps deploy.
Over many sessions we hardened it with **15 deterministic fixes** so it reliably reaches
QA. Three real paid end-to-end runs (1007/1038/1039) then proved a hard truth: **the 15
fixes all hold, but each fresh generation still trips over a DIFFERENT one-off LLM
codegen bug, and the QA retry loop makes it worse.** The next chapter is an
architectural pivot — a **Code Integrity Engine** that validates code DURING Developer
generation, not only at the end. Two slices are now DONE + live: **FIX #16 (Symbol
Resolution Gate, §1a)** and **FIX #17 (backend syntax/AST gate, §1b)**. A full-scope
measurement run (**1105** — Bella Vista with menu PDF + online ordering + Stripe + Auth0)
then went the FULL distance: build (FIX #17 caught + we hand-fixed a syntax bug) → smoke_boot
→ **real Opus PASSED** → QA → deploy → a real HTTPS stack. It required significant HAND-WORK
(§1c). **HONEST OUTCOME (corrected after the user opened the URL): each tier RESPONDS in
isolation, but the app is NOT usable end-to-end — root `/` is 404 (no generated homepage) and
the frontend can't reach the backend (a `NEXT_PUBLIC_API_BASE_URL` vs `NEXT_PUBLIC_API_URL`
config mismatch + build-time inlining + ambiguous proxy paths).** Two decisive lessons: (1)
QA's OWN retry loop regenerated files through a path that ran NEITHER Fix #16 NOR Fix #17 and
re-introduced both classes → **FIX #18 (§1d) now gates that path — DONE + tested**; (2) the
DEPLOY path has multiple unproven layers — Week-7 secrets, a Redis it never provisions, a
health-check that only probes the edge, and a broken frontend↔backend contract → **that DevOps
deploy-path work is the NEXT priority (§5)**. The 888 fixture is still the ONLY end-to-end-usable
demo.**

## 1. CURRENT STATE (all verified this session)
- **15 deterministic fixes + Code Integrity Engine gates FIX #16 (symbol resolution),
  #17 (backend syntax/AST), #18 (QA-regen gate), #19 (attribute resolution, slice 1) +
  DevOps deploy-path FIX #20 (health check, gap #3), #21 (FE↔BE wiring, gap #2), #22
  (generated homepage, gap #4) + FIX #23 (security-review verdict = confirmed-critical)
  COMPLETE, verified live in the running backend, all 14 offline suites pass, committed +
  pushed** (§1a–§1j have the detail). Deploy gaps #2/#3/#4 all closed; only gap #1
  (secrets/redis onboarding) remains, deferred (§5). **🏆 Run 1289 (§1j): first-ever full-scope
  fresh generation to pass Build→smoke_boot→**real Opus security review** unaided (Fix #23
  validated live); then hit real QA 500s → root cause diagnosed (get_db swallows HTTPException)
  → candidate FIX #24 (NOT built; §5.A). Candidate Fix #24 + Fix #19 slice 2 = the only open work.**
  The fixes (see the "FIXES" sections far below for full detail): #1–#11 (the deploy-
  readiness batch: menu-schema dedupe, email-validator, **auth-symbol contract**,
  smoke-boot gate, response_model rule + traceback capture, Fernet key, python-multipart,
  Anthropic SDK class, menu review endpoints, ALLOWED_ORIGINS, FND-1 shared Base),
  **#12** pin the QA/smoke_boot venv to the deploy's exact versions, **#13** Pydantic-v2
  prompt rule, **#14** D4 force-dynamic via the ROOT SERVER layout, **#15** deterministic
  frontend truncation/parse gate. Plus three build-gate detectors added alongside #14/#15:
  **stub-function gate**, **`Depends(get_db)` (not `async_session`)**, **schema-adherence
  (model columns must match the contract)** — all wired into
  `developers/orchestrator._collect_stubs` (flag → retry → fail) and QA static checks.
- **Config live:** `SECURITY_REVIEW_ENABLED=true` (real Opus ON), `CODEGEN_MODE=real`,
  `DEPLOY_TARGET=local`. All keys live (OpenAI/Anthropic/Gemini); **`MENU_EXTRACTION_API_KEY`
  = a SCOPED Anthropic key, distinct from the master** (user created it in the Anthropic
  console; wired via `.env` + `docker-compose.yml`). `.env` is gitignored — never commit it.
- **FIX #16 + FIX #17 = DONE + LIVE + PUSHED.** Two concrete pieces of the Code Integrity
  Engine. Backend rebuilt so both gates are live in `ai-org-backend-1` (verified by import +
  by real run 1105). **DECIDED NEXT STEP is in §5** (resume 1105, then Fix #18).
- Backend rebuilt this session so Fix #16 + Fix #17 are live in `ai-org-backend-1` (verified:
  the new gate symbols import in the running container AND Fix #17 fired on real run 1105).
  Frontend unchanged.
- **DB: project 1105 is DELIBERATELY LEFT IN THE DB** (status build_failed) — it is the run
  we will hand-fix + resume next session (§5). Do NOT delete it. Project 1071 (the earlier
  measurement run, Fix #17's fixture source) was CLEANED UP after its `order_be_3.py` was
  captured to `backend/tests/fixtures/order_be_3_param_order_1071.py`.

## 1a. FIX #16 — SYMBOL RESOLUTION GATE (DONE + verified 2026-08-15)
Deterministic build-gate check: for every generated backend `.py`, each
`from <in-project module> import <symbol>` MUST resolve to a real export of that module.
Directly kills the 1038 `require_admin` class ("correct module path, guessed name") that
fix #3's non-deterministic PROMPT rule could not stop.
- **Where:** augments `developers/orchestrator._collect_stubs` (the existing build gate), NOT
  per-file generation — the whole file set is present there, so a complete in-project symbol
  table is available. Reuses the established flag → bounded-retry → fail pattern. Insertion
  point confirmed to NOT collide with the deployment-layer `DeploymentSnapshot`/Auto-fix Safe
  Mode (a different lifecycle); keeps using the build gate's own in-memory/DB transaction.
- **How:** `agents.build_symbol_index(files)` builds the index once; `agents.
  import_symbol_mismatches(content, filepath, index)` returns STRUCTURED findings
  ({file, line, module, symbol, available}). Auth is validated against the authoritative
  `AUTH_EXPORTS` contract; every other in-project module against an AST scan of its OWN
  top-level defs/classes/assigns + re-exported names. `agents.repair_instructions(result)`
  renders a precise IMPORT_RESOLUTION_FAILURE ticket, and `build_ticket(..., repair=...)`
  feeds it into the bounded retry — a TARGETED repair, the direct antidote to the blind
  regenerate-and-hope that churned 1038/1039 into a non-booting state.
- **Zero-false-positive design (the hard requirement, met):** third-party/stdlib modules
  (OUT OF SCOPE — deferred, see §5), opaque modules (star imports), submodule imports
  (`from pkg import submodule`), re-exports, and relative imports are ALL treated as
  resolvable and never flagged. Proven: **0 findings across the platform's own 64 backend
  modules AND project 888's real working generated files** (auth/database/main/models/menu/
  menu_upload/security). Bonus true-positive on real generated code: it correctly catches
  888's 3 ORPHANED order/stripe files' dangling `Order`/`Product`/`StripeAccount` imports
  (dead code the 888 hand-fix stripped from models.py/main.py).
- **Tests (all green; 13/13 offline suites pass):** in `test_developers_offline.py` —
  `test_import_symbol_resolution_gate` (flags `require_admin`, names available symbols, leaves
  valid siblings alone, gate rejects only the bad ticket + attaches structured repair),
  `test_import_symbol_zero_false_positives` (the 64-module + 888 corpus proof above), and
  `scenario_symbol_repair_retry` (end-to-end through the REAL orchestrator: bad import → gate →
  structured repair → retry converges → `built`). Fixtures: the captured 1038 bug
  `tests/fixtures/menu_upload_require_admin_1038.py`, and 888's 10 real backend files exported
  to `tests/fixtures/gen888/` as the false-positive corpus.

## 1b. FIX #17 — BACKEND SYNTAX/AST GATE (DONE + verified live 2026-08-16)
Deterministic build-gate check: every generated backend `.py` MUST parse (`ast.parse`).
Kills the 1071/1105 class — a fresh generation of `routes/order_be_3.py` put a NON-default
param (`status_update: OrderStatusUpdateRequest`) AFTER a defaulted one
(`order_id: int = Path(...)`) → hard Python `SyntaxError` at import, app never boots.
Previously caught only at smoke_boot (after the whole build); now caught at the build gate.
- **Where:** same slot as fix #16 — `developers/orchestrator._collect_stubs`. Runs the syntax
  check FIRST (an unparseable file blocks every other AST detector, and the others already
  no-op on `SyntaxError`).
- **How:** `agents.python_syntax_error(content, filepath)` → `None` or STRUCTURED
  `{file, line, offset, message, text}` (`.py` only). `agents.repair_instructions` extended to
  render a `SYNTAX_ERROR` repair (file + line + message + offending line + param-ordering
  guidance), fed via the existing `build_ticket(repair=...)` bounded retry.
- **Zero false positives BY CONSTRUCTION:** valid Python parses, invalid does not. Proven:
  `None` across the platform's own 64 backend modules AND 888's real `gen888` files.
- **Tests (13/13 offline suites pass):** `test_python_syntax_gate` (flags 1071's exact bug +
  unclosed-paren/bad-indent, ignores valid/non-`.py`, the zero-FP corpus proof, gate
  integration + structured `syntax_error`, `SYNTAX_ERROR` repair text) and
  `scenario_syntax_repair_retry` (end-to-end through the REAL orchestrator: broken file → gate
  → structured repair → retry converges → `built`). Fixture: `tests/fixtures/
  order_be_3_param_order_1071.py` (the exact captured 1071 file).
- **⚠️ KNOWN LIMITATION (measured on run 1105, the entire reason for FIX #18):** the DETECTION
  is deterministic and perfect, but the bounded REPAIR does not always converge. On 1105 the
  developer agent regenerated the SAME param-ordering error even WITH the `SYNTAX_ERROR` repair
  in its prompt, so the build failed cleanly (non-convergent). Root cause: `build_ticket`'s own
  3-attempt loop only re-generates on **self-review** (a lenient LLM check that does NOT
  validate syntax), and the orchestrator does only ONE gate-retry pass — so BE-3 effectively
  got two fresh, syntax-UNVALIDATED generations. FIX #18 closes this (see §5).

## 1c. RUN 1105 — RESUMED HAND-FIX → **FIRST GENUINELY-LIVE FULL-SCOPE URL** (2026-08-16 late)
The Option-3 resume of run 1105 (Bella Vista: menu PDF + ordering + Stripe + Auth0/2FA, 21
files, Production plan). It went the whole distance and SERVED — but only with meaningful
hand-work. **The sequence, and every intervention, in order:**
1. **Hand-fixed `order_be_3.py`** (reordered params — the Fix #17 class). Verified `ast.parse`.
2. **smoke_boot ✅ clean** (ran `main._smoke_boot` directly on the DB files — the honest gate).
3. **Real Opus security review ✅ PASSED** (`claude-opus-4-8`, 21 files, 89/99 fixed, real cert).
4. **QA ❌ 14/16** — and here is THE finding: **QA's own retry loop (`files_rewritten_by_qa: 6`,
   `root_cause_agent: developer_rework`) regenerated 6 files and RE-INTRODUCED two gate-class
   bugs through a path that runs NEITHER Fix #16 NOR Fix #17:** `order_be_3.py` (syntax, Fix #17
   class — later self-corrected by another QA rewrite) and **`stripe.py` importing
   `StripeOAuthState` from models — a symbol that doesn't exist (Fix #16 class).** This is the
   CONTEXT §2 root cause reproduced precisely: the QA loop churns files into a non-booting state.
5. **Hand-fixed the QA churn:** added the `StripeOAuthState` SQLAlchemy model to `models.py`
   (QA invented the import but never added the model). Re-`_recertify`'d ONLY the 1 drifted file
   (`models.py`, id 2363) via `qa.orchestrator._recertify(1105, bp, {2363})` → Opus re-reviewed
   it, cert re-fingerprinted, **drift = 0**. (Deploy is fail-closed on cert drift — this is the
   honest way past it: re-review the hand-edit, don't bypass.)
6. **Deploy ✅ built + stood up a real HTTPS stack** (Caddy + Next.js frontend + Postgres +
   backend), reported `live`, `security_certified: true`. Live URL: **https://localhost:47899**.
7. **The deployed backend then crash-looped** on a CHAIN of the **Week-7 secrets gap** — the
   deploy path seeds NONE of these, and the generated code (correctly) fail-fasts on each:
   `AUTH0_DOMAIN/CLIENT_ID/AUDIENCE` (auth.py), `STRIPE_CLIENT_ID/SECRET_KEY/TOKEN_ENC_KEY`
   (stripe.py), `ENCRYPTION_KEY` (security.py, must be a valid base64-32/Fernet key),
   `ALLOWED_ORIGINS` (main.py, the CORS hardening Opus adds). I **hand-seeded all of them**
   (dummy presence-satisfying values; real Fernet keys for the two enc keys) by recreating the
   backend container with an `--env-file`. **The stack also had NO Redis**, but the generated
   `security.py` needs it (FastAPI-Limiter) — I **added a `redis:7` container** on the stack
   network (`REDIS_URL=redis://redis:6379`).
8. **Two NEW codegen bugs surfaced at runtime (the "app-logic quality tail"):**
   - **DDL bug:** `models.py` uses `server_default='CURRENT_TIMESTAMP'` as a STRING → Postgres
     casts the literal → `create_all` fails → **no tables** → every DB endpoint 500s. The
     `_devops_bootstrap.py` even has a buggy sync-on-async `create_all(bind=eng)` fallback. I
     **created the tables by hand** with the default corrected to `text('CURRENT_TIMESTAMP')`.
   - **Deploy health-check hole:** the deploy reported `live` (+ `tests_passed: 14`) by probing
     the Caddy/frontend EDGE while the backend crash-looped — it never hit a backend route.
9. **RESULT — deployed + each tier responds IN ISOLATION, but NOT a usable app end-to-end**
   (initial "genuinely live" claim was CORRECTED after the user opened the URL and hit a 404).
   Tiers in isolation: backend `GET /menu` → 200 `[]`, `/health` → 200, `/admin/menu/pending`
   → **401** (auth gate works), `/docs`+`/openapi.json` → 200 (full API). Frontend pages render
   with real content: `/order` ("Place an Order"), `/admin/menu` ("Manage Menu" + add-item form),
   `/admin/menu/review`, `/settings` → 200. **BUT the integrated browser experience is BROKEN:**
   - **Root `/` = 404** — the generated frontend has NO homepage (`app/page.tsx`). This is what the
     user saw.
   - **Every page is stuck "Loading menu…"** — the frontend CANNOT reach the backend. TWO bugs:
     (a) the frontend code reads `process.env.NEXT_PUBLIC_API_BASE_URL` but the deploy set a
     DIFFERENT var `NEXT_PUBLIC_API_URL` (name mismatch) → `API_BASE=""` → it fetches same-origin
     `/menu`, which Caddy routes to the FRONTEND (404), not the backend; (b) even the var the deploy
     set points at a REMOTE prod domain (`bella-vista-….apps.example.com/api`), not this local
     stack, AND Next inlines `NEXT_PUBLIC_*` at BUILD time so a runtime fix needs a frontend rebuild.
   - **Reverse-proxy path model is ambiguous:** Caddy sends `/api/* /docs /openapi.json /health` →
     backend:8000, everything else → frontend:3000 — but the backend's routes are `/menu`,
     `/admin/menu`, etc. (NOT under `/api`), and `/admin/menu` is ALSO a frontend page path. So there
     is no clean path split; the front/back contract is broken in the deploy.
   **NET: the deploy stands up a real stack but produces a NON-FUNCTIONING product** — a NEW class of
   gap (deploy-integration: frontend API base config + proxy routing), on top of the Week-7 secrets
   gap and the health-check hole. None of it is caught by the pipeline; none is addressed by the
   codegen gates (#16/#17). The 888 fixture remains the only END-TO-END-usable demo.

**HONEST TAKEAWAYS for the platform (what 1105 proved):**
- ✅ The Code Integrity gates (Fix #16/#17) + hand-fixes got a fresh full-scope app all the way to
  a live, security-certified, HTTPS deploy — the furthest ever.
- ❌ **QA's retry loop is an UNGATED regeneration path** — it re-introduced both gate classes. THE
  next fix (§5). ❌ **Week-7 secrets onboarding** is still fully open and now shown to block a real
  deploy across auth+stripe+encryption+CORS+redis. ❌ **New deterministic-catchable bugs** the
  gates don't yet cover: the `server_default='CURRENT_TIMESTAMP'` DDL bug (a create_all failure —
  catchable by actually creating tables in smoke_boot/QA), the async `create_all(bind=eng)`
  bootstrap fallback, and the deploy health-check probing only the edge.
- The 1105 stack was left UP for the user to view, then torn down (see §6). It is NOT a frozen
  fixture like 888 — it required live hand-seeding of secrets + tables to serve.

## 1d. FIX #18 — CODE-INTEGRITY GATE ON QA's OWN REGENERATION LOOP (DONE + tested 2026-08-16 late)
Closes the decisive 1105 hole (§1c step 4): QA's repair loop regenerated a file via the Developer
agent and ACCEPTED it with NO deterministic validation, re-introducing the Fix #17 (order_be_3
syntax) and Fix #16 (stripe.py→`StripeOAuthState`) classes and breaking the app at boot. Supersedes
the old narrow "Fix #18" (which only re-validated inside `build_ticket`); the real hole was QA's
separate regeneration path.
- **Where:** `qa/orchestrator.py`. The accept point was `run()` line ~411 (`new_content = await
  _regenerate(...)` → `gf.content = new_content`). Now routed through a gated wrapper.
- **How:** `_gate_regenerated(candidate, filepath, files, file_id)` runs the SAME detectors as the
  build gate — `dev_agents.python_syntax_error` (#17) then `dev_agents.import_symbol_mismatches`
  (#16, index built from the CURRENT file set with the candidate swapped in). `_regenerate_validated`
  wraps `_regenerate`: on a gate failure it feeds `dev_agents.repair_instructions(...)` back into a
  BOUNDED re-generation (`_QA_REGEN_MAX_REVALIDATE = 2` extra attempts), re-validating each; a
  rewrite that still fails is **REJECTED (returns None) → the previous file content is kept**, never
  churned into a non-booting state. `_regenerate` gained a `repair=""` param threaded into
  `build_ticket(..., repair)`.
- **Zero false positives:** proven `{}` across the platform's own 64 backend modules AND 888's real
  working generated files (each file treated as a regeneration of itself against the real set).
  Backend `.py` only; frontend/non-`.py` is a no-op.
- **Tests (14/14 offline suites pass — new suite `test_qa_regen_gate_offline.py`):** flags the REAL
  1105 fixtures (`order_be_3_param_order_1071.py` syntax, `stripe_stripeoauthstate_1105.py` symbol),
  leaves valid siblings alone, the zero-FP corpus proof, and three wrapper scenarios — converges
  (broken→repaired via the fed-back SYNTAX_ERROR), REJECTS (persistently broken → None, bounded),
  accepts a clean rewrite immediately. NOTE: `test_qa_retry_loop`/`test_qa_teardown` mocks were
  updated to the current `build_ticket(..., repair="")` signature (same fix as the developer mocks).
- Backend image REBUILT so the gate is live for the next run.

## 1e. FIX #19 — ATTRIBUTE RESOLUTION GATE, slice 1 (DONE + tested 2026-08-17)
Research-backed: after wrong imports (#16) and syntax (#17), "No attribute" is the next most
common structural LLM codegen error (86K-error taxonomy across 7 models). Code accesses a
field/method that doesn't exist on a class it uses — e.g. `Order.total_amonut` (typo),
`MenuItem.total_amount` (the CONTEXT §"KNOWN-OPEN" example). DIFFERENT mechanism than #16 (#16
checks module-level IMPORTS; #19 checks ATTRIBUTE ACCESS resolves to a real class attribute).
- **Slice 1 scope = CLASS-NAME access only (`ClassName.attr`)** — the type IS the named class,
  so NO instance type-inference (that is where false positives live; deferred to slice 2).
  Instance access (`x.attr`), chained/module-qualified access, and stored targets are OUT →
  skipped. (User approved class-name-only; wants to DISCUSS slice 2 = annotated/constructed
  instance access, now that the FP proof stayed clean.)
- **Index extension (NOT a parallel system):** `agents.build_symbol_index` now also returns
  `classes` (dotted module → {ClassName → raw info: body attrs incl `self.X=`, bases, tablename,
  dynamic, open_base}) and `class_imports` (name → origin), built in the same file-set pass.
- **Resolution + zero-FP rules:** `_resolve_class_attrs` returns a class's FULL attribute surface
  or None (=OPEN → never flag). ORM models (detected by `__tablename__`) get a curated
  SQLAlchemy base surface (`metadata/registry/query/c/__table__/…`); Pydantic (`BaseModel` base)
  gets the Pydantic surface (`model_dump/model_validate/model_fields/…`); in-project base classes
  union recursively; ANY unresolvable/third-party base, a metaclass=, a `__getattr__`/`setattr`
  (dynamic), or a shadowed class name → OPEN/skip. Dunders skipped on the access side. Captures
  BOTH `Column(...)` (Assign) and `Mapped[..]=mapped_column(...)` (AnnAssign), relationships,
  `@property`/methods.
- **Detector:** `agents.attribute_access_mismatches(content, filepath, index)` → structured
  findings `{file, line, class, module, attribute, available}`. `repair_instructions` renders a
  targeted `ATTRIBUTE_RESOLUTION_FAILURE` (class + bad attr + the class's real fields).
- **Wiring:** `developers/orchestrator._collect_stubs` (build gate, alongside #16/#17) AND
  `qa/orchestrator._gate_regenerated` (the Fix #18 QA-regen gate) — same flag → structured-repair
  → bounded-retry / reject flow. No collision.
- **Zero false positives — PROVEN:** 0 findings across the platform's own 64 backend modules AND
  every real generated fixture (888's 10 files + the captured 1105/1071 files), while flagging the
  synthetic `MenuItem.total_amount` / `Order.total_amonut` with correct `available`.
- **Tests (14/14 offline suites pass):** `test_developers_offline.test_attribute_resolution_gate`
  (typos flagged; real columns / relationship / method / dunder / SQLA+Pydantic base attrs NOT
  flagged; OPEN classes — logging.Filter/ABC base, `__getattr__`, DeclarativeBase — NOT flagged;
  instance/constructed/module-qualified/shadowed OUT of scope; gate integration + repair text) +
  `test_attribute_zero_false_positives` (the 64-module + 888/1105 corpus proof) +
  `test_qa_regen_gate_offline.test_gate_attribute`. Backend image REBUILT; gate live.

## 1f. FIX #20 — LAYERED DEPLOY HEALTH CHECK (deploy gap #3) (DONE + tested 2026-08-17)
Closes the run-1105 deploy gap #3 (§1c step 8): the health probe reported `live` by hitting
the Caddy/frontend EDGE (`GET /` → a 404 homepage, `<500`) while the BACKEND was crash-looping
(502 on backend routes). A deploy that silently reports success while the backend is dead is the
same "confident but wrong" class every fix here targets.
- **Where:** `devops/health.py` `probe()` + the call site `devops/orchestrator.py` (STEP 7).
- **How:** `probe()` is now LAYERED (edge → backend → frontend) and reports `ProbeResult.
  failed_layer`. Healthy REQUIRES the BACKEND to answer: a `<500` on any backend-liveness path
  (`_BACKEND_LIVENESS_PATHS = /openapi.json, /health, /healthz` — all Caddy-routed to `backend:8000`;
  `/openapi.json` is always present in FastAPI). Layers: **edge** = no HTTP response at all
  (Caddy/URL unreachable); **backend** = edge answers but backend routes are 5xx (the 1105 crash-loop);
  **frontend** = (only when `has_frontend`) `/` is not `<500` (a 404 homepage still counts as up, so
  gap #4's missing homepage never false-fails). `probe()` gained `has_frontend` + `backend_paths`
  kwargs; the orchestrator derives `has_frontend` from `req.files` via `manifest._is_frontend` and
  prefixes the failure with the layer (`"The backend layer did not become healthy. …"`), also
  returned as `failed_layer`. `classify()` UNCHANGED (still called without a probe result by
  `background/autofix.py`), so once the probe correctly fails, the existing MISSING_CONFIG/APP_ERROR
  → `status="failed"` + teardown flow runs as designed.
- **Tests (14/14 offline suites pass):** `test_devops_offline.test_health_probe` (httpx.MockTransport,
  no network) proves FAILURE, not just success — ⭐ the run-1105 regression (backend 502 + `/` 404 →
  UNHEALTHY, `failed_layer=='backend'`), plus healthy-when-backend-up, 404-homepage-doesn't-false-fail,
  dead-frontend→frontend layer, unreachable-edge→edge layer, and backend-only stacks. Image REBUILT.
- **⚠️ DELIBERATE CONSEQUENCE (intended):** after #20, a 1105-style fresh full-scope deploy will now
  HONESTLY report **failed** at the health gate (backend can't boot without seeded secrets) instead
  of a false `live`. That is the point — measure truthfully. It does NOT make deploys succeed; gaps
  #1/#2/#4 still stand (§5).

## 1g. FIX #21 — FRONTEND↔BACKEND DEPLOY WIRING (deploy gap #2) (DONE + tested 2026-08-17)
Closes the run-1105 deploy gap #2 (§1c step 9): the deployed app rendered but every page was stuck
"Loading…" because the frontend could not reach the backend. Four defects, all fixed against the
REAL generated artifacts:
- **(a) var-name mismatch:** the deploy set `NEXT_PUBLIC_API_URL` but the generated frontend read
  `NEXT_PUBLIC_API_BASE_URL` (LLM-emergent, nothing pinned it). → Deploy now sets
  `NEXT_PUBLIC_API_BASE_URL`, AND it is CONTRACT-PINNED on the codegen side (Part 3) so a fresh
  generation reads exactly that var — determinism, not luck (same pattern as AUTH_EXPORTS).
- **(b) wrong value:** it was `https://{subdomain}/api` (a remote `.apps.example.com` host that
  doesn't resolve to the local stack). → Now a RELATIVE `/api` (same-origin), works on both the
  local `localhost:<port>` and the AWS subdomain origins.
- **(c) build-time inlining:** Next.js inlines `NEXT_PUBLIC_*` at BUILD time, but it was only a
  runtime `environment:`. → Now a Docker BUILD ARG (`_frontend_dockerfile` `ARG ... ENV ...` before
  `npm run build`; local compose `build.args`; AWS buildx `--build-arg`).
- **(d) Caddy /api not stripped:** `@api path /api/*` → backend WITHOUT stripping, so `/api/menu`
  hit backend `/api/menu` → 404. → Now `handle_path /api/* { reverse_proxy backend:8000 }` STRIPS
  the prefix so `/api/menu` → backend `/menu`; `/openapi.json /docs /health /healthz` still route to
  the backend WITHOUT stripping (so the fix #20 health probe is unaffected); everything else →
  frontend. This also removes the `/admin/menu` collision: that path is the FRONTEND page; the
  backend endpoint is reached at `/api/admin/menu`.
- **Files:** `devops/manifest.py` (constants `FRONTEND_API_BASE_ENV`/`_VALUE`, `_caddyfile`/
  `_caddy_routes`, `_frontend_dockerfile`, `_compose` frontend block), `devops/drivers/aws.py`
  (frontend `--build-arg`), `developers/agents._system('frontend')` (the contract-pin — Part 3).
- **Tests (14/14 offline suites pass):** `test_devops_offline.test_frontend_wiring` asserts each of
  the four 1105 defects is resolved against the REAL generated compose/Caddyfile/Dockerfile, incl.
  the AWS branch, PLUS the codegen contract-pin matches the manifest constant (drift guard). Image
  REBUILT.
- **⚠️ KNOWN LIMITATION (logged, not urgent):** `/api` relative works for CLIENT-side fetches (the
  browser hits Caddy). A generated page doing SERVER-side (SSR/RSC) fetching inside the frontend
  container would need `http://backend:8000` instead — acceptable because the generated apps are
  client-heavy (forced-dynamic `"use client"`; 1105 fetched client-side). Revisit only if a run does
  server-side data fetching.

## 1h. FIX #22 — GENERATED HOMEPAGE (deploy gap #4) (DONE + tested 2026-08-17)
Closes the run-1105 deploy gap #4 (§1c step 9): the deployed frontend had NO root
`app/page.tsx`, so opening the live URL hit a 404 (what the user saw). The Architect now
commissions a real root home page deterministically.
- **Where:** `architect/builder.py`. New `_frontend_homepage_ticket(routes, business_name)`
  (FND-6, mirrors FND-4/FND-5), `_frontend_page_routes(tickets)` (derives `/route` from each
  `frontend/app/<route>/page.tsx`, EXCLUDING the root), `_has_root_homepage(tickets)`.
- **What it commissions:** `frontend/app/page.tsx` — a MINIMAL but real SERVER component
  (no `"use client"`, no data fetch, no client hooks → `next build` can't fail on it): the
  business name + a one-line welcome + a Next.js `<Link>` nav to the app's ACTUAL routes.
- **Placement (important):** added in `build_blueprint` BEFORE the entrypoint ticket (so APP-1
  still depends on every ticket and stays last — the "entrypoint is last / depends on all"
  invariant holds), with `dependencies: []` (first wave; the `<Link href>` targets are static
  strings, so linked pages needn't exist when it builds). The real routes are BACKFILLED into
  its description AFTER `_assign_filepaths` (when every frontend page path is final). Skipped if
  a page already owns the root (idempotent) or there is no web frontend.
- **Tests (14/14 offline suites pass):** `test_architect_offline.test_homepage_helpers` (route
  derivation excludes root + ignores layout/css; `_has_root_homepage`; the FND-6 ticket names
  the business, lists the exact routes, is server-only; no-routes → clean welcome, no invented
  links) + `test_generated_homepage` (against a REAL Bella Vista blueprint: exactly one root
  page, FND-6/frontend/no-deps, links every real route and only real routes, root excluded from
  the nav, survives the duplicate-path guard). Image REBUILT.
- **⭐ DEPLOY-PATH GAPS #2/#3/#4 ALL CLOSED.** Only gap #1 (Week-7/8 secrets/redis onboarding)
  remains — DELIBERATELY DEFERRED to its own design session (§5).

## 1i. MEASUREMENT RUN 1289 + FIX #23 — security-review verdict = CONFIRMED critical (2026-08-17)
Full-scope run with ALL fixes live (Bella Vista: menu PDF + ordering + Stripe + auth, **Quick**).
**The codegen + boot pipeline is now SOLID — proven live:**
- BA → PI → Architect (22 tickets incl. FND-6 homepage) → **Build reached `done`**, meaning it also
  **passed smoke_boot**. **Fix #16 CAUGHT A REAL BUG on the fresh generation** (`notifications.py`
  imported `send_email`/`send_sms` from `integrations.integrate`, which don't exist there) → structured
  repair → **recovered on retry** → the full app **assembled + booted with ZERO hand-fixing.** First
  fresh full-scope run ever to reach a clean bootable build unaided. No require_admin/DDL/syntax/QA-churn.
- **Then stopped at the Opus security cert (`passed: False`)** — NOT the secrets gap, NOT a real vuln.
**DIAGNOSIS (proven, not guessed):** re-reviewing the 4 flagged files' FINAL content across 4 fresh
Opus passes returned **0 criticals every time** (`[0,0,0,0]`); only medium/minor issues remained
(file buffered before size-check DoS in menu_upload; unsanitized AI-parsed fields; a stubbed
`validate_api_key`; client-side token exposure; an open-redirect — all real future hardening, none
cert-blocking). The `passed:False` was a **FALSE NEGATIVE in the review's convergence**: the moment
the first stochastic pass tagged a `critical`, `review_file` set `security_passed=False` and its
`_MAX_SECURITY_RETRIES=2` rechecks (each a fresh stochastic review) never happened to come back clean
— so a file whose FINAL content is reproducibly clean was labeled failed; `cert.passed = all(files)`
→ one stuck file fails the whole cert → deploy fail-closed. **Recurring/systemic** (review logic, not
codegen): with a stochastic reviewer over ~22 files, ≥1 file getting stuck recurs run-to-run.
**FIX #23 (`reviewer.review_file` + `_confirmed_critical`):** the fix loop still FIXES criticals
(unchanged), but pass/fail is now decided on the FINAL content by a **confirmation rule** — a file
fails ONLY if a critical is **confirmed on TWO independent passes** (short-circuits when pass 1 is
clean). A genuine (reproducible) vuln shows on every pass → still fails; a one-off flake on clean
content no longer false-fails. Does NOT weaken the gate against stable criticals; narrow, deliberate
loosening of the *convergence verdict* only (user-approved trade-off). Extra Opus cost only for files
that actually hit a critical (1–2 verdict reviews), not every file.
- **Tests (14/14 offline suites pass):** `test_architect_offline.test_reviewer_security_verdict`
  (mocks `_review`/`_fix`): a STABLE critical (both confirm passes) still FAILS; an initial-flag +
  clean-final (the 1289 case) PASSES; a single-pass verdict flake PASSES; a clean file spends no extra
  verdict reviews. Image REBUILT; Fix #23 live.
## 1j. 🏆 RUN 1289 — FULL SEQUENCE + FIX #23 VALIDATED LIVE + the get_db 500 (candidate FIX #24) (2026-08-17 late)
This is the headline result of the whole Code Integrity Engine effort. Full-scope Bella Vista
(menu PDF + ordering + Stripe + auth, **Quick launch**), ALL fixes #16–#23 live. Exact sequence:
1. **BA → PI → Architect:** 22 tickets incl. FND-6 homepage (Fix #22). PI kept all 3 features.
2. **Build → `done`** (means smoke_boot ALSO passed). **FIX #16 CAUGHT A REAL BUG on the fresh
   generation** — `routes/notifications.py` (BE-3) imported `send_email`/`send_sms` from
   `integrations.integrate`, which don't exist there → structured repair → **recovered on retry.**
   The full app **assembled + booted with ZERO hand-fixing** — a first for a fresh full-scope run.
3. **Opus security review — FIRST PASS: `passed:False`** (128 found / 123 fixed). Diagnosed as a
   FALSE NEGATIVE in the review-convergence loop (not a real vuln, not the secrets gap) → **FIX #23
   (§1i).**
4. **Rebuilt + re-ran `POST /pipeline/secure` → ✅ Opus PASSED** (`passed:True`, real
   `claude-opus-4-8`, 90 found / 83 fixed, 22 files). **🏆 FIRST-EVER real Opus security PASS on a
   full-scope fresh generation — Fix #23 validated end-to-end.**
5. **QA → 84 passed / 20 failed** (`status: error`). The 20 failures are ALL on the auth-gated
   `order` + `notification` endpoints (public `GET /menu` is fine). **FIX #18 FIRED LIVE + WORKED:**
   QA's retry loop regenerated `notifications.py` into a wrong-symbol import → the QA-regen gate
   REJECTED it ("REJECTING the rewrite") — the exact 1038/1039 QA-churn, prevented. `files_rewritten
   _by_qa: 6`, `still_certified: False` (QA drift + security re-check failed).
6. **500 ROOT CAUSE — DIAGNOSED (complete; offline assemble+boot, real traceback captured, ~$0):**
   `get_db` in **`database.py` (FND-2)** wraps `yield session` in a broad `except Exception` that
   re-raises **as `HTTPException(500, "Internal server error")`**. So when a protected endpoint's
   OAuth2 dependency raises `HTTPException(401)`, that 401 propagates back through get_db's `yield`,
   hits the broad except, and becomes a **500**. This masks EVERY intended 401/404/422/400 on every
   endpoint that depends on get_db → all 20 failures (no-login→500, missing-field→500, injection→500,
   happy-path→500). Public `/menu` (GET, no error path) is unaffected. **Captured traceback proof:**
   `oauth2.py:588 raise HTTPException(401: Not authenticated)` → response `500 {"detail":"Internal
   server error"}`. (Note: `security.py`'s own HTTPException handler is CORRECT but is on a throwaway
   `app`; `main.py` is the real entrypoint. `create_order` DOES pass created_at/updated_at — the
   earlier model-timestamp hypothesis was WRONG. The confirmed cause is the get_db swallow.)
7. **ASSESSMENT (my read, user to decide):** RECURRING, deterministically-detectable + preventable —
   NOT a per-generation logic bug. It is the "confident but wrong" error-handling anti-pattern
   ("a dependency generator wraps `yield` in a broad `except` that turns framework exceptions into
   500"). Systemic (get_db is foundational → breaks HTTP semantics on every DB endpoint at once).
   QA DID catch it (QA's job), but it is a strong build-gate candidate too (move the cheap
   deterministic failure earlier — the whole Engine thesis; would have saved this run's QA+Opus cycle).

**➡️ CANDIDATE FIX #24 (PROPOSED, NOT BUILT — plan-first, same rigor as #16–#23):** an AST build-gate
detector (sibling of `agents.bad_session_dependency` / `model_schema_mismatches`) that flags a
`get_db`-style dependency generator whose `yield` is inside a `try` whose `except` catches broad
`Exception`/bare-`except` and raises `HTTPException(500)`/returns 500 WITHOUT re-raising an already-
`HTTPException`; wired into `_collect_stubs` (+ the QA-regen gate); PLUS a FND-2/backend prompt rule
("`get_db` must let FastAPI HTTPException 401/404/422 propagate unchanged; never turn errors into 500;
re-raise HTTPException untouched"). Zero-FP proof vs the platform's own 64 modules + 888 real files;
regression test using the CAPTURED 1289 `database.py`. **User's open question to answer next session:
build Fix #24, or accept this as QA's job and move on.**

**⏭️ NOT YET REACHED: deploy.** Run 1289 stopped at QA (app-logic 500), NOT the secrets gap. If Fix
#24 lands (or the get_db is hand-fixed), a re-run of QA→deploy would then hit the Week-7/8 secrets
gap honestly (Fix #20's layered health check reports it as `failed` "backend layer", no false live).

**Project 1289 is LEFT IN THE DB** (status `security_blocked` from the 1st review; the 2nd review +
QA ran after). Its `database.py` is the Fix #24 regression fixture source — captured (see §1k).

## 1m. FIX #26 — PLATFORM PROVISIONING (deploy gap #1, the 3 platform-solvable fixes) (DONE + tested + live 2026-08-20)
The platform-solvable HALF of the secrets gap — the parts NO human owns, which the platform supplies
itself. Built plan-first (user approved: new module + exact-origin ALLOWED_ORIGINS). Companion to the
owner half (`PLAN_owner_onboarding.md`, still not built). New module **`devops/provisioning.py`**:
- **`required_env(files)`** — deterministic scan of the generated BACKEND `.py` for `os.getenv("X")` /
  `os.environ[...]` → the set of env vars the app actually reads. The gate for all three fixes (nothing
  fires for a var an app doesn't use).
- **Fix A `ensure_crypto_keys(project_id, needed, existing)`** — mint + **PERSIST** the platform-mintable
  crypto keys the app needs: `FERNET_KEY` / `TOKEN_ENCRYPTION_KEY` / `STRIPE_TOKEN_ENC_KEY` =
  `Fernet.generate_key()` (the code does `Fernet(key)`), `SESSION_SECRET_KEY` = `secrets.token_urlsafe`.
  Persisted via `secrets_store.set_secret` so a **redeploy reuses the SAME key** (a fresh key would make
  already-encrypted rows unreadable). Wired into deploy `orchestrator.py` STEP 5, merged into `env` +
  guarded (redacted) BEFORE the non-secret config. **NEVER mints an owner secret** (STRIPE_SECRET_KEY /
  AUTH0_* still fail-fast honestly — Fix #20).
- **Fix B `needs_redis(files)`** — `manifest._compose` gained a `needs_redis` param: adds an isolated
  `redis:7-alpine` service (own `appnet`, **NO published host port**) + `REDIS_URL: redis://redis:6379`
  internal wiring + a health-gated `depends_on`, ONLY when the app reads `REDIS_URL`. `build()` computes
  it from `files`, so BOTH local + AWS get it uniformly.
- **Fix C `config_defaults(needed, existing)`** — non-secret defaults for referenced vars
  (`ENVIRONMENT=production`, `SQL_ECHO=false`, `RATE_LIMIT_TIMES/SECONDS`), added to `env` AFTER guard so
  values like "production" aren't redacted from logs; an owner-set value always wins. **`ALLOWED_ORIGINS`**
  is set at DRIVER level (local.py → `https://localhost:{https_port}`; aws.py → `https://{subdomain}`)
  because the host port is chosen dynamically in the driver, not in STEP 5.
- **Tests (all 14 offline suites pass):** `test_devops_offline.test_provisioning` — required_env
  extraction (ignores frontend/plain), redis gate both ways, config defaults (ALLOWED_ORIGINS excluded,
  never-referenced excluded, owner-wins), crypto keys (needed-only, valid Fernet, persisted via set_secret,
  STABLE across a 2nd redeploy, never an owner secret), compose redis present-only-when-needed with no host
  port. Backend REBUILT; `provisioning` imports live. Committed `e847b40`, pushed.
- **⚠️ EXPECTED:** after Fix #26, run 1289 STILL walls on the problem #1 owner vars (`AUTH0_DOMAIN`,
  `API_AUDIENCE`, `STRIPE_CLIENT_ID`, `STRIPE_SECRET_KEY`, `STRIPE_REDIRECT_URI`, SMTP/Twilio). That is the
  NEXT piece — the owner onboarding (`PLAN_owner_onboarding.md`): Stripe click-to-connect in a BA stage,
  Auth0 platform auto-provision, platform email. Fix #26 does NOT make 1289 fully boot on its own.

## 1n. OWNER ONBOARDING — SLICE 1: platform-held provider credentials injected at deploy (DONE 2026-08-20)
First slice of `PLAN_owner_onboarding.md` (problem #1) — the "platform-held" half. Committed `fd5dc66`.
- **`config.py`:** platform-held settings the operator sets ONCE in `.env` (like the scoped menu key):
  `stripe_client_id/secret_key/redirect_uri`, `smtp_host/port/user/password`, `sender_email`, `twilio_*`.
  Absent → that provider's feature is unavailable + the app fail-fasts honestly (Fix #20); nothing faked.
- **`provisioning.platform_provided(needed, existing)`** → `(secret_values, nonsecret_values)` split so
  STEP 5 guards only real secrets (Stripe secret, SMTP password, Twilio token) and NEVER redacts an
  identifier like `SMTP_PORT`. Injects ONLY vars the app reads; an owner-supplied value always wins; an
  unset platform var is omitted (honest fail-fast, logged per-provider).
- **STEP 5 wiring:** platform secrets before `guard()`, non-secret identifiers after — alongside Fix #26.
- **Tests:** `test_devops_offline.test_provisioning` extended (secret/non-secret split, unconfigured-omitted,
  owner-wins, reads-only). All 14 offline suites pass. Backend rebuilt; `platform_provided` live.
- **NOT YET (next slices):** (2) **Auth0 per-project auto-provision** via the Management API — deliberately
  NOT statically injected; (3) the **BA `connect_accounts` stage + Stripe Connect OAuth endpoints** (the
  owner-facing click-to-connect + `/connect/stripe/callback` → `secrets_store`); (4) **SMS** decide/defer.
  All need the one-time HUMAN platform setup (`PLAN_owner_onboarding.md` §7) to run for real; the CODE +
  offline (mocked) tests are buildable without it.

## 1o. OWNER ONBOARDING — SLICE 2: Stripe click-to-connect (BA stage + Connect OAuth) (DONE 2026-08-20)
The owner-facing Stripe piece of `PLAN_owner_onboarding.md`. Committed `9ff8df6`. User chose (this session):
next slice = BA Stripe click-to-connect; Auth0 = per-project (later).
- **`app/onboarding/stripe_connect.py`** (new package `app/onboarding`): platform side of Stripe Connect
  OAuth. `start(project_id)` → authorize URL with a signed, short-TTL, project-bound **state** (Fernet over
  `secrets_enc_key`; CSRF/replay-safe, 600s TTL). `handle_callback(code, state)` → verify state → exchange
  code at Stripe's token endpoint (httpx) → **persist** the owner's connected account id in `secrets_store`
  as `STRIPE_CONNECTED_ACCOUNT_ID`; raises `ConnectError` WITHOUT leaking Stripe's error body. `is_configured()`
  (platform Connect app set?) + `is_connected(project_id)` gate honestly (unconfigured → 503, never faked).
- **`main.py` endpoints:** `GET /connect/stripe/start` (307 → Stripe), `GET /connect/stripe/callback`
  (verify+exchange+store → minimal self-contained result page). Probed live: 503 unconfigured / 404 missing
  project / 400 cancelled.
- **BA `connect_accounts` stage** (`ba/state.py` ORDER just before CONFIRM; `ba/controller.py`): shown ONLY
  when the idea implies taking money (`_needs_payments` deterministic keyword scan; a stored `needs_payments`
  flag overrides). Renders a "Connect your Stripe" button (`ui.kind == "connect_accounts"`) with live
  connected status; **skippable** (`ingest` records `payments_connect_skipped`; deploy then walls on payments
  honestly via Fix #20).
- **Tests:** new **`test_onboarding_offline.py`** (28 checks, the 15th offline suite) — state
  signing/tamper/expiry, authorize URL (configured-only, no secret leak), callback (exchange+persist, bad
  state refused, Stripe-rejection body not leaked), BA stage (payment-intent, skip, ORDER, composed UI).
  All 15 offline suites pass; `app.main` imports.
- **✅ VALIDATED LIVE END-TO-END (2026-08-20):** operator created a Stripe **test-mode** Connect app and set
  `STRIPE_CLIENT_ID`/`STRIPE_SECRET_KEY` (`sk_test_`)/`STRIPE_REDIRECT_URI=http://localhost:8000/connect/stripe/callback`
  in `.env`. Fixes this session: (a) `docker-compose.yml` now forwards the owner-onboarding platform vars
  (STRIPE_*/SMTP_*/SENDER_EMAIL/TWILIO_*/AUTH0_MGMT_*) into the backend — they weren't listed before, so the
  container never saw them; (b) `_exchange_code` uses HTTP basic-auth (secret as username) per current Stripe
  docs. Then the OWNER clicked through the real Stripe test OAuth → callback → **`STRIPE_CONNECTED_ACCOUNT_ID`
  (`acct_…`) persisted encrypted in `secrets_store` for project 1289; `is_connected(1289)` True.** First real
  owner-account connection through the platform. Committed `06771fd`. (Stripe test mode = full Connect flow, no
  real ID/EIN/business verification — the §7 Stripe setup is doable in a Sandbox in minutes.)
- **⚠️ FOLLOW-UP (flagged, NOT done):** the connected account id is captured + persisted, but the generated
  `stripe.py` currently captures its OWN connection at RUNTIME and does NOT read `STRIPE_CONNECTED_ACCOUNT_ID`.
  To make the deployed app USE the pre-connected account (plan §3 Design 2), add a backend CODEGEN contract
  (generated stripe.py reads `STRIPE_CONNECTED_ACCOUNT_ID` from env as a pre-seeded connection). Separate slice.
- **STILL NEXT:** (2) Auth0 per-project auto-provision (Management API); (4) SMS decide/defer; the codegen
  consumption contract above. All need the one-time HUMAN platform setup (`PLAN_owner_onboarding.md` §7) for a
  real end-to-end run.

## 1p. OWNER ONBOARDING — SLICE 3: Auth0 per-project auto-provision (DONE 2026-08-20)
Owner does NOTHING — the platform auto-creates a per-project Auth0 login. Committed `a428425`. User chose
Auth0 next; per-project (not shared tenant).
- **`config.py`:** platform Auth0 Management settings (`auth0_tenant_domain`, `auth0_mgmt_client_id`,
  `auth0_mgmt_client_secret`). Absent → provisioning skipped, app fail-fasts on `AUTH0_*` honestly.
- **`app/onboarding/auth0_provision.py`** `ensure_provisioned(project_id, subdomain, needed)`: client-
  credentials mgmt token → create resource-server (API, identifier = per-project audience `https://{subdomain}/api`)
  + login client → returns `(secret, nonsecret)` env values (`AUTH0_DOMAIN`/`API_AUDIENCE`/`AUTH0_CLIENT_ID`
  non-secret, `AUTH0_CLIENT_SECRET` secret). **IDEMPOTENT** — persists to `secrets_store`, reuses on redeploy
  (no duplicate Auth0 apps, no calls). Skips when the app reads no Auth0 config or the platform is
  unconfigured; a Management-API failure returns `({},{})` (never raises into the deploy — health gate reports it).
- **`orchestrator.py` STEP 5:** provisions Auth0 alongside platform secrets — client secret before `guard()`,
  identifiers after.
- **Tests:** `test_onboarding_offline.test_auth0_provision` (mocked Management API) — unconfigured-skip,
  reads-no-auth0-skip, happy-path create+split+persist, idempotent reuse (no calls), failure-safe. All 15
  offline suites pass; `app.main` imports.
- **NOTE:** provisions + injects `AUTH0_CLIENT_ID/SECRET`, but the FRONTEND login wiring
  (`NEXT_PUBLIC_AUTH0_*`) is a separate frontend/codegen concern; this slice unblocks the BACKEND boot
  (`AUTH0_DOMAIN` + `API_AUDIENCE` JWT validation).
- **REMAINING owner-onboarding work:** (a) ~~codegen consumption contracts~~ DONE (§1q); (b) **SMS**
  decide/defer (Twilio number provisioning); (c) the one-time HUMAN platform setup (`PLAN_owner_onboarding.md`
  §7: Stripe Connect app DONE in test mode; Auth0 tenant + Management app + email sender still to set) —
  needed for a real end-to-end 1289 deploy. NOTE: 1289's EXISTING generated files predate the codegen
  contracts, so a full boot needs a FRESH generation (or hand-wiring) + the remaining §7 creds.

## 1q. OWNER ONBOARDING — SLICE 4: codegen consumption contracts (Stripe account + Auth0 frontend) (DONE 2026-08-20)
Makes the deployed app actually USE what onboarding provisions. Committed `d8a7974`. Both are codegen
CONTRACTS (prompt rules) + the deploy wiring to feed them, mirroring Fix #21's API-base contract.
- **Contract 1 — backend Stripe** (`agents._system("backend")`): read the owner's connected account from
  `STRIPE_CONNECTED_ACCOUNT_ID` and charge ON it (`Stripe-Account` header / `stripe_account=`) so money reaches
  the OWNER; treat it as already-connected (no runtime OAuth needed just to charge); OAuth is the fallback.
  Deploy INJECTION is already automatic — the id lives in `secrets_store` from slice 2, so STEP 5's
  `get_secrets` puts it in `deploy.env`. No deploy change needed.
- **Contract 2 — frontend Auth0** (`agents._system("frontend")`): read login config from
  `NEXT_PUBLIC_AUTH0_DOMAIN`/`_CLIENT_ID`/`_AUDIENCE`. Deploy wires these as **BUILD ARGs** (Next inlines
  `NEXT_PUBLIC_*` at build), values mapped from the provisioned Auth0 (`AUTH0_DOMAIN`/`AUTH0_CLIENT_ID`/
  `API_AUDIENCE`) via `manifest.frontend_public_env()`. New manifest constants `FRONTEND_AUTH0_ENVS` +
  `FRONTEND_AUTH0_FROM_BACKEND`; `_frontend_dockerfile` declares the ARGs; `_compose`/`build` thread
  `frontend_public` into the frontend `build.args` + runtime env; local + aws drivers compute
  `frontend_public_env(req.env)` (aws adds a `--build-arg` per value). An app WITHOUT Auth0 inlines none.
- **Tests:** `test_devops_offline.test_auth0_frontend_wiring` — mapping (source-present only, no secret leak),
  Dockerfile ARGs, compose build-args, no-Auth0-inlines-none, and DRIFT GUARDS (both codegen prompts name the
  exact manifest vars). All 15 offline suites pass; prompts live in the rebuilt backend.
- **⚠️ NOTE:** these change CODEGEN, so a FRESH generation consumes the connected Stripe account + provisioned
  Auth0. Run 1289's existing files predate the contracts — a full 1289 boot needs a fresh gen (or hand-wiring).
- **SMS DECIDED (2026-08-20): DEFERRED by user.** No per-number Twilio provisioning built. Slice 1's
  platform-held Twilio injection already covers it — set `TWILIO_*` → injected/used; absent → the app
  fail-fasts on SMS ONLY (everything else works). Revisit if a launch actually needs texting.
- **✅ ALL THREE PROVIDERS VERIFIED LIVE (2026-08-20)** against real free/test accounts the operator set up:
  - **Stripe** (test mode): owner account connected, `acct_…` persisted for 1289 (§1o).
  - **Auth0** (free tenant `dev-tenant.us.auth0.com`, M2M Mgmt app w/ create:resource_servers +
    create:clients): `ensure_provisioned(1289)` created a real API (audience
    `https://bella-vista-1523a5.apps.example.com/api`) + login client (client id 32ch, secret 64ch),
    persisted to secrets_store, idempotent reuse confirmed. Created Auth0 resources named `proj-1289`.
  - **Email** (Mailtrap sandbox `sandbox.smtp.mailtrap.io:587`): a real STARTTLS+login+send succeeded (test
    email trapped in the sandbox inbox). Platform SMTP creds valid.
  `.env` now holds `AUTH0_TENANT_DOMAIN`/`AUTH0_MGMT_CLIENT_ID`/`AUTH0_MGMT_CLIENT_SECRET`, `SMTP_*`,
  `SENDER_EMAIL`, and the Stripe test keys — all forwarded to the backend via docker-compose. **The entire
  owner-onboarding provisioning stack is proven against real providers, all on free/test tiers.**
- **OWNER-ONBOARDING EPIC — where it stands:** slices 1–4 DONE (platform-held injection; Stripe
  click-to-connect; Auth0 per-project auto-provision; codegen consumption contracts) — ALL LIVE-VERIFIED. SMS
  deferred.

## 1r. FRESH FULL RUN 1496 + FIX #27 — third-party import gate + build self-heal (2026-08-20)
First fresh full-scope run with ALL onboarding work live (coffee shop w/ ordering+payments+auth+tips, Quick).
- **Run 1496 result:** BA (✅ the new `connect_accounts` stage fired for a payments app; driver skipped it),
  PI ✅, Architect ✅ (22 tickets, Stripe Connect + notifications), Build ✅ 22/22 files, **smoke_boot ❌**.
  Root cause: generated `routes/integrate.py` wrote `from stripe.api_resources import PaymentIntent` →
  `ModuleNotFoundError` (stripe installed, that internal submodule doesn't exist). Cost $1.42. **WIN inside
  it:** the same file wrote `STRIPE_CONNECTED_ACCOUNT_ID = os.getenv(...)` — slice-4 Contract 1 worked in a
  fresh gen. Fixture captured: `backend/tests/fixtures/integrate_stripe_api_resources_1496.py`.
- **FIX #27 (committed `f5b71cc`):** the deferred third-party-import class (Fix #16 can't catch it — stripe
  isn't importable in the platform process). `qa/assembly._third_party_import_errors(venv, files)` AST-extracts
  every `from <third-party> import <names>` (skips in-project/stdlib/relative/star/bare-import) and probes them
  in the ASSEMBLY VENV (where the app's real deps are installed) → flags a wrong submodule path or a
  non-exported name. **Zero-FP:** only an INSTALLED package is checked; a `ModuleNotFoundError` is a finding
  ONLY when the missing module IS the path/parent, never a transitive/optional dep
  (`starlette.middleware.sessions`→`itsdangerous` is NOT flagged, via `ModuleNotFoundError.name` matching).
  Wired into `assemble()` after `_install_deps` → precise Failure + early return (no 45s crash);
  `TestEnv.import_errors` carries it. **Bounded self-heal (NEW — no auto-repair on boot failure existed
  before, runs just stopped):** `_smoke_boot` returns the findings; `main._run_build` regenerates the offending
  file(s) via `orchestrator.repair_import_errors` (targeted THIRD_PARTY_IMPORT repair, reuses
  `_contract_text`/`_model_for`/`build_ticket`) and re-boots, ≤2 attempts — the venv-stage analogue of #16's
  flag→repair→retry. Plus a backend prompt rule (import from the public top level, not a guessed submodule).
  Tests: `test_qa_offline.test_third_party_import_gate` (wrong-name + wrong-submodule flagged via installed
  pkgs; zero-FP on the platform's 68 modules + correct/in-project/stdlib/relative/star + missing-optional-dep;
  1496 fixture parsed as a candidate). All 15 offline suites pass; backend rebuilt.
## 1s. FRESH RUN 1557 + FIX #27 FP-fix + FIX #28 (endpoint-completeness self-heal) (2026-08-20)
Second fresh full run (coffee shop, Quick, 18 tickets). Chain of tail bugs, each now durably handled:
1. **Build ✅ 18/18 → smoke_boot: Fix #27 FIRED + self-healed** — but on a FALSE POSITIVE: `from jose import
   jwt` flagged as "jose has no jwt". `jwt` is a SUBMODULE (`jose.jwt`) that `import jose` doesn't auto-load →
   `hasattr` alone false-positived. **Fixed (`c0ec4cb`):** the probe now tries `import pkg.name` before
   concluding a name is missing. Regression test added. (Self-heal mechanism itself worked correctly.)
2. **Re-boot: NEW tail bug — missing designed endpoint** `GET /orders/{order_id}` (Architect designed it, no
   ticket generated it; app booted with 11/12 endpoints). → **FIX #28.**
- **FIX #28 (endpoint-completeness self-heal, `30ea220`):** the runtime check (`_check_designed_endpoints`,
  reads the booted app's `/openapi.json`, FP-free) now returns the STRUCTURED missing paths →
  `TestEnv.missing_endpoints`. `_smoke_boot` returns a combined findings dict `{import_errors,
  missing_endpoints}`; `main._run_build` runs ONE bounded boot-repair loop (≤2) that repairs EITHER class and
  re-boots. `orchestrator.repair_missing_endpoints` attributes each missing endpoint to the route file with
  the longest shared path-prefix (1557: `/orders/{order_id}` → the `/orders` route file) and regenerates it
  with a targeted MISSING_ENDPOINT repair (method+path+purpose from the blueprint), keeping existing routes.
  Tests: `test_developers_offline.test_missing_endpoint_attribution` (`_routes_in` w/ APIRouter prefix,
  `_shared_segments`, longest-prefix attribution). All 15 suites pass.
- **✅ VALIDATED LIVE:** ran the boot-repair loop on 1557 → attempt 1 regenerated the owning file to add
  `GET /orders/{order_id}` → **app BOOTED with all 12 endpoints**, `build:status:1557=done`. 1557 cost $0.64.
- **NOW:** 1557 boots fully. NEXT = continue 1557 → secure → QA → deploy (finally exercising the onboarding
  provisioning: Auth0 auto-provision + Stripe/SMTP inject at deploy), OR run another fresh run. Both projects
  1496/1557 left in the DB.
- Fix #27's prompt rule + gate + Fix #28 mean the recurring boot-tail classes (bad third-party import,
  missing endpoint) now SELF-HEAL at smoke_boot instead of stopping the build.

## 1t. FRESH RUN 1614 + probe hardening + FIX #29 (pin broken fastapi-limiter) — fresh gen BOOTS CLEAN (2026-08-20)
Third fresh full run (coffee shop, 21 tickets). Build ✅ 21/21 → smoke_boot flagged `from fastapi_limiter
import FastAPILimiter` as a bad import. **Investigation (important):** NOT a codegen bug — that import is
CORRECT and works in fastapi-limiter 0.1.6/0.1.5, but an unpinned `pip install fastapi-limiter` resolves to a
BROKEN **0.2.0** (empty `__init__`, no FastAPILimiter). So the gate saw a real failure but the fix is
version-pinning, not regeneration (the self-heal correctly bounded out — the code was already right).
- **Probe hardening (part of `cfe7a5b`):** the import probe used `hasattr()`, which false-flags names that
  ARE importable but not static attributes (jose.jwt submodule; lazily-bound names). Rewrote it to run the
  EXACT `from <mod> import <name>` statement in the venv — GROUND TRUTH, same as boot — classifying only the
  specific error (ModuleNotFoundError of the path → no_submodule; `cannot import name` → no_attr; a missing
  transitive dep / runtime side-effect → NOT flagged). Robustly fixes the jose class with no special-casing.
- **FIX #29 (`cfe7a5b`):** curated `_EXTRA_PINS` map (`fastapi-limiter==0.1.6`) consulted by `pin_spec`, so
  BOTH the QA/smoke_boot venv AND the deployed image install the working version; aliased import root
  `fastapi_limiter → fastapi-limiter`. Verified against the real packages (clean on 0.1.6, still flags
  httpx.NotARealThing / fastapi.fake_sub). All 15 offline suites pass.
- **✅ 1614 NOW BOOTS CLEAN (first attempt, imports=[], missing=[]), `build:status:1614=done`** — a FRESH
  full-scope generation that assembles + boots with ZERO hand-fixing of code (tail handled by self-heal +
  the pin). Cost so far ~$1.5. NEXT = continue 1614 → secure → QA → deploy (finally exercising onboarding
  provisioning at deploy). Projects 1496/1557/1614 in the DB.
- **🏆 1614 CONTINUED → secure ✅ Opus PASSED → QA ✅ 100/100 passed, 0 failed, still_certified:True →
  deploy attempted (2026-08-20).** FIRST fresh full-scope run EVER to reach a **fully clean QA** (100/100, no
  500s — the get_db/#24 + all gates held) after a real Opus PASS. **⭐ ONBOARDING PROVISIONING FIRED LIVE AT
  DEPLOY:** `secrets_store` for 1614 now holds `AUTH0_DOMAIN/API_AUDIENCE/AUTH0_CLIENT_ID/AUTH0_CLIENT_SECRET`
  (Auth0 auto-provisioned a real per-project app during deploy STEP 5) + minted crypto keys
  (`TOKEN_ENCRYPTION_KEY/STRIPE_TOKEN_ENC_KEY`, Fix #26). Total cost $2.99.
- **Deploy ❌ FAILED at the FRONTEND `next build`** (backend was fine; this is the FRONTEND quality tail):
  (1) `app/page.tsx` (FND-6 homepage) has raw CSS appended AFTER the component (`// CSS styles ... .container
  {...}`) → "Expression expected" TSX syntax error — Fix #15's balance check doesn't catch balanced-but-
  invalid TSX; only `next build` (Node) does; (2) `frontend/app/payment/page.tsx` imports `lodash.debounce`,
  not in package.json → "Module not found". Both are FRONTEND codegen bugs with NO current gate (no Node at
  build time). **NET: backend pipeline + onboarding + deploy-provisioning are PROVEN end-to-end; the last
  frontier is FRONTEND codegen quality (invalid TSX + missing npm deps).** Deploy stack torn down; no live URL.
  Candidate next fixes: a real TSX parse (needs Node, or a smarter Python check) + a frontend npm-dep gate
  (import → package.json). Or hand-fix 1614's 2 frontend files + redeploy for a live URL.

## 1u. FIX #30 — durable FRONTEND gates (missing npm dep + CSS-in-TSX) (DONE + tested 2026-08-20)
The two run-1614 frontend `next build` failures, now caught deterministically in Python (no Node). Committed
`c08bee5`.
- **(1) NPM dependency completeness:** `agents.frontend_missing_deps(files)` — every BARE frontend import must
  be a declared package.json dep (relative/`@/`-alias skipped; `lodash/debounce`→lodash; `@scope/pkg/sub`→
  @scope/pkg; `lodash.debounce` is its own package). **Deterministic GUARANTEED fix:** `manifest._add_npm_deps`
  adds any missing package to package.json `dependencies` at "latest" before the frontend build — the frontend
  analogue of the backend venv's dependency install. (Run 1614: `lodash.debounce`.)
- **(2) CSS-in-TSX:** `agents.frontend_css_leak(rel, content)` — flags a `.`/`#` CSS selector immediately
  followed by `{` at brace-depth 0 (after `_strip_code` removes strings/comments, so styled-component template
  literals are safe; a JS method chain never has `{` after `.foo`, so no FP). Wired into the build gate
  `_collect_stubs` alongside Fix #15. (Run 1614: `app/page.tsx` appended `.container { … }` after the component.)
- Zero-FP verified on the platform's own frontend (4 files). Tests:
  `test_developers_offline.test_frontend_deps_and_css_gate` (both detectors + manifest auto-add + build-gate
  wiring + negatives: declared/relative/subpath/scoped imports, method chains, styled templates, top-level JS
  objects). All 15 offline suites pass. Fixture `css_in_page_tsx_1614.tsx`.
- **NOTE:** the missing-dep class is now auto-fixed at DEPLOY (manifest); the CSS-in-TSX class is caught at the
  BUILD gate → regenerated. 1614's stored page.tsx still has the CSS (its build predates the gate) — a redeploy
  of 1614 auto-fixes lodash.debounce but page.tsx would need a regen. NEXT options: regen 1614's page.tsx +
  redeploy for a live URL, OR a fresh run with ALL gates (backend + frontend) live. **Only remaining for a REAL end-to-end deploy of an auth+payments app:** (1) the remaining §7
  human creds — Auth0 **test tenant + Management app** (free, like Stripe test mode) and an **email sender**;
  (2) a **FRESH generation** (the codegen contracts only affect new gens; 1289's files predate them). With
  those, a fresh full-scope run → QA → deploy should BOOT fully (Stripe test connect + Auth0 provisioned +
  crypto keys/Redis/config from Fix #26). Deploy gap #1 would then be genuinely closed for test-mode.

## 1k. FIX #24 — get_db swallows HTTPException → 500 (DONE + tested + live 2026-08-19)
Built exactly as scoped in §5.A / §1j, same rigor as #16–#23. Closes the run-1289 QA-500 class.
- **Root cause (confirmed, §1j step 6):** the generated `database.py` (FND-2) `get_db` wrapped
  `yield session` in `except Exception: raise HTTPException(500, "Internal server error")`. FastAPI
  runs the request INSIDE the generator's `yield`, so a downstream `HTTPException(401/404/422)` was
  caught by the broad except and re-raised as a 500 — masking every intended 4xx on every DB endpoint
  (all 20 QA failures). Public `GET /menu` (no error path) was unaffected.
- **Detector `agents.http_exception_swallow(content, filepath) -> [{file,line,function,detail}]`:**
  AST check that flags a DEPENDENCY GENERATOR (a function whose `try` body contains a `yield` —
  walked, so `async with … yield` nesting counts) whose handler (1) catches broad
  `Exception`/`BaseException`/bare-`except`, (2) raises/returns HTTP 500 (positional `500`,
  `status_code=500`, or `status.HTTP_500_*`), and (3) does NOT preserve already-HTTPException errors
  — no bare `raise`, no `isinstance(_, HTTPException)` guard, no earlier `except HTTPException` sibling
  on the same `try`. `.py` only; `SyntaxError` → `[]` (syntax gate #17 owns that).
- **Zero-FP by the two discriminators (proven):** (a) broad-only → gen888's `get_db` catching a
  SPECIFIC `SQLAlchemyError` is NOT flagged; (b) try-must-wrap-a-yield → plain route handlers that
  legitimately `raise HTTPException(500)` (gen888 menu_upload, 1105 stripe, 1071 order_be_3) are NOT
  flagged. Proven **0 findings** across the platform's own backend modules + 888's `gen888` files +
  the 1105/1071 fixtures; **true positive** on the captured 1289 `database.py` (flags `get_db`).
- **Wiring (mirrors #16/#17/#19):** `developers/orchestrator._collect_stubs` and
  `qa/orchestrator._gate_regenerated` set `http_swallow_repairs` → `agents.repair_instructions`
  renders a targeted `HTTP_EXCEPTION_SWALLOW` ticket → the existing flag→bounded-retry→fail / reject
  loop. Backend `_system("backend")` gained a get_db error-propagation prompt rule (let framework
  HTTPExceptions propagate unchanged; prefer plain `async with … yield`; catch specific
  `SQLAlchemyError`, never broad `Exception`, and re-raise HTTPException first if you must catch).
- **Fixture:** `backend/tests/fixtures/database_get_db_swallow_1289.py` (the real 1289 FND-2, id 2717).
- **✅ VALIDATED LIVE ON RUN 1289 (2026-08-19):** hand-fixed 1289's `get_db` in the DB (id 2717 →
  plain `async with async_session() as session: yield session`, no wrapping try/except) and re-ran QA
  (`POST /pipeline/qa`). Result **103 passed / 1 failed** (was 84/20) — **all 20 auth-gated
  order/notification 500s resolved to correct 4xx; all 22 order/notification/auth tests green; zero
  functional failures**, `files_rewritten_by_qa: 0` (no LLM regen — the fix alone did it). Cost $0.048
  (just the single-file drift re-review). The lone remaining red is `security: re-check after repairs`
  — the certification gate, NOT a functional bug: my edited database.py re-reviewed CLEAN
  (`recertified.passed: True`, 5/5, no criticals), but the overall cert stays `passed: False` because
  its stored base was already `passed: False` (1289 was `security_blocked` from the original review;
  `cert.passed = base_passed AND recert_passed = False AND True`). Restoring a passing cert needs a
  fresh full `POST /pipeline/secure` (Fix #23 makes it PASS per §1j step 4; ~$ Opus) — separate from
  the get_db fix and NOT done here (would spend money; awaiting user call). After that: QA→deploy hits
  the honest Week-7/8 secrets gap (deploy gap #1, deferred).

## 1l. RUN 1289 re-secure → DEPLOY reached the honest secrets wall + ⭐ NEW GAP: the reviewer fix-loop is UNGATED (candidate FIX #25) (2026-08-19)
Per user request ("re-secure 1289 then deploy") after §1k's get_db hand-fix. Exact sequence + findings:
1. **First `POST /pipeline/secure` SILENTLY NO-OP'd** — the review has a HARD GATE (`main._run_review`
   line ~284) requiring `build:status:{pid}=="done"` in redis, but that key has a 24h TTL and had
   EXPIRED (handoff was 2 days prior). It set `secure:status=error` with ZERO llm spend. Fixed HONESTLY:
   ran the real `main._smoke_boot(1289)` on the CURRENT DB files (with the get_db fix) → **booted clean**
   → legitimately restored `build:status:1289=done` (NOT faked — the code demonstrably boots).
2. **Re-`POST /pipeline/secure` → ✅ real Opus PASSED** (`claude-opus-4-8`, 22 files, 75 found/65 fixed,
   cert `passed:True`, cost **$0.82**). Fix #23's confirmation verdict gave a clean PASS again.
3. **⭐ DISCOVERY — the security reviewer's OWN fix loop is an UNGATED regeneration path.** Scanning all
   22 post-review files with the build-gate detectors: the reviewer's `_fix` (general model, minor/medium
   issues) **REWROTE `database.py` and RE-INTRODUCED the exact get_db HTTPException-swallow** Fix #24
   targets (clean during the §1k QA run → dirty right after this review; line 66 `except Exception: ...
   raise HTTPException(500)`), AND flagged `StripeAccount.owner_id` in `stripe.py` (Fix #19 class; may be
   pre-existing). This is the SAME hole Fix #18 closed for the QA loop, now in `reviewer.review_file`.
   `review_subset`/`review_file` write fixes back WITHOUT running the deterministic build gates, so a
   "helpful" error-handling fix reintroduces a gate-class bug. Evidence fixture:
   `backend/tests/fixtures/database_reviewer_reintroduced_swallow_1289.py` (the reviewer-rewritten file).
   **➡️ CANDIDATE FIX #25 (PROPOSED, NOT BUILT — plan-first):** run the build-gate detectors
   (#16/#17/#19/#24) on `reviewer._fix` output; reject/repair a fix that introduces a gate-class bug
   (mirrors Fix #18's bounded re-validate/reject for the QA loop). Regression fixture = the captured file.
4. **`POST /pipeline/deploy` → HONESTLY `failed` at the backend layer** (exactly Fix #20's design):
   `status:failed`, `failed_layer:"backend"`, `live_url:null` (NO false live), `security_certified:true`,
   `tests_passed:103`, `health_attempts:13`. The generated code fail-fasts at startup on the Week-7/8
   secrets gap (AUTH0/STRIPE/ENCRYPTION_KEY/ALLOWED_ORIGINS + missing Redis) — deploy gap #1, DEFERRED by
   decision (NOT auto-seeded). Deploy stack was torn down cleanly (no orphaned 1289 containers, no idle
   spend). NOTE: the deployed database.py carried the reviewer-reintroduced get_db bug, but it never
   manifested — the backend can't boot past the secrets fail-fast anyway.
**NET:** re-secure works (real Opus PASS, Fix #23 holds); deploy reaches the honest secrets wall (Fix #20
holds, no false live). The one blocker to a CLEAN full-scope deploy is now TWO deferred items: deploy gap
#1 (secrets onboarding) and candidate Fix #25 (gate the reviewer fix-loop). Project 1289 LEFT IN THE DB;
its database.py currently holds the reviewer-reintroduced swallow (evidence for Fix #25).
- **Tests (all 14 offline suites pass):** `test_developers_offline.test_http_exception_swallow_gate`
  (true positive; the 5 negatives — specific-exc / HTTPException-sibling / isinstance-guard / bare-raise
  / route-handler-no-yield; zero-FP corpus; gate integration + repair text) +
  `test_qa_regen_gate_offline.test_gate_http_swallow`. Backend REBUILT; the 9-gate liveness one-liner
  (extended with `http_exception_swallow`) prints `True`. Committed `290ff82`, pushed.

## 2. THE THREE MEASUREMENT RUNS (1007, 1038, 1039) — proof + the ROOT-CAUSE diagnosis
All three: same idea (Bella Vista Italian restaurant, **PDF menu upload**, Quick launch),
real Opus ON, scoped key. **All three cleanly passed: BA → PI → Architect → Build (no gate
rejections) → smoke_boot → real Opus security review PASSED.** So the 15 fixes genuinely
HOLD TOGETHER on real paid runs. Each then died AFTER that on a DIFFERENT one-off codegen bug:

| Run | Died at | The new bug (NOT one of the 15) |
| --- | --- | --- |
| **1007** | deploy | Generated `admin/menu/review/page.tsx` was **TRUNCATED** mid-JSX (LLM output cut off) → `next build` syntax error. (QA passed 79/79 — its real `next build` is opt-in/off.) → led to **fix #15**. |
| **1038** | QA | `menu_upload.py` imported invented `require_admin` (auth exports `get_current_admin_user`) — **D3 wrong-symbol**; then 12× 500 on a buggy unrequested `/api/analytics/*` feature; then 10× 500 on `/admin/stripe/*`; the retry loop then broke the boot. |
| **1039** | QA | 10× 500 on `/admin/stripe/*` (the deferred payment feature); then the retry loop regenerated `menu_upload.py` to `from pypdf import PdfReadError` (**not a top-level pypdf symbol** — it's in `pypdf.errors`) → app no longer boots. |

**⭐ KEY DIAGNOSIS (this is the real root cause, not bad luck):** the QA **retry loop can
regenerate a file and INTRODUCE a NEW bug faster than it fixes the original** — it is not
converging. On 1038 and 1039, hand-fixing one bug triggered a QA re-run whose retry loop
churned other files into a non-booting state. So: end-of-pipeline gates + a blind
regenerate-and-retry loop cannot guarantee a clean app. **Validation must move EARLIER —
into Developer generation itself — and repair must be BOUNDED and re-validated.** That is
the entire motivation for the Code Integrity Engine (§4).

Cost ≈ $2.6–5 per run (generation + real Opus). Recommendation given + accepted: **stop
fresh-run roulette; build the durable fix (#16 first).**

## 3. RECORDABLE DEMO — project 888, FULLY WORKING & LIVE RIGHT NOW (separate from fresh-run work)
The demo does NOT depend on a clean fresh run. **Project 888 is a frozen, hand-verified
fixture** proving the menu-onboarding feature end to end, and it is **running now**:
- Stack in `scratchpad/deploy888/` (⚠️ SESSION SCRATCHPAD = ephemeral; relocate for permanence):
  **`site`** (nginx, a polished Bella Vista menu page) on **http://localhost:8890**,
  **`app`** (FastAPI backend) on **http://localhost:8899**, **`postgres`**, **`idp`** (a local
  JWKS server standing in for Auth0). Relaunch: `docker compose -f
  scratchpad/deploy888/docker-compose.deploy888.yml up -d --build` (a `down -v` wipes the
  menu DB → re-upload the PDF + confirm to repopulate).
- **What it proves, all real:** real backend; **real menu PDF extraction** (text path via
  pdfplumber→Claude parse, vision fallback via a real Anthropic image/document call, model
  `claude-haiku-4-5`, using the SCOPED key); **real auth** (RS256 admin JWT validated against
  the local JWKS — sig/aud/iss/`admin` permission); the **review gate** (nothing publishes
  until confirmed); a **real published public menu** (7 dishes from the user's real PDF); and
  a **polished frontend** at :8890 that fetches `GET /menu` LIVE from the backend (CORS wired;
  footer prints the data source — proof it isn't hardcoded). Raw-JSON proof URL:
  `http://localhost:8899/menu`. Admin JWT (30-day) in `deploy888/idp/admin_token.txt`.
- The demo's `menu_upload.py`/`menu.py`/`models.py`/`main.py` were HAND-FIXED in 888's DB
  fixture to a working state (real parse, fixed vision, `source_name`+`created_at`, `get_db`,
  images+scanned-PDF support, order/stripe stripped). It is a fixture, not a fresh generation.

## 4. THE NEW PLAN — "CODE INTEGRITY ENGINE" (architectural pivot in how reliability is ensured)
**Thesis (grounded in §2's diagnosis):** stop relying only on end-of-pipeline validation
(QA/Opus) + a blind retry loop. Insert **deterministic validation DURING Developer agent
execution** — as each file is generated/written — with **bounded, re-validated repair** and
**transactional checkpoints** so a repair can never leave the build worse than before.

**⚠️ HONEST GAP FOR THE NEXT SESSION:** the user said a "full spec" for this was given this
session. That detailed spec text is **NOT in the captured context** (long session; context
was summarized) — it was NOT recorded verbatim and MUST be re-shared by the user or
reconstructed at the start of the next session. Do NOT invent spec details. What IS reliably
captured is the component OUTLINE the user enumerated, plus the design principles from §2:

- **Three validation levels** (level names/exact scope to be confirmed from the real spec;
  working understanding): **L1** single-file structural/syntactic integrity (parses, complete,
  balanced — generalizes fix #15's truncation check + a syntax/parse check per file);
  **L2** symbol resolution (every imported/referenced name resolves to something that actually
  exists — imports resolve to real exported symbols; **FIX #16 is the first slice of L2**);
  **L3** cross-file / contract validation (files agree with each other and with the Architect's
  binding contract — extends the existing schema-adherence + module-map ideas across the whole
  app).
- **Symbol resolution** — build a symbol table of what each generated module actually exports
  (functions/classes/vars) and validate every `from X import Y` / usage against it; catches the
  `require_admin` (1038) and `PdfReadError` (1039) classes deterministically.
- **Cross-file / contract validation** — the generated code must satisfy the blueprint's
  `database_schema`, `api_endpoints`, and generated module map (paths + exported symbols).
- **Structured failure objects** — validators return typed, machine-readable failures (file,
  location, kind, offending symbol, suggested fix) — NOT free-text — so a repair step can act
  precisely and a measurement harness can aggregate them.
- **Bounded repair loops** — a fixed max number of targeted repair attempts per finding, each
  followed by RE-VALIDATION; never an open-ended regenerate-and-hope (this is the direct
  antidote to the 1038/1039 retry-churn root cause).
- **Transactional checkpoints** — snapshot the build state before a repair; if a repair does
  not strictly improve validation (or breaks something), ROLL BACK to the checkpoint. A repair
  must never make the build worse (this is exactly what the QA retry loop violated).
- **Measurement methodology** — a defined way to measure validator effectiveness (e.g., replay
  captured buggy fixtures like 1007's truncated page / 1038's `require_admin` / 1039's
  `PdfReadError`, count catch-rate + false-positive-rate on known-good files) so each level is
  proven the way every prior fix was (regression tests on real captured bugs).

**Design principles that ARE firmly established (from this whole session, safe to rely on):**
deterministic (no LLM) validators; run at BUILD time (no Node in the backend container — use
Python AST/structural checks, not SWC/tsc, exactly as fix #15 does); zero false positives on
valid code (validate against the platform's own frontend + real generated files before wiring);
each validator regression-tested against a REAL captured bug fixture; wire into the existing
`developers/orchestrator._collect_stubs` gate pattern (flag → bounded retry → fail) but evolve
that loop toward the checkpoint/re-validate model above.

## 5. EXPLICIT NEXT STEP — decide candidate FIX #24 (the run-1289 get_db 500). PLAN-FIRST.
Code-integrity gates (#16–#19) + security-verdict fix (#23) are solid and VALIDATED LIVE on run 1289
(§1j: real Opus PASSED, first ever). DEPLOY GAPS #2/#3/#4 ALL CLOSED (#20/#21/#22). The one open,
concrete item is the run-1289 QA finding, already fully diagnosed:

### A. ✅ DONE — FIX #24 (get_db swallows HTTPException → 500). See §1k for the full record.
BUILT + tested + live + pushed (`290ff82`, HEAD). AST detector `agents.http_exception_swallow` wired
into `_collect_stubs` + `_gate_regenerated`, backend prompt rule added, zero-FP proven, regression test
on the captured 1289 `database.py`. **Next concrete step:** re-run 1289 QA→deploy (or hand-fix its
get_db) to reach the honest Week-7/8 secrets/redis gap — deploy gap #1, DEFERRED by decision (§5.C);
do NOT auto-seed secrets. Fix #20's layered health check will report the secrets failure honestly
("backend layer" failed, no false `live`).

### B. (OPTIONAL) Fix #19 slice 2 — annotated/constructed INSTANCE attribute access
Extends the attribute gate (#19, §1e) from class-name access to instance access where the type is
KNOWN with certainty (a `: Order` annotation or a local `x = Order(...)` construction) — catches
`order.total_amonut` / `user.get_profile()` when the instance is typed/constructed. Query-derived
instances stay OUT (not safely inferable). Kept only insofar as the platform+888 zero-FP proof
stays clean (that proof is the arbiter). Plan-first.

### C. ⛔ DEFERRED BY DECISION (2026-08-17) — the Week-7/8 SECRETS-ONBOARDING gap (deploy gap #1)
**Deliberately NOT auto-seeded.** A real deploy of an auth+payments app fail-fasts across `AUTH0_*`,
`STRIPE_CLIENT_ID/SECRET_KEY` (genuinely owner-specific), plus `ENCRYPTION_KEY`/`STRIPE_TOKEN_ENC_KEY`/
`ALLOWED_ORIGINS` and a `REDIS_URL` + a provisioned Redis (platform-generatable) — none of which the
DevOps deploy path seeds/provisions. The generated code is CORRECT to fail-fast; FIX #20 now makes
that failure HONEST (a `MISSING_CONFIG` "backend layer" failed, not a false `live`). **The user's
explicit call: do NOT build a quick auto-seed to make a demo deploy succeed.** This is the same
secrets-onboarding gap open since Week 7-8 and deserves its OWN careful, dedicated design session
(per-owner secret onboarding: how an owner connects their Auth0 tenant + Stripe account; and the
platform-generatable infra secrets + Redis provisioning). Do NOT patch it in passing.
Run 1105 proved a real deploy of an auth+payments app fail-fasts across `AUTH0_*`, `STRIPE_*`,
`ENCRYPTION_KEY`, `ALLOWED_ORIGINS`, and needs a `REDIS_URL` + an actual Redis service — none of
which the DevOps deploy path seeds/provisions. The generated code is CORRECT to fail-fast; the
platform must seed these (per-owner secrets + a provisioned Redis) at deploy time. Big, separate.

**📄 PLAN WRITTEN (2026-08-19), NOT built — `PLAN_owner_onboarding.md` (repo root).** Full plan-first
proposal for the OWNER-account half of gap #1 ("problem #1"). Decisions locked with the user: Auth0 =
platform auto-provisions (owner does nothing); Stripe = click-to-connect (Stripe Connect OAuth) surfaced
in a NEW BA `connect_accounts` stage BEFORE deploy; Email = platform sends on the owner's behalf; SMS =
platform-provide-if-simple-else-defer. Key finding in the plan: the only GENUINELY owner-specific secret
is the connected Stripe `account_id`; STRIPE_CLIENT_ID/SECRET_KEY/REDIRECT_URI + Auth0 tenant + SMTP are
all platform-held. Includes the one-time HUMAN setup (platform Stripe Connect acct, Auth0 Management app,
email sender), the deploy-STEP-5 injection design, zero-regression test strategy, and a build order.
The PLATFORM-solvable trio (crypto-key mint+persist, Redis service, config defaults) is a SEPARATE plan
(problem #3, still to write). Do NOT implement either without explicit go-ahead; do NOT auto-seed secrets.

### C. (bundle where it fits) NEW deterministic-catchable codegen bugs 1105 surfaced
- **DDL bug:** `models.py` `server_default='CURRENT_TIMESTAMP'` as a STRING → `create_all` fails →
  no tables → every DB endpoint 500s. Make smoke_boot/QA actually CREATE TABLES (not just "uvicorn
  started") so this is caught, and add a Backend-Dev prompt rule to use `text('CURRENT_TIMESTAMP')`
  / `func.now()`. Plus the async `create_all(bind=eng)` bootstrap fallback in `_devops_bootstrap.py`.

### LATER — the deferred third-party DEPENDENCY-VALIDATION slice (`PdfReadError`)
Still queued. **The bug (1039):** the QA retry loop wrote `from pypdf import
PdfReadError`, but that name lives in `pypdf.errors`, not top-level pypdf → boot fail. NOT foldable
into #16: `pypdf` is a DEPLOY/QA-venv dependency, NOT importable in the platform process, so the
build gate can't introspect it without false positives. RIGHT home = a gate INSIDE the QA/assembly
venv (`qa/assembly.py`) where the app's real deps are installed; for each `from <pkg> import Y`
with `<pkg>` importable, verify `Y` exists (skip if not importable → no false positive).
Regression-test against the real 1039 `PdfReadError`; prove zero FP on platform + 888 real
third-party imports; one slice, plan-approved first.

**Design principles (unchanged, now proven three times — #15/#16/#17):** deterministic (no LLM);
each validator regression-tested against a REAL captured bug fixture; ZERO false positives on valid
code, proven against the platform's own code + 888's real files BEFORE wiring; bounded,
re-validated repair via the `_collect_stubs` flag → retry → fail pattern; evolve toward the
checkpoint/re-validate model. **Measured on 1105: build-time detection is solved; the frontier is
now (1) gating the QA regeneration loop and (2) the Week-7 secrets/redis deploy onboarding.**

## 6. GIT + STATE AT HANDOFF (2026-08-17 late)
**FIX #24 COMMITTED + PUSHED. `HEAD == origin/master == 290ff82` (Fix #24); this CONTEXT update is the
only uncommitted change at the moment of writing.** All fixes #16–#24 are on `origin/master`, one
commit each, in order: `90169ee` #16, `5a640a1` #17, `5963e1d` #18, `cf4563d` #19, `81a2d8c` #20,
`e5405e4` #21, `3a3854c` #22, `6947af0` #23, `290ff82` #24 (plus the run-1105 CONTEXT commits
`5754caa`/`6f0c7fd` between #17 and #18, and the milestone handoff commit `ab2ed44` before #24).
github.com/Rajkumar2002-Rk/ai-org (private).
Permanent rules: **no `Co-Authored-By`, ever**; never commit `.env`; keep the repo private.
- **This CONTEXT.md handoff update is the only uncommitted change at the moment of writing — commit +
  push it as the final act.** Nothing else is local-only. Candidate FIX #24 is NOT written (proposal
  only, §5.A / §1j).
- **THE RUNNING BACKEND `ai-org-backend-1` HAS Fix #16–#23 LIVE** (rebuilt after #23). ⚠️ It does NOT
  yet include this CONTEXT commit — no code changed after #23, so no rebuild needed; but a fresh
  session should `docker compose build backend && docker compose up -d backend` from latest to be
  safe, then verify all 8 gate families import (one-liner):
  `docker exec ai-org-backend-1 python -c "from app.developers import agents as a; from app.devops import health, manifest; from app.architect import builder; from app.qa import orchestrator as qo; from app.reviewer import reviewer as rv; print(all([hasattr(a,'import_symbol_mismatches'),hasattr(a,'python_syntax_error'),hasattr(qo,'_gate_regenerated'),hasattr(a,'attribute_access_mismatches'),'failed_layer' in health.ProbeResult.__dataclass_fields__,'handle_path /api/*' in manifest._caddyfile('x',True,True,''),hasattr(builder,'_frontend_homepage_ticket'),hasattr(rv,'_confirmed_critical'),hasattr(a,'http_exception_swallow')]))"`
  → must print `True` (that covers #16/#17/#18/#19/#20/#21/#22/#23/#24 respectively).
- **`.env` config live:** `SECURITY_REVIEW_ENABLED=true`, `CODEGEN_MODE=real`, `DEPLOY_TARGET=local`;
  OpenAI + Anthropic + Gemini + scoped `MENU_EXTRACTION_API_KEY` all present & pinged live this session.
- **All 14 offline suites PASS** (run: `docker compose run --rm --no-deps -e PYTHONPATH=/app -v
  "$PWD/backend:/app" backend python tests/<suite>.py`). Suites: architect, background,
  d4_force_dynamic, developers, devops, documentation, menu_onboarding, qa, smoke_boot_gate,
  venv_pinning, qa_classification, qa_retry_loop, qa_teardown, qa_regen_gate.
- **PROJECT 1289 LEFT IN THE DB** (status `security_blocked`) — its `database.py` (FND-2) is the Fix
  #24 regression fixture; grab it before any cleanup. No 1289 deploy containers exist (it never
  deployed). The `qa-build-*` ephemeral instance from the diagnosis was torn down.
- **NOTHING IS SPENDING MONEY** — verified 0 llm_usage in the last 3 min; no host pollers / log tails;
  no monitors/loops (backend runs pipeline stages only when manually POSTed). Running containers are
  all idle: `ai-org-backend/frontend/postgres/redis` + the local `deploy888` demo (no idle LLM spend).

---

# 📚 SESSION DETAIL / HISTORY (the handoff above is the authoritative resume point; below is supporting detail, most-recent first)

# Full measurement run: 14 fixes held (clean QA + real Opus); deploy hit a NEW frontend-truncation bug, now gated (2026-08-12)

## 📏 MEASUREMENT RUN (project 1007, Bella Vista + PDF menu, Quick plan) — the cleanest run yet
Ran ONE full paid pipeline with the real Opus review back ON and the scoped extraction key live,
to measure whether all fixes hold together. Result — stage by stage:
- BA → PI → Architect ✅ (menu tickets MENU-1..4; `menu_items` uses `source`)
- Build ✅ 15/15 files, **no stubs** — all build-gate checks clean (no stub fn, no
  `Depends(async_session)`, no schema rename)
- smoke_boot ✅ · security_review ✅ **real Opus PASSED** (66/69 fixed, real cert) ·
  QA ✅ **79/79 passed, 0 failed** — FULLY CLEAN, no menu 500. **First run ever with a clean QA +
  a real passing Opus review with every fix active.** None of the fixed bug classes recurred.
- deploy ❌ **FAILED** at the frontend `next build`: MENU-4 `admin/menu/review/page.tsx` was
  **TRUNCATED** (LLM output cut off mid-JSX; `styles`/`inputStyle` undefined). NOT one of the 14
  fixes, NOT the AUTH0 gap — a NEW "generated-code quality tail" bug. It exposed a QA GAP: QA's
  real `next build` is opt-in and OFF (`qa_frontend_full_build=false`), so a truncated .tsx sailed
  through QA (79/79) and only died at deploy. Cost ≈ $2.6–4.

## 🔧 FIX #15 — deterministic frontend truncation/parse gate (this closes the 1007 blocker)
No Node at build time, so we parse frontend files STRUCTURALLY in Python:
`agents.frontend_incomplete(rel, content)` strips comments/strings/template-literals/regex, then
checks `{}()[]` balance + unterminated strings → flags a truncated/invalid `.tsx/.ts/.jsx/.js`.
Wired into BOTH: (1) the build gate `orchestrator._collect_stubs` (flag → retry → fail, before the
review/deploy) and (2) QA's ALWAYS-ON static check `level1._check_frontend` (a truncated file now
FAILS QA, not four stages later at deploy). Validated: flags 1007's EXACT file, ZERO false
positives on the platform's own frontend + 1007's other pages. Tests:
`test_developers_offline.test_frontend_completeness_gate` +
`test_qa_offline.test_frontend_truncation_caught_statically`, both using the real 1007 file
(`backend/tests/fixtures/truncated_review_page_1007.tsx`). All 13 free suites pass. Backend REBUILT
so the gate is live for the next measurement run.

### 📏 SECOND measurement run (project 1038, 2026-08-13) — the quality tail, in full
Fresh full run with all 15 fixes + real Opus + scoped key. Build ✅ (22 files, no gate rejections —
**#15 held, no truncation**), smoke_boot ✅, Opus ✅ (real, 106/115 fixed), then **QA FAILED** on a
CASCADE of NEW one-off bugs — none of the 15: (1) `menu_upload.py` imported an invented
`require_admin` (auth exports `get_current_admin_user`) → boot fail (a **D3 wrong-symbol**; fix #3's
PROMPT rule is non-deterministic and didn't stop it); (2) after hand-fixing that, 12× 500 on a buggy
`/api/analytics/*` feature; (3) after stripping that, 10× 500 on `/admin/stripe/*` and the **QA retry
loop regenerated files and broke the boot entirely**. Verdict: **the 15 fixes hold, but a FRESH
generation trips over DIFFERENT random LLM bugs each run** (1007 = frontend truncation; 1038 = wrong
symbol + buggy analytics/stripe). Cost ≈ $5–6. 1038 deleted. **This is exactly why the frozen fixture
exists** — a fresh-pipeline live URL is gated by codegen quality, not by any missing fix.

### 🟢 RELIABLE LIVE DEMO = the frozen 888 deploy (UP NOW)
Per the user's call, the frozen 888 fixture is the reliable live demo (a fresh-generation live URL is
NOT needed — 888 already proved it end to end). Stack is **UP at http://localhost:8899**
(`scratchpad/deploy888/`: app + Postgres + local JWKS IdP). Public site `GET /menu` (no auth) serves
7 real dishes, extracted from the real PDF via the SCOPED key and published through the review gate.
A fresh **30-day** admin JWT is in `deploy888/idp/admin_token.txt`. ⚠️ The stack lives in the SESSION
scratchpad (ephemeral) — for a permanent demo, relocate `deploy888/` out of the scratchpad. Bring it
back up with `docker compose -f scratchpad/deploy888/docker-compose.deploy888.yml up -d --build`,
then re-upload the PDF + confirm to repopulate (the `down -v` teardown wipes the menu DB).

### Still open (candidate future fixes)
- **FIX #16 — deterministic in-project symbol-resolution gate: ✅ DONE (2026-08-15), see §1a.**
  Catches 1038's `require_admin` at the build gate; verified 0 false positives on 64 real platform
  modules + 888's real files; structured-repair retry integrated. Closed the D3 "wrong symbol from a
  correct in-project module" family. (The analytics/stripe runtime 500s remain app-LOGIC quality —
  much harder to gate deterministically; that tail is why the frozen fixture is the demo path.)
  NEXT scoped slice = the third-party dependency-validation gate (`PdfReadError` class), to run in
  the QA/assembly venv — see §5.
- **The real DevOps-path deploy of an auth-gated app** is still unproven end-to-end (Week-7
  secrets-onboarding gap: no `AUTH0_*` seeded → the app fail-fasts at boot). The FEATURE is proven
  (via the local-IdP deploy); the platform deploy path for auth-gated apps is not.
- **`security_review_enabled=true` (real Opus back ON)**; scoped `MENU_EXTRACTION_API_KEY` is live +
  distinct from the master key. Projects 1007 + 1038 cleaned up.

---

# (prior top section) MENU ONBOARDING FEATURE CLOSED: real-HTTP + real-auth end-to-end PROVEN (2026-08-12)

## ✅ MENU ONBOARDING — CLOSING PROOF (2026-08-12, late) — full real-HTTP, real-auth lifecycle
The feature is proven end-to-end THROUGH the deployed app over real HTTP with real auth — not by
calling functions. A local deploy of frozen fixture **888** (app + Postgres + a **local JWKS IdP**
standing in for Auth0, since no Auth0 tenant exists) ran the whole lifecycle with a real RS256 admin
JWT (validated against the JWKS: signature, audience, issuer, `'admin'` permission):
`POST /admin/menu/upload` (no/bogus token → **401**; valid token + the user's real PDF → **200, 7
items**) → `GET /admin/menu/pending` (7 `pending_review`) → `POST /admin/menu/confirm` (7 published)
→ public `GET /menu` (7 published; empty before confirm — the review gate holds). The stack is still
up at `http://localhost:8899` (compose in `scratchpad/deploy888/`, token in `idp/admin_token.txt`);
the user asked to leave it running.

**TWO MORE BUGS found ONLY via the real path** (invisible to direct function calls), fixed + baked
into 888 AND source-hardened this turn:
- `Depends(async_session)` → every request **422** (FastAPI read the sessionmaker's
  `__call__(**local_kw)` as a required query param). Must be `Depends(get_db)`.
- `MenuItemResponse.source` vs model attr `source_name` → **500** on the *published* GET /menu
  (ResponseValidationError, only once rows are serialized). The response field must match the model.

**SOURCE FIXES this turn** (deterministic gate + prompt, same pattern as the stub gate):
`agents.bad_session_dependency()` (flags `Depends(async_session)`) and
`agents.model_schema_mismatches(models, database_schema)` (flags a model that renamed/omitted a
contract column, e.g. `source`→`source_name`), both wired into `orchestrator._collect_stubs`
(the build gate: flag → retry → fail). Backend-Developer `_system` gained the matching rules.
Tests: `test_developers_offline` (`test_build_gate`, `test_session_dependency_rule`,
`test_schema_adherence`). **All 13 free suites pass.** ⚠️ Rebuild the backend before the next real
pipeline run so these gate checks are live.

## ⭐ EARLIER (2026-08-12, evening) — extraction proven, treadmill broken, source-hardened
The pipeline was burning ~$3/run to rediscover a NEW random LLM bug each run (801 Base, 829
conlist, 860 D4, 888 menu-500). We stopped that:
- **Opus review is now OPTIONAL** — `security_review_enabled` (config + `SECURITY_REVIEW_ENABLED`
  in compose/.env, currently **false**). Skips the paid review for LOCAL debugging (~$3→~$1/run);
  ignored for AWS; the cert is honestly marked `security_review_skipped` and the deploy is
  reported NOT certified. Committed `1e61728`. **Re-enable (set true) before any real run/demo.**
- **FROZEN WORKING FIXTURE = project 888** (a menu app, kept in the DB — do NOT delete). Its
  generated code was hand-fixed to a genuinely working state with ZERO further paid runs:
  stripped the buggy order/stripe models+routes (a duplicate `Index('ix_orders_account_id')` +
  `index=True` made `create_all` roll back ALL tables → every read 500'd), and BAKED IN real
  extraction. It now boots, `GET /menu`→200, and end-to-end EXTRACTS+SAVES: 7/7 dishes from a real
  PDF persisted as `pending_review`.
- **MENU EXTRACTION PROVEN on the user's REAL menus** (`menu_upload.py` was a STUB —
  `parse_menu_items` was literally `return []`, vision had a fake model + wrong format + OpenAI-
  style response parsing, save used `source=` not `source_name`). With real code: TEXT path
  (pdfplumber→Claude parse) = 7/7 dishes exact; VISION path (fixed Anthropic image block, model
  `claude-haiku-4-5`) = 7/7 from a photo exact; corrupt files fail gracefully. Names+prices 100%.
- **SOURCE-HARDENED (this is the durable win, uncommitted until this turn's commit):** a
  deterministic **stub-function gate** — `agents.stub_functions()` (AST: a work-named function
  whose whole body is `pass`/empty-return/`NotImplementedError` is a stub) wired into
  `developers.orchestrator._collect_stubs` so a stubbed `parse_/extract_` function is treated as a
  stub (retry→fail), same as a whole-file stub. Plus prompt rules: the Backend-Developer `_system`
  forbids placeholder functions, and MENU-3 pins real parsing + correct `response.content[0].text`
  + a proper base64 image block. Tests: `test_developers_offline` (stub detection + gate + prompt),
  `test_menu_onboarding_offline` (MENU-3 rule). **All 13 free suites pass.**

### ⚠️ KNOWN-OPEN after this session
- **`source` vs `source_name`:** RESOLVED as a class by the `model_schema_mismatches` gate check
  (future generations that rename a contract column fail the build). NOTE: 888's frozen fixture is
  internally consistent on `source_name` (model + save + response schema all aligned this turn) and
  works — it just differs from the contract's `source`; harmless for the fixture.
- **888 lives only in the DB** (portable JSON export still not done — deferred by the user).
- **Real deploy used a controlled local run + local IdP, NOT the platform DevOps path.** The DevOps
  deploy of 888 would fail to boot without seeded `AUTH0_*` secrets (the Week-7 secrets-onboarding
  gap) and can't easily inject a local IdP/CA. So a deploy through the actual `POST /pipeline/deploy`
  path (with real Auth0 or seeded secrets) remains unproven; the FEATURE is proven, the platform
  DEPLOY path for an auth-gated app is not.
- **The `deploy888` stack is still running** (host port 8899) — tear down with
  `docker compose -f scratchpad/deploy888/docker-compose.deploy888.yml down -v` when done.

---

**Start the next session with:** "Read CONTEXT.md. Fixes #12–#14 are in — re-run the Bella
Vista restaurant idea; it should now reach a LIVE deploy URL and exercise menu PDF extraction."
THIS session (2026-08-12) closed three deterministic fixes across two milestones. First a
GATE-INTEGRITY hole (project 829): smoke_boot passed an un-bootable build (paying for the Opus
review) because the throwaway QA/smoke_boot venv was NOT version-pinned → **fix #12** (pin the
venv to the deploy's versions) + **fix #13** (Pydantic v2 prompt rule). Then project **860
became the FIRST run to fully pass QA (104 tests) and reach the DEPLOY step** — where it hit the
**D4** frontend-build bug (`next build` prerendering `/integrate`, a `useSearchParams` client
page) → **fix #14** (force the app dynamic via the ROOT SERVER `layout.tsx`; the old page-level
force-dynamic was DISPROVEN on Next 15 and must NOT return). A separate defect (order.py imports
a nonexistent `Item` symbol) is LOGGED as a D3-family follow-up. **The very next run is expected
to reach a LIVE deploy URL** and finally exercise menu PDF extraction end to end.

**WHAT 829 PROVED (the gate escape, fully diagnosed — do NOT re-litigate):** generated
`routes/order.py` used the Pydantic **v1** spelling `conlist(OrderItem, min_items=1)`, a hard
`TypeError` at import under Pydantic v2. Hard evidence showed the bug was in the ONE-AND-ONLY
version of order.py (id 1767, never regenerated) — so it was NOT "regenerated after the gate".
smoke_boot passed anyway (booted clean in 9s) while QA fail-booted the SAME files: the venv was
`--system-site-packages` + UNPINNED, so it could boot under a different Pydantic than QA/deploy.
The user's first theory (re-run smoke_boot after a QA regeneration) was DISPROVEN by the
evidence; the real fix is making the environment deterministic + identical.

**EXACT CURRENT STATE (fixes #12/#13/#14 landed, verified):** all **13 free offline suites PASS**
(added `test_venv_pinning_offline` + `test_d4_force_dynamic_offline`). Fix #12 proven by an
integration re-assemble of 829's real files (gate `env.ok=False`, venv pinned `pydantic==2.10.4`);
fix #14 proven by `test_d4_real_build.sh` — a real `next build` on 860's actual layout+page FAILS
without the layout fix and SUCCEEDS with it (`/integrate` becomes `ƒ` dynamic). Fixes #12/#13 and
#14 are BOTH COMMITTED locally (two commits: "Fix #12/#13…" then "Fix #14…"). Projects **829 AND 860
have been CLEANED UP** (DB rows cascade-deleted + 860's orphaned deploy images removed); DB otherwise
CLEAN. **Backend image REBUILT** so the running server carries #12–#14 for the next live run.

**GIT — fixes #12/#13/#14 are TWO local commits on master, NOT pushed** ("Fix #12/#13…" then
"Fix #14…"). Base parent is `e1326ad` (== `origin/master`); FND-1 `1cda1f9` is its parent (both
pushed). So `origin/master` is 2 behind local — `git push` when ready.
github.com/Rajkumar2002-Rk/ai-org (private). Permanent rules: **no `Co-Authored-By`, ever**;
never commit `.env`; keep the repo private.

**KEYS/CONFIG (verified live this session):** OpenAI ✅ + Anthropic ✅ + Gemini ✅ all
funded. `.env`: `CODEGEN_MODE=real`, `DEPLOY_TARGET=local`, `MENU_EXTRACTION_API_KEY=SET`
(currently = the MASTER Anthropic key, test-only). The key reaches the backend via an
explicit line in `docker-compose.yml` — the backend uses explicit `environment:` mappings,
NOT `env_file`, so a var not listed there never reaches the app.

## ⏭️ NEXT STEPS (do these to resume)
1. **Docker up + rebuild BOTH from HEAD `1cda1f9`.** The running server has NO volume mount,
   so a rebuild is REQUIRED to pick up committed code:
   `docker compose build backend frontend && docker compose up -d`.
2. **Confirm keys live** — one cheap OpenAI + Anthropic call each; confirm
   `MENU_EXTRACTION_API_KEY` SET (needed for the scanned-PDF vision path, else it reads
   "unavailable"); confirm `CODEGEN_MODE=real`, `DEPLOY_TARGET=local`.
3. **Arm a monitor on the MAIN backend container only** (avoids ephemeral test-container
   noise): `docker logs -f --tail 0 ai-org-backend-1 2>&1 | grep --line-buffered -iE '…'`.
   Match HTTP 5xx in the STATUS position (`HTTP/[0-9.]+" 5[0-9][0-9]`) NOT a bare `5\d\d`,
   or project ids like 5xx false-trip it. Include: traceback|exception|failed|smoke.?boot|
   boot_failed|did not start|escalat|no security certificate|missing from the running|
   live_url|deployed|collided|menu[_ ]|extract|upload|vision|Fernet|multipart|anthropic|
   response field|allowed_origins.
4. **Re-run the SAME idea at localhost:3000:** an **Italian restaurant named Bella Vista**
   (BA rendered it "bella veita"/"Bella Veita"); at the menu question choose **"Upload a
   PDF"**. Have TWO 1-page test PDFs ready: a **text-based** menu PDF (fast pypdf/pdfplumber
   path) and a **scanned/image-only** menu PDF (Claude vision fallback); optionally a
   corrupt file to test graceful failure.
5. **When it reaches a live URL**, arm a SECOND monitor on the DEPLOYED app's container
   (name derived from the project id) to watch the runtime extraction (text-extract →
   vision-fallback → pending-review gate) — the backend monitor can't see the deployed
   container.
6. Cost per full run ≈ **$2.6–4** (run 801 was $2.59 through QA); the Opus review is the
   variable line.

## 🧱 THE SMOKE-BOOT GATE (added this session, `7beaee1`; live + proven)
A FREE assemble+boot check (`main._smoke_boot`, reuses `qa.assembly.assemble` → `env.ok`,
NO LLM) runs right after the Developer agents and BEFORE the Opus security review. Only
code that actually STARTS (and exposes all designed endpoints) proceeds. A boot failure
sets build status `boot_failed`, records the FULL traceback in a new `smoke_boot` pipeline
stage (`4f2d017` — so you diagnose without re-running), and routes back to the Developer
stage. `_run_review` also HARD-GATES on the build having booted. **Why it exists:** three
consecutive live runs each paid for a full Opus security review (~$1–1.5+) on code that
then failed to boot at QA. The gate makes every boot failure a CHEAP catch + zero-re-run
diagnosis. The frontend shows an honest boot-failure message. Proven by
`test_smoke_boot_gate_offline.py` (a broken build NEVER reaches the reviewer).

## 🔧 THE 11 FIXES THIS SESSION (in commit order — what broke / root cause / fix / commit)
Driving the same restaurant build repeatedly, each run surfaced ONE blocker, each fixed
deterministically WITH a regression test. Several share a class: a dependency/symbol/env
value triggered by USAGE not by an import (so the AST scan misses it), a QA-environment
placeholder that isn't format-valid, or a GUESSED symbol/name.

1. **Menu dedupe** (`aef5349`) — run 461 didn't boot: FND-1 "table already defined". Cause:
   the LLM Architect schemas its OWN `menu_items` table AND `_menu_schema()` added a second.
   Fix: `builder._reconcile_menu_schema()` collapses any LLM `menu_items` into the single
   deterministic one (merging extra columns); `_ARCH_SYSTEM` forbids a menu table/route.
2. **email-validator** (`4a91170`) — run 487 booted-failed: `email-validator is not
   installed`. Cause: a Pydantic `EmailStr` needs the extra, triggered by field TYPE (no
   import names it) → scan missed it. Fix: `assembly.needs_email_validator()` → added to the
   QA venv (`_install_deps`) AND the deployed image (`manifest._backend_requirements`).
3. **Auth symbol contract** (`d45c24a`) — runs 435/513 booted-failed: `cannot import name
   'Auth0Config'/'verify_token' from backend.app.auth`. Cause: a backend file GUESSED a name
   auth.py never exported (it exports `get_current_user`/`get_current_admin_user`). Fix:
   `builder.AUTH_EXPORTS`; `agents._base_prompt` injects the exact auth-exports contract into
   every backend file's prompt (auth.py + frontend excluded), forbidding invented names.
4. **Smoke-boot gate** (`7beaee1`) — see the section above.
5. **response_model rule + traceback capture** (`4f2d017`) — runs 342/573 booted-failed:
   `Invalid args for response field` (a route used a SQLAlchemy ORM model as `response_model`).
   Fix: the Backend-Developer system prompt mandates `response_model` be a Pydantic schema
   (or `response_model=None`), never an ORM model. SAME commit: `_smoke_boot` now captures the
   full boot traceback into the `smoke_boot` stage.
6. **Fernet key** (`119d48c`) — run 606 booted-failed: `Fernet key must be 32 url-safe
   base64-encoded bytes`. Cause: the generated Stripe token store builds
   `Fernet(STRIPE_TOKEN_ENC_KEY)` at import, and QA's curated `_TEST_ENV` value was a raw
   32-CHAR string, not a valid Fernet key — a QA-ENVIRONMENT fault, not an app bug. Fix:
   `_TEST_ENV["STRIPE_TOKEN_ENC_KEY"]` is a real throwaway Fernet key; `_fake_env_value`
   hands a valid Fernet key for any discovered `*_ENC_KEY`/`*_FERNET` var.
7. **python-multipart** (`5a2142e`) — run 661 booted-failed: `Form data requires
   "python-multipart"`. Cause: the menu upload endpoint uses `UploadFile`/`File`/`Form`,
   which FastAPI needs `python-multipart` for — triggered by USAGE, not an import. Fix:
   `assembly.needs_python_multipart()` → QA venv + deployed requirements. (This was the menu
   upload code's OWN dependency — real progress into the feature.)
8. **Anthropic SDK / Claude** (`e4adba4`) — run 689 booted-failed: `cannot import name
   'Claude' from 'anthropic'`. Cause: the generated vision-extraction code hallucinated the
   client class; the real class is `Anthropic`. The MENU-3 ticket said "Anthropic Claude"
   loosely. Fix: MENU-3 pins the EXACT SDK usage (`from anthropic import Anthropic`,
   `client.messages.create(...)` with a base64 image block) and says there is NO `Claude`
   class. (This was INSIDE the extraction code — deep progress.)
9. **Menu review endpoints** (`04b8de3`) — run 718 BOOTED but 2 designed endpoints missing:
   `/admin/menu/pending`, `/admin/menu/confirm`. Cause: `POST /admin/menu/confirm` was
   ORPHANED — only the FRONTEND MENU-4 referenced it, so no backend ticket built it; `/pending`
   was only loosely mentioned. Fix: MENU-3 explicitly commissions BOTH review-flow endpoints
   as real routes; the test also guards that no backend menu endpoint is orphaned.
10. **ALLOWED_ORIGINS** (`edf9729`) — run 773 got past building, smoke-boot, AND the Opus
    security review, then failed QA (`environment_fault`): the app reads
    `os.getenv('ALLOWED_ORIGINS','').split(',')` and fail-fasts if empty (a CORS hardening the
    Opus review ADDS). Because it has a default, QA's discovery skips it. Fix: `_TEST_ENV`
    curates `ALLOWED_ORIGINS`/`CORS_ORIGINS` with a valid loopback origin list; the APP-1
    ticket pins the exact `ALLOWED_ORIGINS` name.
11. **FND-1 shared Base** (`1cda1f9`) — run 801 booted, passed security, 100/109
    QA passed; the 9 failures were `GET /menu` + `GET /reviews` → 500 "database error". Cause:
    `models.py` called its own `declarative_base()`, separate from `database.py`'s Base →
    models registered on a Base the engine never sees → `create_all` made NO tables. Fix:
    FND-1 pins `from backend.app.database import Base` and forbids a second `declarative_base()`.

## 🔧 FIXES #12 / #13 / #14 (2026-08-12 — the gate-integrity + first-deploy session)
12. **Pinned + deterministic smoke_boot/QA venv** — project 829 booted clean at smoke_boot,
    passed the paid Opus review, then fail-booted at QA on the SAME files. Root cause: the
    throwaway venv is `--system-site-packages` + installs missing deps UNPINNED, so it could
    boot under a different Pydantic than QA/deploy — a gate that green-lights un-bootable code.
    (The bug was in the single, original `order.py`; NOT a regeneration — proven from stored
    content + timestamps.) Fix: the platform's own tested `backend/requirements.txt` is now the
    SINGLE pin source consumed by BOTH the QA/smoke_boot venv and the deploy image.
    `assembly.PLATFORM_PINS` / `pin_spec()` / `platform_constraints_text()`; `_install_deps`
    writes a pip `--constraint` file so a platform package (Pydantic above all) can never drift
    while missing extras install, and pins each missing pkg via `pin_spec`. `manifest.
    _backend_requirements` pins every requirement from the SAME source. Both gate and QA go
    through the one `assembly.assemble`, so they are identical by construction. Proven by
    `test_venv_pinning_offline.py` (30 checks: identical deploy⇄gate pins, constraint carries no
    extras, and under the pinned Pydantic `conlist(min_items=1)` raises while `min_length` works)
    + an integration re-assemble of 829's real files (gate `env.ok=False`, venv pinned 2.10.4).
13. **Pydantic v2 prompt rule** — the 829 defect itself: `conlist(OrderItem, min_items=1)` is
    v1; v2 renamed it `min_length`/`max_length` and a v1 name is a hard import `TypeError`. The
    Backend-Developer system prompt (`developers/agents._system`) now mandates v2 names for
    `conlist`/`constr`/`Field`/`conset` and forbids `min_items`/`max_items`. Proven by
    `test_developers_offline.test_pydantic_v2_rule` (frontend prompt excluded).
14. **D4 force-dynamic via the ROOT SERVER layout** — project 860 was the FIRST run to fully
    pass QA (104 tests), then failed at the DEPLOY step: `next build` threw prerendering
    `/integrate`, a `"use client"` page using `useSearchParams()` without Suspense → the whole
    frontend image build fails. ⚠️ The originally-documented fix (inject `export const dynamic =
    "force-dynamic"` into the PAGE files) was DISPROVEN with a real `next build` on Next 15:
    route-segment config is IGNORED in client components, and the pages are all `"use client"`,
    so it does nothing. The working, real-build-proven fix: inject `export const dynamic =
    "force-dynamic"` into the ROOT SERVER `layout.tsx` (config there cascades to every route →
    whole app dynamic → no page is prerendered). `assembly.force_dynamic_layout(rel, content)`
    (skips: non-root-layout, a CLIENT root layout, and a layout that already sets `dynamic`),
    applied at BOTH build sites — the deploy `manifest` frontend write AND QA's `_write_files`
    (so QA's opt-in `next build` matches the deploy). Proven by `test_d4_force_dynamic_offline.py`
    (11 injection checks) + `test_d4_real_build.sh` (real `next build`: FAILS without the layout
    fix, SUCCEEDS with it, `/integrate` becomes `ƒ` dynamic — EXCLUDED from the free suite, needs
    Node+Docker like the live tests). Verified live against project 860's actual layout + page.

## ⚠️ KNOWN-OPEN / worth watching
- **D3-FAMILY: order.py imports a nonexistent `Item` symbol (project 829, LOGGED not yet fixed).**
  `routes/order.py` did `from backend.app.models import Order, Item`, but models.py exports
  `Order`/`StripeAccount`/`MenuItem` — no `Item` (the pydantic `OrderItem` is defined locally in
  order.py). This is the SAME wrong-symbol class as the D3 residual: a correct module path, a
  guessed NAME. It surfaces as a clean `ImportError` the gate now catches deterministically (it
  was the boot error in the 829 integration re-assemble). Real, separate defect worth fixing —
  candidate fixes: extend the binding-contract prompt to inject the exact models exports (like
  `AUTH_EXPORTS` does for auth), and/or a deterministic check that generated imports resolve to
  real exported symbols. NOT blocking the gate-integrity fix.
- **Residual LLM menu backend route colliding with MENU-1.** In run 606 the LLM generated its
  own backend menu route (`BE-1` → `routes/menu.py`) which collided with deterministic MENU-1
  (renamed `menu_menu_1.py`). Fix 1 (schema dedupe) means this no longer CRASHES — single
  `menu_items`, and the collision resolver + module-path pinning register MENU-1 from its
  renamed path — but the `_ARCH_SYSTEM` prompt tightening does NOT fully stop the LLM from
  emitting a menu backend route. NOT blocking (run 801 built `menu.py` as MENU-1's file
  cleanly). If it recurs, the clean fix is to deterministically drop/rename any LLM menu
  backend ticket so MENU-1 always owns `routes/menu.py`.
- **`MENU_EXTRACTION_API_KEY` = master Anthropic key (test-only).** Fine for local testing;
  MUST be swapped for a separate scoped/rate-limited key before any demo RECORDING so a
  deployed app never holds the platform master key. The scoped platform-key injection into
  deploys is built (`_has_menu_pdf` in devops/orchestrator); a per-owner key depends on the
  still-open Week-7 secrets-onboarding gap.
- **Menu extraction still UNPROVEN LIVE** — the app has never fully deployed, so the runtime
  text-extract → vision-fallback → pending-review flow has never actually run. That is the
  single remaining thing to prove.
- Carried from before: post-Week-8 **MODEL SWITCH** (own session), the secrets-table
  onboarding gap, a real AWS Cost Explorer shakeout.

**Offline suite count is now 13** (added `test_smoke_boot_gate_offline` +
`test_menu_onboarding_offline` + `test_venv_pinning_offline` + `test_d4_force_dynamic_offline`
to the original 9). All pass; run them all before any commit. The 9 "free" suites are still the
regression baseline. NOTE: `test_d4_real_build.sh` (D4 real `next build`) is EXCLUDED — it needs
Node + Docker, like `test_devops_local_live`; run it from the host when touching the D4 fix.

---

# MENU ONBOARDING — food/restaurant menu setup (manual OR PDF extraction) — BUILT, offline-proven (2026-08-08)

A real generated FEATURE for food businesses, built into the generated app the SAME
way as Stripe Connect (BA captures the choice → Architect commissions deterministic
tickets → Developer agents build it), NOT something the platform does itself. The
owner chooses to type menu items in OR upload a menu PDF and have items pulled out.

### The six agent changes (all offline-proven; no LLM/network/paid build)
- **BA** (`ba/understanding.py`, `ba/graph.py`, `ba/state.py`, `ba/controller.py`):
  `classify()` now returns **`is_food`** (restaurant/cafe/bar/etc., detected exactly
  like `is_local`/`customer_facing`). A new **`ASK_MENU`** stage (in `ORDER`, gated by
  `_should_skip` on `is_food`) asks the one plain-English question *"type in your menu
  items yourself, or upload a PDF…"*. The answer is parsed (`_parse_menu_setup` →
  `manual`/`pdf`), shown on the confirmation screen, carried in the summary
  (`is_food`+`menu_setup`), and captured as a **`user_stated` requirement** — same
  pattern as every other BA answer.
- **Architect** (`architect/builder.py`): deterministic `_menu_schema()` (a shared
  **`menu_items`** table with a `status` = `pending_review`|`published` and `source`),
  `_menu_endpoints()`, and `_menu_tickets(menu_setup)`. Gated in `build_blueprint` on
  `is_food` + `menu_setup`. **Manual** → MENU-1 (backend CRUD + public `GET /menu`) +
  MENU-2 (admin add/edit form). **PDF** → also MENU-3 (upload: text-first extraction,
  vision fallback via `MENU_EXTRACTION_API_KEY`, writes `pending_review`, file-size +
  content-type + filename-injection guards, graceful on corrupt PDFs) + MENU-4 (review/
  confirm screen — nothing publishes until the owner approves). The `_ARCH_SYSTEM`
  prompt now tells the LLM **not** to generate menu tickets (may still design a
  customer-facing menu DISPLAY page). One shared table + admin form is reused by both
  paths — the PDF review screen is that form pre-filled.
- **Code Reviewer** (`reviewer/reviewer.py`): `_is_menu_extraction()` flags MENU-3/4
  and `menu_upload`/`menu/review` files; the GENERAL review pass gets a
  `_MENU_EXTRACTION_FOCUS` checklist (malformed PDFs, oversized files, filename
  injection, never auto-publish). Ordinary menu CRUD (MENU-1) is deliberately NOT
  over-flagged.
- **QA** (`qa/level2.py`): new `_menu_pdf_extraction` probe (in the attack list) +
  `_text_pdf` fixture builder. Verifies a corrupt PDF fails gracefully (no 5xx crash)
  and extracted items are NEVER auto-published (sentinel absent from public `/menu`).
  Because `/admin/menu/upload` is owner-only, a real QA run without a token records an
  explicit **"login-gated, not exercised"** note (honest — never a false pass).
- **Documentation** (`documentation/datasource.py`, `documentation/generators.py`): a
  `menu` fact derived from REAL generated files (`built`/`is_pdf`); the user guide and
  handoff describe the feature accurately — for the PDF path they mention the review
  step and say the reading "isn't always perfect" (never overstate accuracy).
- **DevOps** (`config.py`, `devops/orchestrator.py`): `_has_menu_pdf()` gates a scoped
  injection of the platform-held **`MENU_EXTRACTION_API_KEY`** into deploys of apps
  that shipped MENU-3 — added before `guard()` so it's redacted from logs, and only
  when the setting is present (else it warns; the app reports scanned-menu reading as
  unavailable, never faked).

### Decisions (with rationale)
1. **Deterministic shared menu feature** (user chose) — one `menu_items` table + admin
   form generated deterministically, not left to the non-deterministic LLM (same
   reasoning as the binding-contract / Stripe fix). Confirmed first that NO
   deterministic menu ticket existed (menu tables/tickets were LLM-emergent and usually
   a customer-facing display, not an admin add-item form).
2. **Platform-provided vision extraction** (user chose) — a small restaurant owner
   won't have their own AI account (unlike Stripe, which owners expect to "connect").
   A **scoped, single-purpose** platform key (`menu_extraction_api_key`), deliberately
   separate from the master `anthropic_api_key`.
3. **Build + offline tests only** (user chose) — no paid end-to-end run this session.

### ⚠️ KNOWN GAP — vision extraction depends on the secrets-injection gap (Week 7)
Platform-provided vision extraction needs `MENU_EXTRACTION_API_KEY` to actually reach
the deployed app. The DevOps injection path is BUILT and offline-proven (the scoped
"minimal path" the user asked for, NOT the full owner-facing "connect your keys" UI —
that broader secrets-onboarding producer is still open since Week 7). To make scanned-
menu extraction usable on a real deploy: set `MENU_EXTRACTION_API_KEY` in the
platform's env. Until then, text-PDF and manual entry work; scanned/image menus read
as "unavailable" (honestly), never faked. **This is the temporary, scoped unblock —
the fuller secrets-onboarding UI remains the real fix.**

**⚠️ ACTION REQUIRED BEFORE THE REAL DEMO RECORDING (not before the local test run).**
For the 2026-08-09 local test run, `MENU_EXTRACTION_API_KEY` in `.env` was set to the
**master `ANTHROPIC_API_KEY` value** (and wired into the backend via
`docker-compose.yml`), so the deployed local app calls Claude with the master key.
That is acceptable ONLY for a local test on the owner's own machine. **Before the real
demo recording, replace it with a SEPARATE, scoped, rate-limited Anthropic key** (its
own budget cap) so a deployed app never holds the platform master key — this is exactly
why `menu_extraction_api_key` is a distinct setting from `anthropic_api_key`. Do NOT
record the demo until this swap is done.

### Verified (2026-08-08) — `test_menu_onboarding_offline.py`, 42 checks, 0 failures
Architect ticket emission (food+pdf → MENU-1..4 + schema + endpoints; food+manual →
MENU-1/2 only; non-food → none; LLM guard; unique filepaths; MENU-3 spec content); BA
parsing + `is_food` gating + summary capture; reviewer flagging (positive AND negative
cases); the QA probe run against a **correct** synthetic app (all checks pass) and a
**broken** one that crashes on a corrupt PDF / auto-publishes (probe correctly FAILS —
so it can fail for the reason it exists); documentation honesty; DevOps injection
gating. **All 9 free suites still pass — no regressions.** No paid run (see the ⚠️
above — the Developers' real menu code is unproven live).

---

# WEEK 10 PART 1 — Landing page & website polish — DONE (verified live in browser)

The public front door. A full marketing landing page now shows FIRST; the BA
conversation + build pipeline (Weeks 1-9) is reached by the "Start building" CTA.
Plus a simple, swappable CSS build-dashboard character. Frontend-only — no backend,
model, or agent changes.

### Every file created/modified this week, and why
NEW:
- `frontend/app/character.tsx` — `BuildCharacter` mascot (a friendly purple robot).
  Pose is ONE CSS class (`.mascot--thinking|typing|inspecting|launching|
  celebrating`); a `CAPTIONS` map gives each a plain-English line. Deliberately
  **CSS-only, not Lottie** (user's call: minimal + easy to iterate). Swapping a pose
  = editing the map + the matching `.mascot--x` rules; no animation runtime.

MODIFIED:
- `frontend/app/page.tsx` — the whole landing page (Sections 1-6) + wiring. New
  `view` state (`"landing" | "app"`); the landing is the default and mount NO LONGER
  auto-starts a BA conversation (`?dashboard=<id>` still jumps straight to the Week-9
  dashboard). New module consts `PLACEHOLDERS` / `BUCKETS` / `TRUST` / `FAQS`; a
  rotating-hero-placeholder effect; `startBuilding(idea)` (view→app, `start()`, then
  sends the typed idea as the FIRST BA message); `start()` now RETURNS the project id
  and `send()` takes a `pidOverride` (the id state hasn't flushed the instant after
  `start()`, so the first message would otherwise post with `project_id=null`). The
  `BuildCharacter` is rendered in the app view with pose derived from `pipeline`.
  Brand `PURPLE` constant changed **`#7c3aed` → `#534AB7`** (one constant → recolors
  landing + chat + build + dashboard). ~200 lines of landing styles added to `s`.
- `frontend/app/globals.css` — mascot CSS (all 5 poses + keyframes, eyes/arms/
  accessory per pose, a `prefers-reduced-motion` off-switch) and the FAQ native
  `<details>` accordion styles.
- `frontend/app/layout.tsx` — `<title>`/description set to the hero headline.

### The six sections (exact, per brief)
1. **Hero** — "Describe your idea. We'll build the app." + one input with the 3
   rotating placeholders + "Start building — it's free to try" + "No signup required
   to start." 2. **Social proof** (honest) — 15 / 9 / ✓ (see decision 1). 3. **Three
   buckets** — Just for me / My small team / My customers → **$19 Starter / $49
   Growth / $99 Business** (decision 2). 4. **Trust** — the exact five checkmarks.
   5. **FAQ** — six plain-English Q&As, no technical words. 6. **Bottom CTA** — the
   hero headline + input again, so the entry point is always in reach.

### Decisions made this session (with rationale)
1. **Honest social proof, no fabricated usage number** (user chose). Confirmed by
   querying `pipeline_status`: every row is a dev/test run, per-run wall-clock 0s to
   **52,275s (14.5h)**, "building" averages ~35min — so there is NO honest
   build-time stat to quote and nobody has used the product yet. The three stats are
   framing, not counts: "15 specialized AI agents" / "Built & verified across 9
   development phases" / "Security-reviewed by the most advanced AI available".
2. **LOCKED landing pricing $19/$49/$99 (Starter/Growth/Business)** came from the
   user's brief, used verbatim. ⚠️ These are NOT in CONTEXT.md — the ~$15/$50/$150
   figures elsewhere are the **DevOps server-sizing tiers** (quick/production/scale),
   a different concept. Do not conflate them.
3. **Character is CSS-only, not Lottie** (user: "keep it minimal and easy to iterate
   on later"). Pose ↔ stage: thinking (BA + Architect), typing (Developer),
   inspecting (Code Review + QA), launching (DevOps), celebrating (complete).
4. **Brand purple unified to #534AB7 everywhere** (user chose "everywhere" over
   "landing only") — a single shared constant, one consistent brand color.
5. **Landing is the default view; building starts on the CTA. No backend change** —
   `startBuilding` reuses `/conversation/start` + `/conversation/message`.

### Verified (2026-08-01) — what + how
- **⚠️ Frontend has NO volume mount** (`build: ./frontend` bakes source into the
  image), so `next dev` served STALE code after my edits — caught live in the browser
  (old chat auto-started, old purple, old title). Fix + the rule to remember:
  **frontend edits need `docker compose build frontend && docker compose up -d
  frontend`** (unlike backend *tests*, which mount source). After rebuild:
  `npx tsc --noEmit` clean; Next compiled with 0 errors.
- **Live browser check (localhost:3000):** all six sections render with the correct
  copy + pricing; `<title>` updated. All **five mascot poses render distinctly**
  (verified by injecting the mascot markup with each pose class — zero pipeline
  cost). The **live landing→build transition works**: typed "I want an app to manage
  my grocery store", clicked Start building, and it posted as the FIRST BA message
  with the thinking mascot + "Getting to know your idea…". **Mobile (375px) stacks**
  cleanly (hero, stats, buckets, trust all `flex-wrap`).
- **Cleanup:** deleted 2 throwaway test projects — **433** (conversation from the
  pre-rebuild stale auto-start) and **434** (the Start-building test) — both
  conversation-only (0 deployments, 0 pipeline_status rows), so neither could read as
  a monitoring/cost target.

### Carried forward / known-open (Week 10 Part 1)
- **Week 10 Part 2 = the real demo run** (next; real spend).
- Frontend runs on local `next dev` at :3000; it is **not deployed**. Visual QA was
  spot-checked at desktop + 375px only.
- FAQ answer #2 quotes "$19 a month" as the entry price — keep it in sync if the
  locked plan pricing ever changes.
- Unchanged from Week 9: MODEL SWITCH pending; secrets-table onboarding + real AWS
  Cost Explorer still open.

## HOW TO RUN (zero-context)
- Start everything: `docker compose up -d` (postgres, redis, backend:8000,
  frontend:3000). Backend runs `alembic upgrade head` on start; DB is at migration
  **`0013`**.
- Run a test / any backend script with the LIVE source mounted (so edits are seen
  without a rebuild):
  `docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" backend python tests/<name>.py`
- **The 9 free regression suites** (all must print `RESULT: ALL CHECKS PASSED ✓`,
  check the exit code too): `test_qa_offline`, `test_architect_offline`,
  `test_qa_retry_loop`, `test_qa_teardown`, `test_token_instrumentation`,
  `test_developers_offline`, `test_devops_offline`, `test_documentation_offline`,
  `test_background_offline`. (`test_qa_classification` is excluded — real Gemini.)
- After editing backend code that the RUNNING server must serve (endpoints, agents
  invoked via the API), rebuild: `docker compose build backend && docker compose up
  -d backend`. Same for `frontend`. Tests don't need a rebuild (source is mounted).
- `.env` holds real API keys + `SECRETS_ENC_KEY` + AWS/DevOps vars; it is
  gitignored. `~/.aws` + the docker socket are mounted into the backend for the
  DevOps/AWS paths.

## WEEK 9 — Background agents (#13/#14/#15) — DONE (local/synthetic proof)

Three post-launch agents that run silently after deployment; the user sees them
only via the dashboard. Deterministic-first and honest — metrics/costs come from
stored data, and a missing source reads as "not available yet", never fabricated.
All code is under `app/background/`.

### Every file created/modified this week, and why
NEW:
- `backend/app/background/__init__.py` — package doc for the three agents.
- `backend/app/background/monitor.py` (#13) — `check_once` (one HTTP probe →
  is_healthy/response_time_ms/error_code), `check_and_record` (probe the latest
  LIVE deployment, else return None), `monitor_loop` (bounded cadence loop),
  `weekly_summary` (aggregate real logs → plain English via Gemini + deterministic
  fallback → stored as a `weekly_report` document). `monitor_url()` maps a local
  `localhost:<port>` live_url to `host.docker.internal` so the in-container probe
  reaches the host-published port (the Week-7 probe lesson).
- `backend/app/background/autofix.py` (#14) — `handle(project_id, problem)`:
  `_snapshot` (Safe Mode, before any fix) → `health.classify` → Level 1 restart
  via the REUSED DevOps `driver.restart` → re-check → silent (L1) / notify (L2) /
  escalate+`_escalate` (L3) / rollback-if-worse. `_LEVEL3_INSTRUCTIONS` = per-fault
  plain-English steps.
- `backend/app/background/cost_tracker.py` (#15) — `project_month_end` (straight
  line), `record` (store actual+projected+budget+over_budget), `poll` (gated real
  CE), `_ce_actual_month_to_date` (real boto3 Cost Explorer, GATED), `summary`
  (dashboard cost picture). `_MIN_PROJECTION_DAYS=3` guard (see decisions).
- `backend/app/background/dashboard.py` — `build(project_id)` aggregates the 4
  dashboard sections read-only from deployment / cost_logs / monitoring_logs /
  user_issues.
- `backend/alembic/versions/0013_background_agents.py` — creates
  `monitoring_logs`, `deployment_snapshots`, `fix_logs`, `user_issues`, `cost_logs`.
- `backend/tests/test_background_offline.py` — the 32-check offline proof (below).

MODIFIED:
- `backend/app/models.py` — 5 new models (MonitoringLog, DeploymentSnapshot,
  FixLog, UserIssue, CostLog) + their `Project` relationships. Columns match the
  spec + honesty fields (fix_logs.level/outcome/notified/notification, cost_logs.
  over_budget, snapshots.state_json).
- `backend/app/config.py` — W9 settings: `monitoring_model`=gemini-2.5-flash-lite,
  `autofix_model`=gpt-4o, `cost_tracker_model`=gemini-2.5-flash-lite,
  `monitoring_interval_seconds`=60, `monitoring_request_timeout`=10,
  `autofix_notify_downtime_seconds`=120, `cost_budget_alert_ratio`=1.20,
  `aws_cost_explorer_enabled`=False (gated).
- `backend/app/main.py` — imports the 3 agents; `_run_monitor` background
  supervisor (edge-triggered: on a NEW failure, and only if no open user_issue,
  call `autofix.handle`); auto-starts monitoring after a `live` deploy; endpoints
  `POST /pipeline/monitor`, `POST /pipeline/cost-check`, `POST /pipeline/weekly-
  summary`, `GET /dashboard/{id}`.
- `backend/app/schemas.py` — `CostCheckRequest`, `DashboardResponse`.
- `frontend/app/page.tsx` — post-launch dashboard view rendered at
  `?dashboard=<projectId>` (fetches `/dashboard/{id}`): 4 sections + "Make a change
  to my app" button → `makeAChange()` starts a fresh BA conversation. Input form
  hidden in dashboard mode. New styles `dashRow/dashLabel/dashVal`.
- `CONTEXT.md` — this record.

### Decisions made this session (with rationale)
1. **Local/synthetic testing, no live AWS spend** (user chose). Real AWS Cost
   Explorer + AWS-driver restart are written as gated, off-by-default code.
   Rationale: auto-fix reuses the already-proven Week-7 restart primitive, and CE
   data lags 24-48h so a real call would teach little for the money — unlike the
   Week-7 DevOps shakeout where the infra was genuinely untested.
2. **Orphan cleanup before building** — a stale project `358` (and later demo
   projects) with a fake `live` deployment row were deleted first, so nothing fake
   read as a monitoring/cost target.
3. **Auto-fix reuses the Week-7 `driver.restart` primitive** (not a second restart
   path). It builds a minimal `DeployRequest` and calls
   `devops.orchestrator._get_driver(dep.target).restart(req)`. Structurally can't
   touch code/security. The three Level-1 remedies (not responding / memory / DB
   dropped) are all one restart (a container restart re-establishes the pool +
   clears memory).
4. **No fabricated "actions completed" count** — the spec's example weekly summary
   says "143 actions completed", but monitoring only pings; it does not observe
   app-level actions. The summary reports uptime / checks / response time / real
   downtime instead, and only claims "we fixed it" when a `fix_log` exists.
5. **Cost projection guard** (`_MIN_PROJECTION_DAYS=3`) — caught during the live
   demo: $4.10 spent on day 1 straight-lined to ~$127 and fired a FALSE over-budget
   alarm. Below 3 elapsed days we now don't project or alert; the dashboard says
   "still early in the month". Committed as follow-up `3f7e726`.
6. **Routing stays current** (Gemini monitoring/cost, GPT-4o auto-fix); the
   post-Week-8 model switch is deliberately a separate session.

### Verified (2026-08-01) — what + how
- **`test_background_offline.py` — 32 checks, 0 failures** (no AWS, no LLM spend;
  `codegen.generate` patched, a real threaded `http.server` for monitoring):
  Monitoring proven with REAL HTTP round-trips (200 healthy; 404/500 captured with
  code; dead port unhealthy with message; no live deployment → honest None). Every
  auto-fix branch: L1 silent heal (restart called once, snapshot taken BEFORE the
  fix), L2 long-downtime notify, L3 app-error escalate (restart NOT attempted) +
  user_issue created, L3 restart-didn't-help → rolled_back (restart called twice).
  Read-only proven: `generated_files`/`code_reviews` counts unchanged after
  auto-fix. Cost projection ($6 by day 10/30 → $18), +20% alert, day-1 guard, and
  no-budget honesty. Weekly summary uses real uptime + no "actions" word + no
  false "fixed" claim; empty project → honest "not a full week yet". Dashboard
  aggregation live vs not_live.
- **Dashboard verified LIVE in the browser** at `?dashboard=<id>` against a seeded
  project (App status Live ✓, $4.10 → projected $12.71 vs $15 on track ✓, 99%
  uptime / 118ms / 2 errors, "Make a change" button). Demo data cleaned up
  afterward; working tree left clean; backend rebuilt to match committed code.
- **All 9 free suites pass; no regressions** from the models/config/main/schemas
  changes.

### Carried forward / known-open
- The `secrets` table still has NO onboarding producer, so integrations honestly
  read "designed, not yet connected" (since Week 7).
- Real AWS Cost Explorer poll is unrun (gated), like the AWS deploy driver was
  before its shakeout. To enable: set `aws_cost_explorer_enabled=True`, a tagged
  AWS deployment must exist, then `cost_tracker.poll(project_id)` (or the daily
  cron in prod).
- Blueprint `llm_routing` doesn't list monitoring/cost/auto-fix and its
  `documentation` entry is a stale `gpt-4o-mini`; cosmetic (agents use
  `settings.*_model`); tidy during the model-switch session.
- Monitoring runs as an in-process asyncio task started after deploy; it does NOT
  survive a backend restart (fine for this project — nothing stays deployed long).
  A durable scheduler is future work if apps become long-lived.

---

# (Week 8 record below — also closed)

## WEEK 8 — Documentation Agent (#12) — DONE (read-only; honest on real data)

Generates four documents into a new `documents` table from REAL stored data only.
Strictly READ-ONLY over the rest of the system (reads tables + Redis, writes only
`documents`); never fabricates a number or status — a missing source reads as
"not available yet". Routes to **Gemini 2.5 Flash-Lite @0.5** via
`codegen.generate` (locked through Week 8; `claude-haiku-4-5` is the post-Week-8
switch, NOT applied yet).

### The honesty is structural
- ONE `documentation/datasource.gather()` decides "what is true" from stored data
  (deployment / Redis cert + code_reviews / qa_results / blueprint ∩
  generated_files / secrets). Every generator reads only from it.
- Integrations are "connected" ONLY when a real secret row backs them; Stripe is
  never claimed live (it connects in-app after launch).
- The Handoff summary uses NO LLM — every field is real data — and carries
  `honest_notes` surfacing partial/known-open state (not deployed, tests failed,
  no cert, Stripe not connected).
- Demo script steps are one-per-REAL-screen (from generated files); the LLM only
  phrases narration, so it can never script a screen that doesn't exist.

### Outputs + surface
`documents` (id, project_id, doc_type, content, created_at): user_guide (md),
demo_script (json), maintenance_guide (md), handoff_summary (json). Plus
`POST /pipeline/document`, `GET /pipeline/{id}/documents-status`, `/documents`,
and the frontend FINAL completion table (live link, security, tests passed, user
guide ready, demo script ready, monthly cost — no technical words).

### Verification (2026-07-31)
- **`test_documentation_offline.py` — 30 checks, 0 failures** (free; LLM patched):
  honest reporting on REAL project 342 (not deployed, 2 of 8 tests failed, no cert
  — the handoff says exactly that); READ-ONLY proven (every other table's row
  count unchanged); real-screens-only (no Stripe screen unless present); honest
  missing-data (support = no invented contact, leans on free code-export / no
  lock-in).
- **Real Gemini run** confirmed genuine plain-English output — and caught a
  jargon-in-headings issue (guide headings echoed ticket titles like "Implement
  menu retrieval endpoint"); fixed by forcing plain headings and re-verified.
- **Completion screen verified live in the browser** (seeded green project, since
  cleaned up).
- All 8 free suites pass (6 prior + DevOps + Documentation); no regressions.
- Committed **`c7cb94e`** (no Co-Authored-By; `.env` untouched). New:
  `app/documentation/` (datasource, generators, orchestrator, graph), Document
  model + migration `0012`, `test_documentation_offline.py`.

### Carried forward
- Still no onboarding stage populates the `secrets` table with real user secrets,
  so integrations honestly read "designed, not yet connected" (gap since Week 7).
- `builder._llm_routing()` still lists a stale `documentation: gpt-4o-mini` (same
  shape QA's stale entry had); the agent uses `settings.documentation_model`
  (Gemini) directly so it is cosmetic — correct it in the post-Week-8 model switch.

---

# (Week 7 record below — also closed)

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
LIVE, independently from the host:** `https://shakeout-3c155f.apps.example.com`
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
removed. The `apps.example.com` hosted zone (`Z0XXXXXXXXXXXXXXXXXX`) is KEPT.
Nothing paid is left running.

**To run a live AWS deploy again** (all shakeout infra was torn down, so it must
be recreated — logged as a known gap below):
1. DNS is already delegated (zone `Z0XXXXXXXXXXXXXXXXXX`, NS at Namecheap).
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
- **Flaky SSG prerender (D4)** (runs 274 fail / 283 pass / 342 fail on `/integrate`;
  project 860 fail at deploy). `next build` compiles, then THROWS prerendering
  `/integrate` — a `"use client"` page calling `useSearchParams()` without a Suspense
  boundary — which fails the whole frontend image build. **RESOLVED 2026-08-12 by
  fix #14 (see the fixes section).** ⚠️ The fix originally proposed HERE — inject
  `export const dynamic = "force-dynamic"` into the PAGE files — was **DISPROVEN with
  a real `next build` on Next 15**: route-segment config is IGNORED in Client
  Components, and every generated `page.tsx` is `"use client"`, so the page-level
  export does NOTHING and the build still fails. **Do NOT re-introduce the page-level
  approach.** The mechanism that actually works (real-build proven) is exporting
  `dynamic = "force-dynamic"` from the ROOT SERVER `layout.tsx`, whose config cascades
  to every route — see fix #14.
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
- **D4 — frontend prerender runtime error (SEPARATE family).** With globals.css
  fixed, `next build` compiled and static-generated, but prerendering one page threw
  during SSG export. **RESOLVED 2026-08-12 by fix #14** — force the app dynamic via
  the ROOT SERVER `layout.tsx` (NOT the pages: page-level force-dynamic was disproven
  on Next 15, see the fixes section + the Week-6 D4 note).

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


## 1v. RUN 1614 DEPLOY CASCADE + FIX #31 (provider env-var contracts + missing-module gate) (2026-08-20)
Pushing 1614 to a live URL: frontend BUILT (Fix #30 held - lodash.debounce auto-added; page.tsx regenerated
clean after a first over-correction that imported a non-existent .module.css). Backend then fail-fasted in the
DEPLOYED stack (QA's throwaway _TEST_ENV had masked it) on PROVIDER ENV-VAR NAME mismatches + a missing module:
- AUTH0_AUDIENCE (code) vs API_AUDIENCE (provisioner); STRIPE_CLIENT_SECRET vs STRIPE_SECRET_KEY;
  STRIPE_STATE_SECRET not generated. FIX A: auth0_provision injects the audience under BOTH names
  (AUDIENCE_ALIASES); provisioning.platform_provided also injects the Stripe secret as STRIPE_CLIENT_SECRET;
  ensure_crypto_keys mints STRIPE_STATE_SECRET; backend prompt rule pins the exact provider var names.
- order.py `from backend.app.catalog import ...` but catalog.py NEVER generated -> boot fail (#16 gap: it
  skipped modules-not-in-set as third-party). FIX B: import_symbol_mismatches now flags an in-project-SHAPED
  module (shares a generated module's 2-seg prefix) that was never generated; third-party still skipped
  (zero-FP); repair says the module doesn't exist. Verified live on 1614's catalog import.
- All 15 offline suites pass. Committed a830c94 LOCALLY.
- BLOCKER (environment, not code): mid-session macOS revoked this shell's access to `~/Documents/Portfolio
  Projects` ('Operation not permitted'). Fix #31 was applied+tested+committed via the Docker daemon (which kept
  access), but the commit is NOT PUSHED (GitHub creds in macOS Keychain, unreachable from a container) and the
  backend image is NOT REBUILT. TO FINISH: grant the terminal/Claude app Full Disk Access (System Settings ->
  Privacy & Security), RESTART it, then `git push origin master` + `docker compose build backend && docker
  compose up -d backend`. 1614 is NOT live: after rebuild, redeploy it (its per-project secret patches
  AUTH0_AUDIENCE/STRIPE_CLIENT_SECRET/STRIPE_STATE_SECRET are already in its store) + it still needs a catalog.py.

## 1w. 🏆🏆 RUN 1614 IS LIVE — first fresh full-scope gen to a genuinely working deployed app (2026-08-20)
File access restored → pushed Fix #31 (`a717139`) + rebuilt backend (Fix #31 live). Then finished 1614:
- **Fixed the missing module:** regenerated `order.py` via the developer agent with Fix #31's missing-module
  repair → no more `backend.app.catalog` import, endpoints intact. Re-`_recertify`'d the drift (passed).
- **Cleared the remaining provider-name fail-fasts** (scanned ALL of 1614's fail-fast env vars at once):
  `STRIPE_API_KEY` (a THIRD Stripe-secret spelling, order_be_3.py) + `STRIPE_CONNECTED_ACCOUNT_ID` (the BA
  connect was scripted-skipped) → added to 1614's secrets_store (placeholder acct id; validated at request
  time, not boot). ALLOWED_ORIGINS is driver-set (not a gap).
- **Redeploy → `status: live`, `https://localhost:54473`, health_attempts:2.** Verified serving:
  backend `:8000/openapi.json`→200, frontend `:3000/`→200, and `GET /admin/stripe/connect`→**401** (auth gate
  returns a proper 401, NOT a 500 — Fix #24 holding LIVE). Full stack up: caddy+frontend+backend+db+redis.
  Onboarding provisioning all fired at deploy: Auth0 auto-provisioned, crypto minted, Stripe/SMTP injected.
- **DURABLE amendment (part of Fix #31):** `provisioning._PLATFORM_HELD` now injects the Stripe secret under
  ALL spellings STRIPE_SECRET_KEY/STRIPE_CLIENT_SECRET/**STRIPE_API_KEY** so future runs don't hit this
  whack-a-mole. Devops + onboarding suites pass.
- **⭐ THE MILESTONE:** first fresh full-scope generation (BA→Architect→Build→smoke_boot→**real Opus PASS**→
  **QA 100/100 clean**→**deploy LIVE**) to produce a real, security-certified, serving app — with the entire
  owner-onboarding stack (Stripe connect flow, Auth0 auto-provision, email) provisioned live at deploy.
- **⚠️ Remaining honest edges (not blockers to the live app):** (a) ~~STRIPE_CONNECTED_ACCOUNT_ID fail-fast~~
  CORRECTED 2026-08-21: 1614's `order_be_3.py` actually GUARDS it (`if STRIPE_CONNECTED_ACCOUNT_ID:`) — NOT a
  boot fail-fast; the real boot blocker was `STRIPE_API_KEY` (Fix #31 alias). The placeholder I added to 1614's
  store was unnecessary. No STRIPE_CONNECTED gate needed (no real bug); this edge was an overclaim, retracted.
  (b) the Caddy edge probe from a sibling container returns 000 (internal SNI/cert for the container name) —
  the platform's own health gate + host-port URL work, so cosmetic; (c) the provider-name variance is now
  absorbed by aliases, but pinning ONE canonical name in codegen would be cleaner long-term.

## 1x. FIX #32 — frontend LOGIN completeness (the run-1614 "live but unusable" gap) (DONE 2026-08-20)
User opened 1614's live app and hit "Not authenticated" 401 on every gated action. HONEST diagnosis: the
app IS live + serving (public `/menu`→200, homepage + pages render, auth gate returns proper 401s — Fix #24
holds), the onboarding wiring reached the frontend (`NEXT_PUBLIC_AUTH0_*` injected), BUT the **generated
frontend implemented NO login flow** — no Auth0 sign-in, no `/callback`, no token attached — so a user can
never authenticate and every protected feature is a dead 401. AUTH-1 only wires the BACKEND to VALIDATE
tokens; nothing made the FRONTEND obtain one. My earlier "🏆 works end-to-end" was right about infra/serving
and WRONG about usability — I verified 200s + 401s but never that a person can log in. The honest 1105 lesson
repeating: "tiers respond, but not usable end-to-end." **FIX #32 (`d6d9f68`):**
- **Architect FND-7 ticket** (`_frontend_auth_ticket`) commissions `frontend/app/providers.tsx` — Auth0Provider
  from `NEXT_PUBLIC_AUTH0_*`, Login/Logout (`loginWithRedirect`), an `apiFetch` that attaches
  `Authorization: Bearer`, and the root layout wraps children in it. Commissioned for any web frontend
  (auth is mandatory every build), like FND-6.
- **`agents.frontend_missing_login`** — deterministic WHOLE-APP gate: backend gates endpoints
  (`Depends(get_current_*)`) + a web frontend exists + NO frontend login evidence (Auth0 SDK OR Bearer token;
  Stripe's `/authorize` deliberately does NOT count) → flag. Wired into `_collect_stubs`, attributed to the
  FND-7 providers ticket for regen.
- **Frontend prompt rule:** you MUST implement login (not just read the vars).
- Tests: `test_developers_offline.test_frontend_missing_login_gate` + `test_architect_offline` asserts FND-7.
  All 15 offline suites pass. Backend rebuilt.
- **⚠️ 1614's existing frontend predates Fix #32** — it has no login and won't get one without regen. A FRESH
  full run now commissions FND-7 + the gate catches a missing login. **Frontend auth quality (does the
  generated login actually WORK across layout+pages) is still LLM-dependent** — FND-7 + the prompt give the
  mandate, the gate catches TOTAL absence, but a partially-wired login isn't deterministically verifiable
  without Node/a browser. That is the honest remaining frontier.

## 1y. FIX #33 — duplicate-endpoint gate (run-1614 "Duplicate Operation ID") (DONE 2026-08-21)
Grounded in 1614's LIVE deploy warning: the order feature was over-split into `order.py` AND `orders.py`,
BOTH defining `POST /orders`. main.py includes both routers → FastAPI registers the path twice
("Duplicate Operation ID create_order_orders_post") and one handler silently SHADOWS the other — which one
actually runs is router-include order (a coin flip). Real correctness risk, not cosmetic.
- **`agents.duplicate_endpoints(files)`** — deterministic WHOLE-APP detector: extracts every `(METHOD, PATH)`
  from `@router.<m>('<p>')` (with any `APIRouter(prefix=...)` prepended, path-params normalised `{x}`→`{}`)
  across backend route files; flags a `(method, path)` defined in ≥2 files. Zero-FP: a single-owner path is
  never flagged.
- **Wired into `_collect_stubs`** (whole-app, like the login gate): attributes each duplicate to the THINNER
  file (fewer total routes = the redundant one), keeping the fuller implementation; sets
  `duplicate_endpoint_repairs` → `repair_instructions` renders a DUPLICATE_ENDPOINT ticket ("remove this route,
  it's kept in <other file>") → the bounded build retry regenerates the thinner file without the dup.
- Tests: `test_developers_offline.test_duplicate_endpoint_gate` (real POST /orders dup flagged, single-owner
  not flagged, param normalisation, APIRouter-prefix path, thinner-file attribution, repair text, zero-FP).
  All 15 offline suites pass. Backend rebuilt.
- NOTE: the deeper cause is the ARCHITECT over-splitting one resource into two route files; this gate catches
  the collision post-hoc + self-heals. Verified live: flags 1614's real `POST /orders` duplicate.

## 1z. FIX #34 — frontend login QUALITY gate: BOTH halves required (the run-1614 frontier) (DONE 2026-08-23)
The honest #1 frontier from the Monday next-steps: Fix #32's `frontend_missing_login` only caught TOTAL
absence (login button + provider + token all missing). A PARTIALLY-wired login — the LLM's realistic failure
mode — sailed through: e.g. an `<Auth0Provider>` wrap but no call site attaches the token (user signs in yet
every fetch is still an anonymous 401), or a `Authorization: Bearer` attach with no provider (the SDK hooks
throw at runtime, login is dead). **FIX #34** upgrades the gate to require BOTH halves deterministically.
- **`agents.frontend_missing_login`** now checks two independent signals across the web frontend:
  (a) `_PROVIDER_WRAP_RE` = the app is wrapped in `<Auth0Provider>` (SDK context exists), AND
  (b) `_TOKEN_ATTACH_RE` = a call site acquires+attaches a token (`getAccessTokenSilently` OR
  `Authorization: Bearer …`). Only BOTH present → pass. Emits a TAILORED reason for each gap (total absence /
  provider-but-no-token / token-but-no-provider), all pointing to the FND-7 providers ticket for regen.
- Still deterministic, no Node/browser. Whole-app gate wired via `_collect_stubs` → FND-7 (unchanged path).
- Tests: `test_frontend_missing_login_gate` extended — provider-only flagged, token-only flagged, BOTH-halves
  (two files or one file) NOT flagged. All offline dev-suite checks pass. Backend rebuilt + verified live in
  `ai-org-backend-1` (provider-only → flagged, both → None).
- HONEST LIMIT: this raises the deterministic bar (a login button with no working wiring is now caught) but a
  provider that wraps the WRONG subtree, or a token attached to only SOME protected calls, is still not
  provable without executing the app. A fresh measurement run (~$3, ask first) remains the way to confirm a
  generated login actually works end-to-end.

## 1aa. FIX #35 — Architect-level duplicate-route CURE (prevents the run-1614 split at the source) (DONE 2026-08-23)
Fix #33 (§1y) was the post-hoc GATE: it catches a `(method, path)` defined in two route files after codegen
and self-heals. The DEEPER cause (noted in §1y) is the ARCHITECT over-splitting ONE resource into two sprint
tickets whose derived route files differ only by singular/plural (`order.py` + `orders.py`), both generating
`POST /orders`. **FIX #35** cures it at the source so the split never happens.
- **`builder._merge_duplicate_route_tickets(tickets)`** — runs in `build_blueprint` right BEFORE the entrypoint
  ticket is built. Groups DERIVED backend route tickets (`_is_derived_route_ticket`: assigned_to backend, NO
  explicit filepath, no path named in text — so foundation/auth/security/payment/menu tickets that pin a path
  are NEVER touched) by canonical resource = `_singular(_conventional_stem(title))`. Two tickets on the same
  key → fold the later into the first (append its work to the description, union dependencies, record
  `merged_ticket_ids`), so ONE Developer owns the whole resource in ONE route file. Dependency edges pointing
  at a folded ticket are rewritten to the survivor so no wave edge dangles.
- **`builder._singular`** — crude, consistent singularisation (only ever compared to itself): `orders`==`order`,
  `categories`->`category`; non-plural `-s` endings (`status`, `analysis`, `bonus`, `ss`) left alone.
- Runs BEFORE the entrypoint append so a folded id never leaks into the entrypoint's dependency list.
- Tests: `test_architect_offline.test_merge_duplicate_route_tickets` (plural sibling folded, pinned-path ticket
  untouched, different resource not merged, dependency rewrite, singularisation). All architect + developer
  offline suites pass. Backend rebuilt + verified live. Fix #33's gate stays as the post-hoc backstop.

## 1bb. FIX #36 — Fix #33 FALSE POSITIVE: only route MODULES own routes (measurement run 1843) (DONE 2026-08-24)
**Grounded in a REAL paid measurement run (project 1843, coffee-shop w/ ordering+Stripe+login).** The run
went BA → PI → Architect (18 tickets) → Build 18/18 files → **build ERROR**. Root cause diagnosed:
- The Architect commissioned SEC-1 → `backend/app/security.py` (a security HELPER, NOT a route module). The LLM
  put an ILLUSTRATIVE `@app.post("/orders", dependencies=[Depends(get_current_user)])` in it as an example of
  gating an endpoint. `duplicate_endpoints`'s file guard only skipped NON-`.py` files, so this non-route `.py`
  fell through and got scanned → it invented a phantom `POST /orders` "duplicate" between security.py and the
  REAL `order.py`, attributed the removal to order.py, and the bounded retry regenerated order.py WITHOUT its
  route → BE-1 produced a stub → "1 of 18 tickets produced no code" → build not certifiable → ERROR.
- **Fix:** `duplicate_endpoints` now `continue`s for any `.py` that is NOT under `routes/` and not `main.py`, so
  only real route modules can own routes. Regression test `test_duplicate_endpoint_gate` extended with the exact
  1843 scenario (illustrative endpoint in security.py → NOT a duplicate; genuine order.py+orders.py → still
  caught). All offline dev-suite checks pass. Backend rebuilt + verified live (phantom → `[]`, real dup → 1).
- **WHAT 1843 VALIDATED (the wins):** ✅ **Fix #35 confirmed live** — the order resource stayed in a SINGLE
  `order.py` (no order.py+orders.py split). ✅ FND-7 `providers.tsx` + a login flow WERE generated (Fix #34's
  mandate held) — but end-to-end login could NOT be measured because the build errored first.
- **⏭️ NEXT:** the build-error CAUSE is fixed. Rather than pay for a fresh run, we measured 1843's login the
  CHEAP way (see §1cc). Project 1843 left in DB.

## 1cc. FIX #37 — frontend Auth0 audience alias + the CHEAP measurement method (deploy of run 1843) (DONE 2026-08-24)
**Cost lesson (user asked "is there a cheaper way than a fresh $3 run every time?"): YES.** Two $0/near-$0 tools
replace most paid runs:
- **$0 — offline gate replay:** every deterministic fix (#16–#37) is a gate with no LLM. Load a run's stored
  `generated_files` and run the gate. Confirmed Fix #36 live against 1843's REAL files (phantom dup → `[]`).
  Also fixturized 1843 (`security_illustrative_endpoint_1843.py` + `order_route_1843.py`) as a permanent free
  regression.
- **near-$0 — deploy the EXISTING generated files** (no codegen): mint the debug skip-cert
  (`reviewer.skipped_certificate`, no LLM) into `security_cert:<pid>`, then POST `/pipeline/deploy`. Deploy is
  docker build + run only. Run 1843 went LIVE at a local `https://localhost:<port>` for $0. (The build-status
  gate on `/pipeline/secure` needs a passing build, so mint the cert directly — a supported local-debug path.)
  NOTE: re-running `/pipeline/build` is NOT cheap — `orchestrator.run` regenerates ALL tickets (~$1 + variance +
  duplicate DB rows); only use it to test codegen/prompt changes, never to "redeploy existing files".

**WHAT THE 1843 DEPLOY MEASURED (Fix #34's honest #1 frontier — the generated login):**
- ✅ **Login CODE is genuinely good** (verified by READING the real files): `layout.tsx` wraps the app in
  `<Providers>` → `<Auth0Provider>`; `providers.tsx` has a real `loginWithRedirect` Login/Logout UI + a
  `useApi()` helper that fetches the token via `getAccessTokenSilently` and attaches `Authorization: Bearer`.
  Wiring is COHERENT vs the backend gating: gated pages (admin/menu, settings) attach the token; public pages
  (menu GET /menu, order POST /orders — both ungated in the generated backend) correctly do not.
- 🐞 **A REAL deploy-only bug the code-read could NOT catch → FIX #37:** at deploy the frontend
  `NEXT_PUBLIC_AUTH0_AUDIENCE` was EMPTY while the backend had `AUTH0_AUDIENCE` set. `manifest.frontend_public_env`
  mapped the frontend audience ONLY from `API_AUDIENCE`, but 1843 stored it under `AUTH0_AUDIENCE` (Fix #31's two
  spellings). → the SPA requested a token with NO audience → every gated API call would 401 AFTER a successful
  login (login built but not usable e2e — the exact 1105/1614 "responds but not usable" pattern, one layer up).
  **Fix:** `FRONTEND_AUTH0_FROM_BACKEND` maps the audience from EITHER alias (API_AUDIENCE, then AUTH0_AUDIENCE);
  `frontend_public_env` tries each. Regression in `test_devops_offline`. Backend rebuilt; 1843 REDEPLOYED and the
  frontend env now carries `NEXT_PUBLIC_AUTH0_AUDIENCE=https://…` (was empty). All devops offline checks pass.
- **Minor tail (not a bug):** gated pages hand-roll `Authorization: Bearer` via `useAuth0` instead of reusing the
  shared `useApi()` helper. Cosmetic consistency only.
- **Could NOT get a browser click-through:** the sandbox browser refuses self-signed localhost HTTPS, and an
  ephemeral-port local deploy's callback URL isn't registered in the hosted Auth0 tenant (would be a callback
  mismatch) — both ENVIRONMENT limits, not app bugs. The config-level verification above is the honest result.
- The 1843 ephemeral deploy stack (`aiorg_p1843_*`) is a LOCAL docker stack (no cloud cost). Tear down with
  `docker rm -f $(docker ps -aq --filter name=aiorg_p1843_)` when done poking at it.

## 1dd. FIX #38 — themed design-system globals.css + local playability of 1843 (2026-08-24)
User opened the LIVE 1843 app and gave two pieces of real feedback: (1) "plain website, no animations", (2)
"I want to add items and manage the menu".
- **FIX #38 (the platform fix for #1 — committed):** the FND-5 globals.css ticket MANDATED "minimal, plain CSS",
  so every generated app looked bare, and the BA-captured `design.brand_color` / `style_vibe` NEVER reached
  codegen. Now `builder._design_system_css(summary)` bakes a polished DETERMINISTIC globals.css themed by the
  brand colour + vibe: CSS tokens, styled native elements (button/input/select/textarea/a/h1-h6/table), focus
  rings, cards, and motion (fadeInUp + hover lifts) behind a `prefers-reduced-motion` guard. Plain CSS only →
  `next build` can't fail on it. `_brand_palette` maps free-text colours ('warm brown'→coffee) to a palette +
  warm/cool ground (unknown→coffee brown). FND-5 ships it as verbatim `content` (is_boilerplate), and
  `agents.build_ticket` now SHORT-CIRCUITS boilerplate tickets with fixed content (written verbatim, NO LLM
  call — reliable look every build + one fewer paid ticket). Test in `test_architect_offline`. Verified live:
  swapped the themed CSS into the running 1843 frontend + rebuilt → warm coffee theme + fade-in now serving.
- **Local playability of 1843 (NOT committed — throwaway hacks on the running ephemeral containers only):**
  (a) seeded 9 published `menu_items` into `aiorg_p1843_db` so the Menu/Order pages show real content;
  (b) appended a DEMO auth bypass to the deployed backend's `auth.py` (`get_current_user`/`get_current_admin_user`
  return a stub admin) + restarted it; (c) patched the deployed frontend's `admin/menu/page.tsx` to drop the
  `isAuthenticated` gate + not require a token, rebuilt (`npm run build`) + restarted. Result: Manage-menu UI
  (add/edit/delete) is usable at the plain-HTTP URL WITHOUT Auth0 login. A fresh deploy restores the normal gate.
- **Plain-HTTP access (added to the running Caddy):** the deploy's Caddy only served HTTPS (self-signed → sandbox
  browser refuses it). Added a `:80` server block (same /api + frontend routing) and `caddy reload`, so the app
  is reachable at `http://localhost:<caddy-80-host-port>` (was 41813 this session) with no cert warning.
- **⏭️ Design follow-ups (not yet done):** generated PAGES still use inline style objects (globals.css lifts
  native elements + the ground, but page-level layout/cards are inline). A deeper pass would (a) have the frontend
  prompt use the design-system classes (.card, .btn, tokens) instead of ad-hoc inline styles, and (b) prove #38
  on a FRESH build. #38 is a big lift already; measure it on the next real/cheap build before investing more.
- **MENU-ITEM PHOTOS (committed platform feature, `df0d747`):** menu items were text-only (user: 'no pictures').
  Added an optional `image_url` to the canonical `_MENU_ITEMS_TABLE` (first-class column → flows into FND-1's
  model + the binding contract), and wired it through MENU-1 (backend request/response schemas) + MENU-2 (admin
  form field + thumbnail). URL-based (paste a photo link — no blob storage). Test in `test_architect_offline`
  (schema column + both ticket wirings). Also applied to the LIVE 1843 app (NOT committed): `ALTER TABLE
  menu_items ADD image_url`, seeded loremflickr photo URLs, patched the deployed backend model+schemas and the
  frontend menu page to render an `<img>` thumbnail, rebuilt. Public menu page rendering on a FRESH build is
  best-effort via the contract (the public menu page is a creative ticket) — verify on the next build.
  - **PERSIST fix (`b94b3c9`):** live-app testing hit the trap that a create/edit handler can accept image_url
    in the Pydantic schema yet never write it to the model (photo silently dropped). Strengthened MENU-1 to
    require PERSISTING image_url on create+update; also patched the live handlers (add_menu_item constructor +
    edit_menu_item) to set it. Test asserts the 'PERSIST' wording.
  - **Admin form + Order page images (LIVE only, NOT committed):** added image_url URL field + thumbnail to the
    Manage-menu add AND edit forms, and image thumbnails to the Order page. (Platform MENU-2 already has the
    admin form field; the Order page is a creative ticket → contract-only for fresh builds.)
  - **CUSTOMER-facing rendering now MANDATED platform-wide (`23aa9b1`):** the public menu/order pages are
    LLM-generated, so image rendering was left to chance. Added a CRITICAL item-image rule to the frontend
    SYSTEM prompt (`agents._system('frontend')`): render `<img src={item.image_url} alt={item.name}/>` as a
    thumbnail whenever image_url is set (omit when null), across menu page / order page / item cards. Enforced
    as a strong PROMPT rule (like the API-base + Auth0 rules), NOT a build-blocking gate — failing a whole build
    over a missing thumbnail is disproportionate for a visual feature. Test in `test_developers_offline`. This is
    the reliable-but-safe choice for option (b) 'deterministic public rendering'; a hard gate was rejected.
  - **FILE UPLOAD deliberately NOT taken platform-wide** (option a): stays live-1843-only because real upload
    needs PERSISTENT storage (volume/blob) — a deploy-layer design choice. URL-based is the platform default.
- **FILE UPLOAD for menu images (LIVE 1843 only, NOT committed — the platform stays URL-based):** user asked for
  device upload (and a Google search-result LINK is not a direct image URL, so it never renders). Installed
  `python-multipart` in the deployed backend, mounted `StaticFiles` at `/uploads` (reachable at `/api/uploads/*`
  via Caddy's /api strip), added `POST /admin/menu/upload-image` (UploadFile → saved to `/srv/uploads`, returns
  `{url}`), and added a `<input type=file accept=image/*>` to both admin forms that uploads then sets image_url.
  Round-trip verified. CAVEAT: `/srv/uploads` is ephemeral (lost on redeploy) — real platform upload needs
  PERSISTENT storage (volume or blob), a deliberate design choice, so it was NOT added to codegen.

## 1ee. FIX #39 — self-heal a HALLUCINATED third-party package (fresh full run 1869) (DONE 2026-08-24)
**Grounded in a REAL paid full run (project 1869, Opus on, ~$3) — the user chose the full run to surface a new
bug.** BA→Architect(18 tickets, incl. MENU-1/MENU-2)→Build 18/18 → **boot_failed** (smoke_boot caught it; the
auto-repair loop did NOT fix it). Root cause: `backend/app/security.py` (SEC-1) generated
`from starlette_limiter import Limiter` — **no such PyPI package** (the LLM hallucinated it; the real one is
`slowapi`). Because the assembly installs all third-party deps in ONE pip batch, that single bad name failed
the WHOLE batch (python-jose, stripe, email-validator, python-multipart all dropped) → the app then boot-crashed
on `ImportError: email-validator is not installed`. The existing Fix #27 boot-repair only heals a wrong PATH/name
of an INSTALLED package; an install-failed-because-nonexistent package produced only a generic Failure, so no
file was regenerated.
- **Fix (reuses the Fix #27 channel, minimal new plumbing):** `assembly._nonexistent_pkgs(out)` parses the
  non-existent package(s) from the pip output ("No matching distribution found for X" / "Could not find a
  version…"); `_missing_package_findings(written, nonexistent)` maps each back to the importing file as an
  `import_errors`-style finding (`kind="missing_package"`). `assemble()` sets `env.import_errors` + returns early
  (no 45s boot timeout). `orchestrator.repair_import_errors` emits a MISSING_PACKAGE repair ("REMOVE the import;
  use a REAL package; slowapi for rate limiting; never invent a name"). `_import_error_reason` renders it.
- **Source-side prevention:** backend system prompt now says use `slowapi` for rate limiting, there is NO
  `starlette_limiter`, only import packages that really exist.
- Verified against 1869's REAL files (flags `security.py:11`). Tests in `test_qa_offline`; qa/developers/
  smoke_boot/venv-pinning suites pass; backend rebuilt.
- **⚠️ The recent design/menu-image changes were NOT measured this run** — the build boot-failed on the SEC-1
  package before deploy, so we never saw the generated menu render. A re-run (now that #39 self-heals the cause)
  is the way to finally measure Fix #38 (design), the menu image_url end-to-end, and the image-render mandate.
  Project 1869 left in DB (boot_failed).

## 1ff. FIX #40 — build-gate OFFLINE blocklist for known-hallucinated packages (companion to #39) (DONE 2026-08-24)
User asked: "do we check imports after the developer writes code, and drop a package if it doesn't exist on
PyPI?" Answer: Fix #39 does exactly that but at SMOKE_BOOT (pip is the ground-truth oracle; the build gate is
offline/AST so it can't know PyPI truth without network). Fix #40 adds the OFFLINE fast-path at the BUILD GATE so
KNOWN hallucinations are caught one step earlier (before smoke_boot even runs), with no network.
- **`agents.hallucinated_package_imports(content, filepath)`** — AST-scans a backend `.py`'s imports; flags a
  top-level package on the curated **`_HALLUCINATED_PACKAGES`** blocklist (currently just `starlette-limiter`).
  Blocklist-only → a real package is NEVER flagged (a wrong entry would fail good builds; only proven-nonexistent
  names go in, grows as runs surface them).
- **`repair_instructions`** renders a MISSING_PACKAGE repair (drop the import; use `slowapi` for rate limiting;
  never invent a name). Wired into `_collect_stubs` beside the other build-gate detectors.
- **Two-layer defense:** build gate catches KNOWN hallucinations offline (#40); smoke_boot `pip install` stays the
  ground-truth check for ANY non-existent package not on the list (#39). Verified against 1869's real security.py
  (flags line 11). Test `test_hallucinated_package_gate`; developer offline suite passes; backend rebuilt.

## 1gg. FIX #41 — truncation gate FALSE POSITIVE on apostrophes in JSX text (re-run 1887) (DONE 2026-08-24)
**Re-run 1887 (full, Opus on, ~$3) — the payoff run that MEASURED our recent work.** BA→Architect(19 tickets)→
Build 19/19 → **error**. HUGE positive signal in the generated files first:
- ✅ **Fix #38 design system LANDED** — `globals.css` is the exact deterministic themed system (4581 chars).
- ✅ **Menu images LANDED** — `models.py` has the `image_url` column, `menu.py` PERSISTS it, and the customer
  pages (`menu`, `order`, `admin/menu`) all render `<img src={item.image_url}>` (the Fix #38 mandate worked!).
- ✅ **`starlette_limiter` did NOT recur** — Fix #39/#40 held; `security.py` clean.
- ✅ Auth flow (`providers.tsx`), Stripe, layout-wraps-provider — all generated.
**The ONLY failure was a FALSE POSITIVE:** `settings/page.tsx` (PAY-2) is a COMPLETE, valid file, but Fix #15's
`_strip_code` treated the apostrophe in JSX text (`Stripe's hosted checkout`) as a string delimiter → entered
string mode → consumed the code+parens up to the next apostrophe → desynced the brace counter → falsely reported
"2 unclosed (/{" → stubbed PAY-2 → build error. So a single English contraction in copy failed the whole build.
- **Fix:** in `_strip_code`, a `'` or `"` immediately preceded by a WORD char (letter/digit/`_`) is a contraction
  in JSX text (`Stripe's`, `we're`, `don't`), never a valid JS string start — append it, don't enter string mode.
  Backticks excluded (tagged templates legitimately follow an identifier). Genuine truncation / unterminated
  strings still caught (the 1007 fixture still flags). Fixture `jsx_apostrophe_settings_1887.tsx` = the real file.
  Test in `test_frontend_completeness_gate`; developer offline suite passes; backend rebuilt.
- **⏭️ 1887's codegen was actually GOOD** — every file is complete/valid (confirmed by Fix #41), our features all
  landed, and only the false-positive blocked it. So 1887's EXISTING files can be DEPLOYED (skip-cert, near-$0) to
  finally SEE the design system + menu images in a browser — no new $3 run needed. Project 1887 left in DB.
- Two `needs_review` files (MENU-2 admin/menu, FE-1 menu) — real files that failed the lenient LLM self-review
  but are NOT truncated and NOT stubs, so they do NOT fail the build; deployable as-is.

## 1hh. FIX #42 — re-validate POST-build rewrites (Opus auto-fix + QA regen) (fresh full run 1914) (DONE 2026-08-25)
**🏆 Run 1914 (full, Opus on, ~$3) went FURTHER than any run: Build 17/17 done → real Opus review PASSED
(claude-opus-4-8, 74 issues fixed, CERTIFIED) → QA → deploy.** But QA failed 31/92 and deploy failed
("app did not become healthy"). Every failure was a systemic `500 {"detail":"Internal server error"}` across
orders + stripe endpoints — a security-CERTIFIED app that 500s on every DB endpoint.
- **Root cause (an architectural hole):** the build gate certifies clean code, then TWO post-build stages rewrite
  files WITHOUT re-running the deterministic gates:
  1. **Opus security auto-fix (reviewer/orchestrator):** applied `rev["new_content"]` straight to `gf.content`
     with ZERO re-validation. Opus's "hardening" wrapped `get_db` in the FIX #24 HTTPException-swallow
     (`try: …yield… except Exception: raise HTTPException(500)`), so every handler error became a masked 500.
  2. **QA regen gate (`_gate_regenerated`, Fix #18):** checked syntax/symbol/attribute/http-swallow but NOT
     schema-mismatch, so QA's rewrite of `models.py` renamed the contract column `source`->`source_name` unchecked.
  Both detectors DO flag these when run — they just never ran on the rewrites. (Confirmed: `http_exception_swallow`
  and `model_schema_mismatches` both fire on 1914's real files.)
- **Fix:** `agents.rewrite_integrity_gate(content, filepath, files, schema, file_id)` — the full build-gate check
  packaged for reuse (syntax, hallucinated-pkg, symbol, attribute, http-swallow, schema-mismatch); returns a
  repair-shaped dict; `repair_instructions` gains a SCHEMA_MISMATCH section. `reviewer._accept_or_reject_fix`
  re-validates every Opus fix and KEEPS the certified original if the fix reintroduces a defect the original
  lacked. `qa._gate_regenerated` now delegates to the shared gate (adds schema-mismatch).
- Verified against 1914's REAL files: `database.py` → `http_swallow_repairs`, `models.py` → `schema_repairs`
  (`menu_items.source`). Tests `test_rewrite_integrity_gate` + `test_reviewer_rejects_unsafe_autofix`; developers
  + qa offline suites pass; backend rebuilt.
- **WHAT 1914 VALIDATED:** ✅ Fixes #39/#40/#41 all held (no hallucinated pkg, no truncation FP). ✅ Design system
  + menu image_url + column all landed again. ✅ First fresh run to PASS the real Opus review and REACH deploy.
- **⏭️ NEXT:** the cause is fixed; a re-run should now get a security-certified app that actually WORKS at QA/deploy
  — potentially the first fresh full run to a genuinely LIVE, usable app. Project 1914 left in DB.

## 1ii. FIX #43 — provision generic crypto/secret key NAMES (deploy startup, fresh full run 1934) (DONE 2026-08-25)
**Run 1934 (full, Opus on, ~$3) — the BEST run yet:** Build 20/20 → Opus PASSED (certified) → **QA 84/88** (only
4 fails — Fix #42 KILLED the systemic 500s: down from 31) → DEPLOY. But deploy FAILED at backend STARTUP.
- **Root cause:** `security.py` reads `os.getenv('ENCRYPTION_KEY')`/`os.getenv('SECRET_KEY')` at MODULE level and
  `raise RuntimeError("Critical environment variables are missing.")` if either is falsy. The platform provisions
  crypto keys ONLY under `FERNET_KEY`/`TOKEN_ENCRYPTION_KEY`/`SESSION_SECRET_KEY` — NOT the generic names the LLM
  chose. QA passed because its env auto-discovery (`_discover_required_env`) fills ANY required var with a
  throwaway; the deploy injects only the real provisioned set → `ENCRYPTION_KEY`/`SECRET_KEY` = None → RuntimeError
  at import. Same NAME-contract class as Fix #31, but for crypto keys. (The app BOOTS in QA/smoke_boot, FAILS only
  in the real deploy env — that gap is the tell.)
- **Fix:** added the generic crypto/secret names to `provisioning._CRYPTO_KEYS` so the deploy mints them:
  `ENCRYPTION_KEY`/`TOKEN_ENC_KEY`/`APP_ENCRYPTION_KEY` → a valid Fernet key (code does `Fernet(THE_KEY)`);
  `SECRET_KEY`/`APP_SECRET_KEY`/`JWT_SECRET_KEY` → a random signing secret. Platform-mintable only — NEVER an
  owner secret. `ensure_crypto_keys` mints only names in `required_env(files)`, so this is safe. Verified against
  1934's real files (both minted; ENCRYPTION_KEY is a valid Fernet key). Test in `test_devops_offline`; devops
  suite passes; backend rebuilt.
- **WHAT 1934 VALIDATED:** ✅ **Fix #42 held** — no reintroduced get_db swallow / `source` rename; QA 500s dropped
  31→4. ✅ Fixes #39/#40/#41 held. ✅ Design system + menu images landed again. Furthest + cleanest run to date.
- **⚠️ KNOWN separate bug (does NOT block deploy):** 1934's `menu.py` `MenuItemResponse` Pydantic schema is
  malformed → `GET /menu` 500s (the 4 remaining QA fails). Codegen-quality/LLM-variance; logged for follow-up.
- **⏭️ NEXT:** with #43 the app should START in deploy → a re-run has a real shot at the FIRST genuinely LIVE app
  (menu may 500 until the response_model bug is addressed). Project 1934 left in DB.

## 1jj. 🏆 MILESTONE — run 1935: first fresh full run to a LIVE, CLEAN app (QA 100/100) (2026-08-25)
The payoff run for the whole #37–#43 wave. Ran with **Opus OFF (~$1, user had $2.96 in the Anthropic account** —
a full Opus run risked a mid-review credit-out; Opus isn't needed to test a DEPLOY-startup fix). Result:
- BA → PI → Architect (20 tickets) → **Build 20/20 done** → smoke_boot → skip-cert → **QA 100/100, ZERO fails**
  → **DEPLOY LIVE at `https://localhost:45439`** (self-signed HTTPS, isolated `aiorg_p1935_*` docker stack).
- Verified serving: `/`→200, `/menu`→200, `/api/menu`→`[]` (works, not a 500 — the 1934 response_model bug did
  NOT recur), `/health`→ok. Live CSS bundle carries the FIX #38 themed design (`--color-primary:#6f4e37` warm
  brown + `fadeInUp`).
- **What this proves:** FIX #43 cleared the crypto-key startup crash (backend came up healthy); FIX #42 held
  (no reintroduced defects — the systemic 500s that plagued 1914/1934 are GONE, QA went 84→100); the design
  system + menu image_url + owner-onboarding provisioning all worked end-to-end. First fresh generation that is
  both LIVE and CLEAN.
- Config restored: `SECURITY_REVIEW_ENABLED=true` back in `.env` (the ~$1 run was a one-off debug flip).
- **Made playable** (LIVE-app hacks, NOT committed — like 1843): seeded published `menu_items` + a plain-HTTP
  Caddy `:80` block for a no-cert-warning URL. Project 1935 + its stack left up.
- **⏭️ REMAINING honest edges (LOW priority):** (a) the 1934 `MenuItemResponse` malformed-schema → `GET /menu`
  500 is LLM-variance, not yet gated (1935/1936 didn't hit it); a deterministic "response_model is a complete
  Pydantic schema" gate would harden it. (b) ✅ DONE — the Opus-ON live run (§1kk).

## 1kk. 🏆🏆 MILESTONE — run 1936: LIVE + SECURITY-CERTIFIED via the FULL production flow (Opus ON) (2026-08-26)
The definitive end-to-end success. User recharged Anthropic credits + asked for a full fresh run "including stripe
and authentication". Torn down the 1843 stack first. `SECURITY_REVIEW_ENABLED=true` (real Opus). Result:
- BA → PI → Architect (19 tickets) → **Build 19/19 done** → smoke_boot → **REAL Opus review PASSED**
  (`claude-opus-4-8`, 99 issues found / 86 fixed, **CERTIFIED**) → **QA 93/93, ZERO fails** → **DEPLOY LIVE +
  `security_certified=true` at `https://localhost:58171`** (isolated `aiorg_p1936_*` stack, self-signed HTTPS).
- Verified serving: `/`, `/menu`, `/api/menu`, `/health` all 200. **Stripe Connect** (`STRIPE_CLIENT_ID=ca_…`) +
  **Auth0** (`AUTH0_DOMAIN`/`AUTH0_CLIENT_ID`/`AUTH0_AUDIENCE`) provisioned into the deployed backend.
- **THE KEY PROOF: Fix #42 held through a REAL Opus run** — Opus rewrote 86 issues, yet QA came back 93/93 with
  NO systemic 500s (the reviewer's re-validation kept any defect-reintroducing "fix" out). This is the exact
  failure mode that made 1914 a certified-but-broken app; now the full flow yields a certified-AND-working app.
- All this session's fixes proven together live: #37 (audience), #38 (design), #39/#40 (hallucinated pkg),
  #41 (apostrophe FP), #42 (post-build re-validate), #43 (crypto key names).
- **Made playable** (LIVE-app hacks, NOT committed — like 1843/1935): seeded published `menu_items` + plain-HTTP
  Caddy `:80` block. Project 1936 + stack left up.
- Config unchanged (Opus stays ON — this was the intended full run, not a debug flip).

## 1ll. 🏆🏆🏆 run 1937 — the USER drove the ENTIRE pipeline BY HAND through the real UI (2026-08-26)
The human milestone. After ~2 months chasing this, the user opened the platform frontend (localhost:3000) and drove
the WHOLE flow themselves — typed the idea, talked to the BA, went through onboarding, watched every stage. Their
idea: **"raja foods" — a small ITALIAN RESTAURANT** (menu + online takeout orders + pay), design **"Luxury premium",
brand_color BLACK**, menu_setup=manual. Result, fully hands-on via Opus-ON pipeline:
- BA → PI → Architect (17 tickets) → **Build 16 files done** → **real Opus PASS (certified)** → **QA 90/90, ZERO
  fails** → **DEPLOY LIVE + certified at `https://localhost:41535`** (isolated `aiorg_p1937_*` stack). Stripe Connect
  + Auth0 provisioned. The design system landed BLACK (Fix #38 luxury/black theme). Frontend routes: `/`, `/online`,
  `/order`, `/order/fe_3`, `/admin/menu`, `/settings` (no `/menu` — this generation structured pages its own way;
  the menu lives on `/online` + `/order`, and all render `image_url` — Fix #38 image mandate held).
- **Made playable** (LIVE-app hacks, NOT committed): seeded 8 Italian dishes + photos; plain-HTTP Caddy `:80`;
  auth bypass (backend `auth.py` stub `get_current_user`/`get_current_admin_user` returning permissions=['admin'] +
  frontend `admin/menu/page.tsx` login-gate removed + rebuilt) so Manage-menu add/edit/delete works login-free.
- **🐞 REAL BUG in the generated app → the GATE TO ADD TOMORROW:** creating a menu item 500'd. Root cause: the
  generated `MenuItem` (and `Order`) model declared `created_at = Column(DateTime, nullable=False)` **with NO default**
  (no `server_default`, no Python default), and the create handler NEVER sets `created_at` → every INSERT sends
  `created_at=NULL` → `NotNullViolationError` → 500 (masked by the handler's broad `except SQLAlchemyError → 500`).
  QA's 90/90 did NOT catch it (QA's create tests may not exercise this path, or the tested tables differ). Patched
  LIVE by `ALTER TABLE menu_items ALTER COLUMN created_at DROP NOT NULL` (create then returns 200). **NOT committed.**

## ✅ FIX #44 (2026-08-26 morning) — render the Connect-Stripe button in the BA onboarding (run 1937)
User's screenshot of their 1937 run exposed a real UI bug: the BA `connect_accounts` stage says "tap the button to
connect" Stripe, and the backend (`ba/controller.py`) DOES send `ui.kind="connect_accounts"` + `providers[]`
(label + `/connect/stripe/start?project_id=` URL) — but the platform frontend (`frontend/app/page.tsx`) had NO
handler for that `ui.kind`, so it fell through to the plain text box and the **Connect button NEVER rendered**. The
owner could only type skip/next — the interactive Stripe-connect step was unreachable (the AUTO Auth0/Stripe/email
provisioning at deploy still ran, which is why the deployed apps HAD the creds). Fixed: added a `connect_accounts`
render block (a per-provider button opening `${API_URL}${provider.url}` — the Stripe OAuth flow — in a new tab,
plus next/skip) and extended the `UI` type. Frontend compiles clean + serves. Committed + pushed (`3fcc089`).

## ✅ FIX #45 (2026-08-26) — DONE — gate a NOT-NULL datetime column with no default (run-1937 create-500)
The run-1937 `created_at` bug is now gated. `agents.timestamp_not_null_no_default(content, filepath)` — AST detector:
flags a NOT-NULL **datetime-family** column (created_at/updated_at/order_time…) that has NO `default`/`server_default`
(skips PKs + already-defaulted columns). Zero-FP by design: only datetime types (handlers virtually never set a
timestamp on create), so NOT-NULL string/int columns that ARE set from the request body are never flagged.
`repair_instructions` gains a TIMESTAMP_NO_DEFAULT section (add `server_default=sa.func.now()`). Wired into BOTH
`_collect_stubs` (build gate) AND the shared `rewrite_integrity_gate` (Fix #42 → so Opus/QA rewrites are re-checked).
Verified against 1937's REAL models.py — flags `orders.order_time`, `stripe_accounts.created_at`,
`menu_items.created_at` (all latent create-500s, incl. `order_time` which wasn't found by hand). Tests +
developers/qa suites pass. Committed `1b09654`.
- **⏭️ STILL OPEN (LOWER priority):** the 1934 `MenuItemResponse` malformed-Pydantic-schema → GET /menu 500 gate.

## 🧹 STATE (2026-08-26 morning) — platform UP (idle, $0), all ephemeral app stacks gone
- **UPDATE:** the platform (`docker compose up -d`) is BACK UP as of this morning — brought up ONLY to verify Fix
  #44 compiles (idle = no LLM = $0). All ephemeral generated-app stacks stay REMOVED. Last night's teardown note
  below still describes the overnight state.
- **All ephemeral generated-app stacks REMOVED**: `aiorg_p1843_*` (earlier), `aiorg_p1935_*`, `aiorg_p1936_*`,
  `aiorg_p1937_*` all torn down. **Platform itself STOPPED** (`docker compose down`). Nothing running → $0 spend.
  Volumes persist (platform DB + secrets safe). **Restart tomorrow: `docker compose up -d`.**
- **All platform code COMMITTED + PUSHED** (HEAD on origin/master). This session shipped Fixes **#37–#43** + the
  README/LICENSE/scrub for going public. The live-app playability tweaks (seed/auth-bypass/DB ALTER/Caddy HTTP) were
  NEVER committed — they only lived on the now-removed ephemeral stacks.
- Projects 1934/1935/1936/1937 rows remain in the platform DB (the stacks are gone, the DB records stay) as captured
  fixture sources if needed.
- ⛔ Repo public-readiness: current files are scrubbed of the real infra identifiers + secrets-clean; the identifiers
  still linger in OLD git history (non-secret) — a `git filter-repo` history scrub is prepared but NOT run (user chose
  Option A: safe to publish as-is). `.env` stays gitignored (real STRIPE/AUTH0/SMTP test creds live there).

## 1mm. run 1950 (user's 2nd hands-on run) — Fixes #46/#47/#48 from ONE run (2026-08-26)
User did a 2nd hands-on run through the real UI ("raja foods" Italian restaurant, black luxury theme) — and this
time COMPLETED the Stripe connect step (Fix #44's button worked; `stripe_connect.is_connected(1950)==True`). The
run went Build 20/20 (**Fix #45 CAUGHT + repaired** the created_at bug live — flagged orders.order_date/
stripe_accounts.created_at/menu_items.created_at, added server_default) → Opus certified → **QA 103/103 PERFECT**
→ **DEPLOY FAILED**. Diagnosing the deploy surfaced THREE grounded platform bugs, all now fixed:
- **FIX #46 (`05939a3`) — mint STRIPE_STATE_SIGNING_KEY:** stripe.py fail-fasts at import on 5 Stripe vars incl.
  `STRIPE_STATE_SIGNING_KEY`, which the platform minted only as `STRIPE_STATE_SECRET` (Fix #43 name-contract class).
  Added STRIPE_STATE_SIGNING_KEY/STRIPE_STATE_SIGN_KEY/STATE_SIGNING_KEY to `_CRYPTO_KEYS`.
- **FIX #47 (`d9bb6b8`) — Auth0 deploy resilience:** per-project Auth0 provisioning 403'd (platform tenant app-limit
  / lost Mgmt scope from our MANY runs) → app fail-fasted on missing AUTH0_* → whole deploy died. Now when Auth0
  provisioning is unavailable AND the app needs it, the deploy injects safe PLACEHOLDER Auth0 config
  (`auth0_provision.placeholder_config` — a non-resolving `.invalid` domain, so JWKS fails cleanly per-request, never
  at import) → app BOOTS + goes LIVE for public features, login degraded, reported honestly (`auth_degraded`).
  Verified triggering on redeploy.
- **FIX #48 (`0249df4`) — re-validate FRONTEND rewrites (the frontend half of Fix #42):** the REAL deploy blocker —
  `next build` failed on `admin/menu/page.tsx:401` ('Unexpected token div'). The file was CLEAN at the build gate but
  a POST-build rewrite (Opus/QA) truncated it (2 unclosed openers), and `rewrite_integrity_gate` only re-checked
  backend `.py`. Extended it to re-check frontend files (frontend_incomplete + frontend_css_leak → `frontend_repairs`;
  repair_instructions renders FRONTEND_FILE_BROKEN). Now the reviewer rejects a truncating Opus frontend fix (keeps
  the clean original). Verified: the gate flags 1950's real broken file.
- **⚠️ 1950 itself:** its generated `admin/menu/page.tsx` is ALREADY truncated in the DB; Fix #48 prevents the class
  GOING FORWARD but doesn't un-break 1950's file — 1950 would need that one file regenerated to deploy. Its
  Auth0/Stripe/created_at issues are all fixed platform-side. Projects 1948/1949 (BA-walkthrough test convos) +
  1950 left in DB.
- **⚠️ Auth0 tenant is at/over its app limit** (403 on create) from all our runs — the user should delete old
  auto-provisioned Auth0 apps in the dashboard, or Fix #47 keeps future deploys LIVE (login-degraded) regardless.
