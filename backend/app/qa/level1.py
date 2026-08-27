"""LEVEL 1 — user interaction testing (Week 6).

For every generated API endpoint, exercise the ways a real person actually
breaks software:

    happy path · empty inputs · wrong data types · double clicking ·
    very long inputs (1000+ chars) · missing required fields (one at a time) ·
    network interruption (slow + failed requests)

Endpoints are discovered from the RUNNING app's own /openapi.json rather than
from the blueprint, so we test what was actually built, not what was intended.

Generated UI files get a static pass (imports actually resolve, pages export a
component) AND a real `npm install && next build` (settings.qa_frontend_full_build,
ON by default since fix #51 — run 1950's unclosed `<p>` kept braces balanced so the
static check passed but the deploy's build failed; only a real build catches that
JSX-structure class). The build costs an npm install + compile per QA pass; set the
flag false only for a fast local codegen loop.

Rule used throughout: a 5xx (or a hang/crash) is a FAILURE. A 4xx is the app
correctly rejecting bad input — that is a PASS.
"""
import asyncio
import json
import logging
import os
import re
import shutil

import httpx

from app.config import settings
from app.qa.assembly import TestEnv
from app.qa.outcome import TestOutcome, failure_is_server_error

logger = logging.getLogger("qa.level1")

LONG_STRING = "A" * 2000          # "very long inputs: 1000+ characters"
_SKIP_PATHS = ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")


# ------------------------------------------------------------------ schema
def _resolve(schema: dict, spec: dict, depth: int = 0) -> dict:
    """Follow $ref into components/schemas."""
    if not isinstance(schema, dict) or depth > 6:
        return {}
    ref = schema.get("$ref")
    if ref and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        return _resolve(spec.get("components", {}).get("schemas", {}).get(name, {}),
                        spec, depth + 1)
    return schema


def _sample(schema: dict, spec: dict, depth: int = 0) -> object:
    """A plausible VALID value for a schema — the happy-path payload."""
    schema = _resolve(schema, spec, depth)
    if depth > 5:
        return "x"
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]

    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {k: _sample(v, spec, depth + 1) for k, v in props.items()}
    if t == "array":
        return [_sample(schema.get("items", {}), spec, depth + 1)]
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    fmt = schema.get("format")
    if fmt == "email":
        return "qa.tester@example.com"
    if fmt in ("date-time", "date"):
        return "2026-01-01T00:00:00Z"
    if fmt == "uuid":
        return "00000000-0000-4000-8000-000000000000"
    return "qa-test"


def _string_fields(schema: dict, spec: dict) -> list[str]:
    schema = _resolve(schema, spec)
    return [k for k, v in (schema.get("properties") or {}).items()
            if _resolve(v, spec).get("type") in (None, "string")]


def _numeric_fields(schema: dict, spec: dict) -> list[str]:
    schema = _resolve(schema, spec)
    return [k for k, v in (schema.get("properties") or {}).items()
            if _resolve(v, spec).get("type") in ("integer", "number")]


def _body_schema(op: dict, spec: dict) -> dict:
    body = op.get("requestBody") or {}
    content = (body.get("content") or {}).get("application/json") or {}
    return _resolve(content.get("schema") or {}, spec)


def _fill_path(path: str, op: dict, spec: dict) -> str:
    """Substitute path params with valid-looking values."""
    def sub(m):
        name = m.group(1)
        for p in op.get("parameters", []) or []:
            if p.get("name") == name:
                val = _sample(p.get("schema", {}), spec)
                return str(val)
        return "1"
    return re.sub(r"\{([^}]+)\}", sub, path)


def _endpoints(spec: dict) -> list[tuple[str, str, dict]]:
    out = []
    for path, item in (spec.get("paths") or {}).items():
        if path in _SKIP_PATHS:
            continue
        for method, op in (item or {}).items():
            if method.lower() in ("get", "post", "put", "patch", "delete") and isinstance(op, dict):
                out.append((method.upper(), path, op))
    return out


# ------------------------------------------------------------------ requests
async def _send(client: httpx.AsyncClient, base: str, method: str, url: str,
                payload: object | None, timeout: float | None = None):
    kwargs = {}
    if payload is not None and method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = payload
    if timeout is not None:
        kwargs["timeout"] = timeout
    return await client.request(method, f"{base}{url}", **kwargs)


async def _probe(client, base, method, url, payload, label, target,
                 timeout: float | None = None) -> TestOutcome:
    """One request; 5xx / crash / hang = failure, anything else = pass."""
    try:
        r = await _send(client, base, method, url, payload, timeout)
    except httpx.TimeoutException:
        return TestOutcome(label, 1, False, "The request timed out — the app hung "
                           "instead of responding.", target)
    except Exception as exc:
        return TestOutcome(label, 1, False, f"The app dropped the connection: {exc}", target)
    if failure_is_server_error(r.status_code):
        return TestOutcome(label, 1, False,
                           f"Server error {r.status_code} — the app crashed instead of "
                           f"handling this. Response: {r.text[:300]}", target)
    return TestOutcome(label, 1, True, "", target)


