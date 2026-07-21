"""LEVEL 2 — security attack simulation (Week 6).

Actively tries to exploit the RUNNING throwaway instance of the user's own
generated app:

    protected pages without login · invalid credentials · SQL injection through
    every input field · another project's data via ID manipulation (IDOR) ·
    negative payment amounts · malicious file names

SCOPE GUARD: every request is asserted against the ephemeral loopback instance
before it is sent (`_assert_local`). This agent can only ever attack the
throwaway app on this machine — never an external host.

This complements, and does not replace, the Week-5 Code Reviewer: that reads the
code with Claude Opus 4.8, this attacks the app while it is actually running.
"""
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.qa.assembly import TEST_HOST, TestEnv
from app.qa.outcome import TestOutcome, failure_is_server_error
from app.qa.level1 import (
    _body_schema, _endpoints, _fill_path, _numeric_fields, _sample, _string_fields,
)

logger = logging.getLogger("qa.level2")

SQL_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1' UNION SELECT NULL,NULL--",
    "admin'--",
]

MALICIOUS_FILENAMES = [
    "../../../../etc/passwd",
    "shell.php%00.jpg",
    "<script>alert(1)</script>.png",
    "..\\..\\windows\\system32\\config\\sam",
]

# Signs the database engine leaked an error straight back to the caller.
_SQL_ERROR_RE = re.compile(
    r"(syntax error at or near|psycopg|asyncpg|sqlalchemy|sqlite3\.|"
    r"unterminated quoted string|PG::|SQLSTATE)", re.I)

_AUTH_WORDS = ("login", "signin", "sign-in", "token", "auth", "session")
_PROTECTED_WORDS = ("admin", "me", "profile", "account", "settings", "dashboard",
                    "orders", "users", "payments", "stripe")
_AMOUNT_WORDS = ("amount", "price", "total", "cost", "fee", "tip", "quantity",
                 "qty", "subtotal", "balance")


def _assert_local(url: str) -> None:
    """Hard guard: QA may only ever talk to the ephemeral loopback instance."""
    host = urlparse(url).hostname
    if host not in (TEST_HOST, "localhost", "::1"):
        raise RuntimeError(
            f"QA attack simulation refused: target '{host}' is not the local "
            f"throwaway test instance."
        )


async def _req(client, base, method, path, **kw):
    url = f"{base}{path}"
    _assert_local(url)
    return await client.request(method, url, **kw)


# ------------------------------------------------------------------ attacks
async def _no_login(client, base, spec) -> list[TestOutcome]:
    """Try reaching protected-looking endpoints with no credentials at all."""
    out = []
    for method, path, op in _endpoints(spec):
        if method != "GET":
            continue
        if not any(w in path.lower() for w in _PROTECTED_WORDS):
            continue
        target = f"{method} {path}"
        try:
            r = await _req(client, base, method, _fill_path(path, op, spec))
        except Exception as exc:
            out.append(TestOutcome(f"{target} — blocks access without login", 2, False,
                                   f"Request failed: {exc}", target))
            continue
        if r.status_code in (401, 403):
            out.append(TestOutcome(f"{target} — blocks access without login", 2, True,
                                   "", target))
        elif failure_is_server_error(r.status_code):
            out.append(TestOutcome(f"{target} — blocks access without login", 2, False,
                                   f"Server error {r.status_code} instead of refusing "
                                   f"access.", target))
        elif r.status_code == 200 and len(r.text.strip()) > 2 and r.text.strip() not in ("[]", "{}"):
            out.append(TestOutcome(
                f"{target} — blocks access without login", 2, False,
                "Private information was returned to a visitor who never logged in.",
                target))
        else:
            out.append(TestOutcome(f"{target} — blocks access without login", 2, True,
                                   "", target))
    return out


async def _bad_credentials(client, base, spec) -> list[TestOutcome]:
    """Log in with credentials that must never work."""
    out = []
    for method, path, op in _endpoints(spec):
        if method != "POST" or not any(w in path.lower() for w in _AUTH_WORDS):
            continue
        target = f"{method} {path}"
        schema = _body_schema(op, spec)
        payload = _sample(schema, spec) if schema else {}
        if isinstance(payload, dict):
            for k in payload:
                if "pass" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    payload[k] = "definitely-not-the-password"
                elif "email" in k.lower() or "user" in k.lower():
                    payload[k] = "nobody@example.invalid"
        try:
            r = await _req(client, base, method, _fill_path(path, op, spec), json=payload)
        except Exception as exc:
            out.append(TestOutcome(f"{target} — rejects invalid credentials", 2, False,
                                   f"Request failed: {exc}", target))
            continue
        if r.status_code in (400, 401, 403, 404, 422):
            out.append(TestOutcome(f"{target} — rejects invalid credentials", 2, True,
                                   "", target))
        elif failure_is_server_error(r.status_code):
            out.append(TestOutcome(f"{target} — rejects invalid credentials", 2, False,
                                   f"Server error {r.status_code} on a bad login attempt.",
                                   target))
        else:
            out.append(TestOutcome(
                f"{target} — rejects invalid credentials", 2, False,
                f"A completely invalid login was accepted (status {r.status_code}).",
                target))
    return out