# ------------------------------------------------------------------ per endpoint
async def _test_endpoint(client, base, method, path, op, spec) -> list[TestOutcome]:
    target = f"{method} {path}"
    url = _fill_path(path, op, spec)
    schema = _body_schema(op, spec)
    has_body = bool(schema) and method in ("POST", "PUT", "PATCH")
    valid = _sample(schema, spec) if has_body else None
    results: list[TestOutcome] = []

    # 1. Happy path
    results.append(await _probe(client, base, method, url, valid,
                                f"{target} — happy path", target))

    if has_body:
        # 2. Empty inputs
        results.append(await _probe(client, base, method, url, {},
                                    f"{target} — empty input", target))

        # 3. Wrong data types (letters where numbers expected)
        nums = _numeric_fields(schema, spec)
        if nums and isinstance(valid, dict):
            bad = {**valid, **{n: "not-a-number" for n in nums}}
            results.append(await _probe(client, base, method, url, bad,
                                        f"{target} — wrong data types", target))

        # 5. Very long inputs (1000+ chars)
        strs = _string_fields(schema, spec)
        if strs and isinstance(valid, dict):
            long_payload = {**valid, **{s: LONG_STRING for s in strs}}
            results.append(await _probe(client, base, method, url, long_payload,
                                        f"{target} — very long input", target))

        # 6. Missing required fields, one at a time
        for field in (schema.get("required") or [])[:6]:
            if isinstance(valid, dict) and field in valid:
                missing = {k: v for k, v in valid.items() if k != field}
                results.append(await _probe(
                    client, base, method, url, missing,
                    f"{target} — missing required field '{field}'", target))

    # 4. Double clicking — two identical requests fired at once
    try:
        r1, r2 = await asyncio.gather(
            _send(client, base, method, url, valid),
            _send(client, base, method, url, valid),
            return_exceptions=True,
        )
        broke = [r for r in (r1, r2)
                 if isinstance(r, Exception) or failure_is_server_error(r.status_code)]
        if broke:
            detail = (str(broke[0]) if isinstance(broke[0], Exception)
                      else f"status {broke[0].status_code}")
            results.append(TestOutcome(
                f"{target} — double click", 1, False,
                f"Submitting twice quickly broke the app ({detail}). Rapid repeat "
                f"submissions must be handled safely.", target))
        else:
            results.append(TestOutcome(f"{target} — double click", 1, True, "", target))
    except Exception as exc:
        results.append(TestOutcome(f"{target} — double click", 1, False, str(exc), target))

    # 7. Network interruption — client aborts mid-flight, app must stay alive
    try:
        await _send(client, base, method, url, valid, timeout=0.001)
    except Exception:
        pass  # the abort itself is expected
    results.append(await _probe(client, base, method, url, valid,
                                f"{target} — recovery after interrupted request", target))
    return results


# ------------------------------------------------------------------ frontend
_REL_IMPORT_RE = re.compile(r"""import\s+[^'"]*from\s+['"]([^'"]+)['"]""")
_UI_EXT = (".tsx", ".ts", ".jsx", ".js")


def _check_frontend(env: TestEnv) -> list[TestOutcome]:
    """Static checks on generated UI files: do imports point at files that were
    actually generated, do pages export a component, and is each file COMPLETE (not
    truncated/invalid) — the last catches project 1007's cut-off review page WITHOUT
    needing the opt-in `next build`, so a truncated .tsx fails QA, not the deploy."""
    from app.developers.agents import frontend_incomplete  # local: avoid import cycle
    results: list[TestOutcome] = []
    ui = {r: c for r, c in env.files.items()
          if r.startswith(("frontend/", "mobile/")) and r.endswith(_UI_EXT)}

    for rel, content in ui.items():
        # Completeness/parse: a truncated or unbalanced JS/TS file breaks `next build`.
        incomplete = frontend_incomplete(rel, content)
        if incomplete:
            results.append(TestOutcome(
                f"{rel} — complete & parseable", 1, False,
                f"The generated interface file is {incomplete} — `next build` "
                f"would fail to compile it.", rel))
        else:
            results.append(TestOutcome(f"{rel} — complete & parseable", 1, True, "", rel))

        # Relative / alias imports must resolve to a real generated file. This is
        # the cross-file drift bug the binding contract exists to prevent.
        broken = []
        for spec_path in _REL_IMPORT_RE.findall(content):
            if not spec_path.startswith((".", "@/", "~/")):
                continue  # npm package — covered by the optional full build
            if spec_path.startswith("@/") or spec_path.startswith("~/"):
                cand = os.path.normpath(os.path.join("frontend", spec_path[2:]))
            else:
                cand = os.path.normpath(os.path.join(os.path.dirname(rel), spec_path))
            if not any(f == cand or f.startswith(cand + ".") or f.startswith(cand + "/")
                       for f in env.files):
                broken.append(spec_path)
        if broken:
            results.append(TestOutcome(
                f"{rel} — imports resolve", 1, False,
                f"Imports point at files that were never generated: "
                f"{', '.join(broken[:5])}.", rel))
        else:
            results.append(TestOutcome(f"{rel} — imports resolve", 1, True, "", rel))

        # A Next.js page/screen must export a component to render at all.
        if rel.endswith(("page.tsx", "page.jsx")) and "export default" not in content:
            results.append(TestOutcome(
                f"{rel} — screen renders", 1, False,
                "This screen has no default export, so it cannot render.", rel))

    return results