# Field names to try when a body accepts free-form JSON (no declared schema).
# Untyped bodies are exactly where unvalidated input tends to reach the database,
# so they must never be skipped just because OpenAPI declares no properties.
_GENERIC_FIELDS = ("q", "query", "search", "name", "email", "username", "title",
                   "description", "comment", "message", "filter")


def _judge_injection(r, target: str, label: str) -> TestOutcome:
    if _SQL_ERROR_RE.search(r.text or ""):
        return TestOutcome(label, 2, False,
                           "A database error was returned to the caller, which means "
                           "the input reached the database unsafely.", target)
    if failure_is_server_error(r.status_code):
        return TestOutcome(label, 2, False,
                           f"Server error {r.status_code} when given a SQL injection "
                           f"string — the input was not handled safely.", target)
    return TestOutcome(label, 2, True, "", target)


async def _sql_injection(client, base, spec) -> list[TestOutcome]:
    """Push SQL injection payloads through every input field we can find:
    declared body fields, free-form bodies, query strings and path params."""
    out = []
    for method, path, op in _endpoints(spec):
        target = f"{method} {path}"
        label = f"{target} — resists SQL injection"
        schema = _body_schema(op, spec)
        fields = _string_fields(schema, spec) if schema else []
        base_payload = _sample(schema, spec) if schema else None
        accepts_body = bool(op.get("requestBody")) and method in ("POST", "PUT", "PATCH")

        # Body fields — declared, or generic names when the body is free-form.
        if accepts_body:
            for payload_str in SQL_PAYLOADS[:2]:
                if fields and isinstance(base_payload, dict):
                    attack = {**base_payload, **{f: payload_str for f in fields}}
                else:
                    # No declared properties: probe with common field names.
                    attack = {f: payload_str for f in _GENERIC_FIELDS}
                    if isinstance(base_payload, dict):
                        attack = {**base_payload, **attack}
                try:
                    r = await _req(client, base, method, _fill_path(path, op, spec),
                                   json=attack)
                except Exception as exc:
                    out.append(TestOutcome(label, 2, False, f"Request failed: {exc}",
                                           target))
                    continue
                out.append(_judge_injection(r, target, label))

        # Query-string parameters (declared, plus a generic probe).
        query_names = [p.get("name") for p in (op.get("parameters") or [])
                       if p.get("in") == "query" and p.get("name")]
        if method in ("GET", "DELETE"):
            probes = query_names or ["q"]
            params = {n: SQL_PAYLOADS[0] for n in probes}
            try:
                r = await _req(client, base, method, _fill_path(path, op, spec),
                               params=params)
                out.append(_judge_injection(
                    r, target, f"{target} — resists SQL injection in search terms"))
            except Exception:
                pass

        # Path params (e.g. /orders/{id})
        if "{" in path:
            hostile = re.sub(r"\{[^}]+\}", "1'%20OR%20'1'='1", path)
            try:
                r = await _req(client, base, method, hostile)
                if _SQL_ERROR_RE.search(r.text or "") or failure_is_server_error(r.status_code):
                    out.append(TestOutcome(
                        f"{target} — resists SQL injection in address bar", 2, False,
                        "A SQL injection string in the web address reached the "
                        "database.", target))
                else:
                    out.append(TestOutcome(
                        f"{target} — resists SQL injection in address bar", 2, True, "",
                        target))
            except Exception:
                pass
    return out