async def _full_frontend_build(env: TestEnv) -> list[TestOutcome]:
    """Real `next build` (settings.qa_frontend_full_build, on by default — fix #51)."""
    from app.qa.assembly import _run  # local import: internal helper

    fe = os.path.join(env.root or "", "frontend")
    if not os.path.isdir(fe):
        # Never return [] here: a check that produces NO outcome is
        # indistinguishable from one that passed. Say which case this is.
        if any(r.startswith("frontend/") for r in (env.files or {})):
            return [TestOutcome(
                "frontend — build", 1, False,
                "Interface files were generated but no frontend directory exists "
                "to build them in.", "frontend")]
        return [TestOutcome(
            "frontend — build (not applicable)", 1, True,
            "This build has no interface files, so there is nothing to build.",
            "frontend")]
    if not os.path.exists(os.path.join(fe, "package.json")):
        return [TestOutcome("frontend — build", 1, False,
                            "No package.json was generated, so the interface cannot "
                            "be built.", "frontend")]
    # A missing toolchain is QA's problem, not the generated code's. Without this
    # check `_run` returns -1 ("No such file or directory: 'npm'") and the
    # failure reads as "Interface dependencies failed to install" — blaming the
    # Developer for the harness, which is exactly how QA once "fixed" correct
    # fail-fast auth by hardcoding credentials. The wording is matched by
    # root_cause._ENV_REASON_SIGNALS so it classifies as environment_fault.
    if shutil.which("npm") is None:
        return [TestOutcome(
            "frontend — build", 1, False,
            "QA's test environment has no Node toolchain (npm is not installed "
            "in the test container), so the interface could not be built here. "
            "The generated interface code is not at fault.", "frontend")]

    code, out = _run(["npm", "install", "--no-audit", "--no-fund"], cwd=fe, timeout=600)
    if code != 0:
        return [TestOutcome("frontend — dependencies install", 1, False,
                            f"Interface dependencies failed to install: {out[-500:]}",
                            "frontend")]
    code, out = _run(["npx", "next", "build"], cwd=fe, timeout=600)
    if code != 0:
        return [TestOutcome("frontend — build", 1, False,
                            f"The interface failed to build: {out[-800:]}", "frontend")]
    return [TestOutcome("frontend — build", 1, True, "", "frontend")]


# ------------------------------------------------------------------ entrypoint
async def run_static(env: TestEnv) -> list[TestOutcome]:
    """Checks that need only the generated FILES — never a booted backend.

    These used to sit inside run(), which the orchestrator calls only when
    assembly succeeded. So a backend that failed to boot silently cost the
    frontend ALL of its coverage, including the full `next build`, even though
    frontend buildability has nothing to do with whether the backend starts.
    Two independent things were chained to one condition; this unchains them.
    """
    results: list[TestOutcome] = _check_frontend(env)

    if settings.qa_frontend_full_build:
        try:
            results.extend(await _full_frontend_build(env))
        except Exception as exc:  # pragma: no cover
            results.append(TestOutcome("frontend — build", 1, False, str(exc)[:300],
                                       "frontend"))
    return results


async def run(env: TestEnv) -> list[TestOutcome]:
    """Level 1 tests against the RUNNING instance.

    Static file checks live in run_static(), which the orchestrator calls
    whether or not the app booted.
    """
    results: list[TestOutcome] = []

    async with httpx.AsyncClient(timeout=settings.qa_request_timeout) as client:
        try:
            spec_res = await client.get(f"{env.base_url}/openapi.json")
            spec = spec_res.json() if spec_res.status_code == 200 else {}
        except Exception as exc:
            results.append(TestOutcome(
                "API — discoverable", 1, False,
                f"Could not read the app's own API description: {exc}", "app"))
            return results

        eps = _endpoints(spec)
        if not eps:
            results.append(TestOutcome(
                "API — has endpoints", 1, False,
                "The app started but exposes no working endpoints.", "app"))
            return results

        for method, path, op in eps:
            try:
                results.extend(await _test_endpoint(client, env.base_url, method,
                                                    path, op, spec))
            except Exception as exc:  # pragma: no cover - never kill the run
                results.append(TestOutcome(f"{method} {path} — test error", 1, False,
                                           str(exc)[:300], f"{method} {path}"))
    return results