async def _idor(client, base, spec) -> list[TestOutcome]:
    """Change the ID in the URL to reach somebody else's record."""
    out = []
    for method, path, op in _endpoints(spec):
        if method != "GET" or "{" not in path:
            continue
        target = f"{method} {path}"
        exposed = []
        for other_id in (1, 2, 3, 9999):
            probe = re.sub(r"\{[^}]+\}", str(other_id), path)
            try:
                r = await _req(client, base, method, probe)
            except Exception:
                continue
            if r.status_code == 200 and len(r.text.strip()) > 2 and \
                    r.text.strip() not in ("[]", "{}", "null"):
                exposed.append(other_id)
        if len(exposed) >= 2:
            out.append(TestOutcome(
                f"{target} — blocks access to other people's records", 2, False,
                f"Records {exposed[:4]} were all returned to an unauthenticated "
                f"visitor just by changing the ID in the address.", target))
        else:
            out.append(TestOutcome(
                f"{target} — blocks access to other people's records", 2, True, "",
                target))
    return out


async def _negative_amounts(client, base, spec) -> list[TestOutcome]:
    """Submit negative money. Must be rejected, never accepted."""
    out = []
    for method, path, op in _endpoints(spec):
        if method not in ("POST", "PUT", "PATCH"):
            continue
        schema = _body_schema(op, spec)
        if not schema:
            continue
        nums = _numeric_fields(schema, spec)
        money = [n for n in nums if any(w in n.lower() for w in _AMOUNT_WORDS)]
        if not money:
            continue
        target = f"{method} {path}"
        payload = _sample(schema, spec)
        if not isinstance(payload, dict):
            continue
        attack = {**payload, **{m: -9999 for m in money}}
        try:
            r = await _req(client, base, method, _fill_path(path, op, spec), json=attack)
        except Exception as exc:
            out.append(TestOutcome(f"{target} — rejects negative amounts", 2, False,
                                   f"Request failed: {exc}", target))
            continue
        if 200 <= r.status_code < 300:
            out.append(TestOutcome(
                f"{target} — rejects negative amounts", 2, False,
                f"A negative amount ({', '.join(money)} = -9999) was accepted. This "
                f"would let someone pay a negative amount.", target))
        elif failure_is_server_error(r.status_code):
            out.append(TestOutcome(f"{target} — rejects negative amounts", 2, False,
                                   f"Server error {r.status_code} on a negative amount.",
                                   target))
        else:
            out.append(TestOutcome(f"{target} — rejects negative amounts", 2, True, "",
                                   target))
    return out


async def _malicious_filenames(client, base, spec) -> list[TestOutcome]:
    """Only runs if the generated app actually has an upload endpoint."""
    out = []
    for method, path, op in _endpoints(spec):
        body = op.get("requestBody") or {}
        content = body.get("content") or {}
        is_upload = "multipart/form-data" in content or "file" in path.lower() or \
                    "upload" in path.lower()
        if method != "POST" or not is_upload:
            continue
        target = f"{method} {path}"
        for name in MALICIOUS_FILENAMES[:2]:
            try:
                r = await _req(client, base, method, _fill_path(path, op, spec),
                               files={"file": (name, b"qa-test", "text/plain")})
            except Exception:
                continue
            if 200 <= r.status_code < 300:
                out.append(TestOutcome(
                    f"{target} — rejects dangerous file names", 2, False,
                    f"A file named '{name}' was accepted. Names like this can "
                    f"overwrite system files.", target))
            elif failure_is_server_error(r.status_code):
                out.append(TestOutcome(f"{target} — rejects dangerous file names", 2,
                                       False,
                                       f"Server error {r.status_code} on a hostile "
                                       f"file name.", target))
            else:
                out.append(TestOutcome(f"{target} — rejects dangerous file names", 2,
                                       True, "", target))
    return out


# ------------------------------------------------------------------ entrypoint
async def run(env: TestEnv) -> list[TestOutcome]:
    """Run the full attack simulation against the throwaway instance."""
    _assert_local(env.base_url or "")
    results: list[TestOutcome] = []

    async with httpx.AsyncClient(timeout=settings.qa_request_timeout) as client:
        try:
            spec_res = await client.get(f"{env.base_url}/openapi.json")
            spec = spec_res.json() if spec_res.status_code == 200 else {}
        except Exception as exc:
            return [TestOutcome("security — app reachable", 2, False,
                                f"Could not inspect the running app: {exc}", "app")]

        for attack in (_no_login, _bad_credentials, _sql_injection, _idor,
                       _negative_amounts, _malicious_filenames):
            try:
                results.extend(await attack(client, env.base_url, spec))
            except Exception as exc:  # pragma: no cover - one attack must not kill the rest
                logger.warning("Attack %s errored: %s", attack.__name__, exc)
                results.append(TestOutcome(f"security — {attack.__name__.strip('_')}", 2,
                                           False, str(exc)[:300], "app"))
    return results
