"""Ephemeral test environment for the QA agent (Week 6).

Takes the code sitting as TEXT in generated_files and turns it into something
that ACTUALLY RUNS locally, just long enough to test it:

    pull files -> write to a temp dir (module layout from the binding contract)
    -> venv (--system-site-packages) -> install missing deps -> temp Postgres
    database -> uvicorn on a random free port -> health check -> hand back a
    handle -> ALWAYS tear down.

This is deliberately minimal and THROWAWAY: no AWS, no SSL, no domain, no Safe
Mode, no versioning, nothing persisted. Full production deployment is the DevOps
agent (#11, Week 7) and is explicitly out of scope here.

If assembly fails (missing dep, broken import, syntax error, app won't boot)
that is a legitimate QA FINDING, not a crash: `assemble()` returns a handle
whose `ok` is False and whose `failures` explain what broke, and the QA agent
records them as Level 1 failures with root-cause tracing like any other bug.
"""
import ast
import asyncio
import json
import logging
import os
import re
import base64
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger("qa.assembly")

# The generated app is ALWAYS bound to loopback. QA must never be able to point
# its traffic (especially the Level 2 attack simulation) at anything but the
# throwaway instance on this machine.
TEST_HOST = "127.0.0.1"

# Stdlib / already-present modules we never try to pip install.
_STDLIB_SKIP = set(sys.stdlib_module_names) | {
    "app", "backend", "frontend", "mobile", "tests", "__future__",
}

# Config the generated app legitimately requires from the environment.
#
# Generated apps are now told to delegate auth to a provider and to fail fast
# when its config is missing — that is CORRECT security behaviour. If the test
# environment does not supply it, the app rightly refuses to boot and QA blames
# the Developer for a bug that does not exist. (Observed in verification: the
# Developer "fixed" it by hardcoding mock Auth0 credentials to get past QA.)
# These are obviously-fake loopback-only values; nothing here is a real secret.
# A VALID (throwaway) Fernet key — 32 url-safe base64 bytes. Encryption-key env
# vars MUST decode as a real Fernet key or a CORRECT app that builds a Fernet cipher
# at import (e.g. the Stripe token store: `Fernet(STRIPE_TOKEN_ENC_KEY.encode())`)
# crashes under QA with "Fernet key must be 32 url-safe base64-encoded bytes" — a
# QA-environment fault, not an app bug (project 606). Used both here (curated) and
# in _fake_env_value (discovered enc-key vars).
_FAKE_FERNET_KEY = base64.urlsafe_b64encode(
    b"qa-test-fernet-throwaway-key".ljust(32, b"0")[:32]).decode()

_TEST_ENV = {
    "SECRET_KEY": "qa-test-secret-not-a-real-key",
    # Was a raw 32-char string — NOT a valid Fernet key, so it crashed at import
    # (project 606). Must be a real Fernet key.
    "STRIPE_TOKEN_ENC_KEY": _FAKE_FERNET_KEY,
    "STRIPE_CLIENT_ID": "ca_qa_test_client_id",
    "STRIPE_SECRET_KEY": "sk_test_qa_placeholder",
    "STRIPE_WEBHOOK_SECRET": "whsec_qa_test_placeholder",
    "AUTH0_DOMAIN": "qa-test.example.auth0.com",
    "AUTH0_ISSUER": "https://qa-test.example.auth0.com/",
    "AUTH0_AUDIENCE": "https://qa-test.local/api",
    "AUTH0_API_AUDIENCE": "https://qa-test.local/api",
    "AUTH0_CLIENT_ID": "qa-test-client-id",
    "AUTH0_CLIENT_SECRET": "qa-test-client-secret",
    "APP_ENV": "test",
    # CORS: the entrypoint reads an allowed-origins list from the env and fail-fasts
    # if it's empty (a security hardening the Opus review adds). It reads WITH a
    # default (`os.getenv('ALLOWED_ORIGINS', '')`), so discovery skips it — curate a
    # valid loopback origin list here so a correct app boots (project 773). CORS_ORIGINS
    # is the common alias.
    "ALLOWED_ORIGINS": "http://127.0.0.1,http://localhost",
    "CORS_ORIGINS": "http://127.0.0.1,http://localhost",
}

# Generated code fail-fast requires provider secrets by env-var name, and the
# model invents those names freely (STRIPE_STATE_SECRET, STRIPE_REDIRECT_URI, …).
# A fixed _TEST_ENV allowlist can't keep up: a real baseline run refused to boot
# on STRIPE_STATE_SECRET, which the code correctly required but _TEST_ENV didn't
# supply. So QA also SCANS the generated code for the env vars it requires and
# supplies a throwaway value for each one _TEST_ENV doesn't already cover — the
# app code is UNCHANGED and still fail-fast in production; only QA's throwaway
# child-process env is filled, so this never weakens security (it is the same
# mechanism _TEST_ENV already uses, just complete instead of hardcoded).
#
# Only NO-DEFAULT reads are matched. A var with an explicit default
# (os.getenv("X", "d")) is left alone, so an intentional default is never
# clobbered — we fill only the vars whose absence would fail-fast the boot.
_ENV_REQUIRED_RES = (
    re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\)"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\)"),
)


def _fake_env_value(name: str) -> str:
    """An obviously-fake, loopback-only value — never a plausible real secret."""
    if name.endswith(("_URI", "_URL")):
        return "http://127.0.0.1/qa-test"
    up = name.upper()
    if "FERNET" in up or "ENC_KEY" in up or "ENCRYPTION_KEY" in up:
        return _FAKE_FERNET_KEY
    return f"qa-test-{name.lower()}"


def _discover_required_env(files: list[dict]) -> dict[str, str]:
    """Env vars the generated Python fail-fast requires, minus what _TEST_ENV
    already curates (curated values win — see child-env construction)."""
    names: set[str] = set()
    for f in files:
        path = f.get("filepath") or f.get("filename") or ""
        if not path.endswith(".py"):
            continue
        content = f.get("content") or ""
        for rx in _ENV_REQUIRED_RES:
            names.update(rx.findall(content))
    return {n: _fake_env_value(n) for n in names if n not in _TEST_ENV}

# import-name -> pip package, where they differ.
_PACKAGE_ALIASES = {
    "sqlalchemy": "SQLAlchemy",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "dotenv": "python-dotenv",
    "multipart": "python-multipart",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "dateutil": "python-dateutil",
    "psycopg2": "psycopg2-binary",
    "stripe": "stripe",
    "redis": "redis",
    "httpx": "httpx",
    "pydantic_settings": "pydantic-settings",
    "email_validator": "email-validator",
}


# ---------------------------------------------------------------- version pinning
# GATE-INTEGRITY (project 829, 2026-08-12): smoke_boot PASSED an app whose
# `conlist(OrderItem, min_items=1)` cannot import under Pydantic v2, then QA
# fail-booted the SAME files — because the throwaway venv's dependency versions
# were not pinned and not guaranteed to match either the deployed image or each
# other. A gate that boots under a DIFFERENT Pydantic than the deploy (or than QA)
# can green-light un-bootable code and waste the paid Opus review. The platform's
# OWN `requirements.txt` is the tested, known-good pin set the backend container is
# built from; make it the SINGLE source of truth that both the QA/smoke_boot venv
# (via a pip --constraint file) and the deployed image (`manifest`) install from.
def _canon(name: str) -> str:
    """PEP 503-ish canonical package key: no extras, lower-case, `_`->`-`."""
    return (name or "").split("[")[0].strip().lower().replace("_", "-")


def _find_requirements_txt() -> str | None:
    """The platform's pinned requirements.txt — `/app/requirements.txt` in the
    container (COPYed before the app), and the repo's `backend/requirements.txt`
    when tests mount the source at /app. Resolve from this module's location so it
    works in both without a hard-coded path."""
    here = os.path.dirname(os.path.abspath(__file__))          # .../app/qa
    candidates = [
        os.path.join(here, "..", "..", "requirements.txt"),    # /app/requirements.txt
        os.path.join(here, "..", "..", "..", "requirements.txt"),
        os.path.join(here, "..", "..", "..", "backend", "requirements.txt"),
    ]
    for c in candidates:
        p = os.path.abspath(c)
        if os.path.isfile(p):
            return p
    return None


def _load_platform_pins() -> dict[str, str]:
    """Parse requirements.txt into {canonical package name -> exact version}.
    Only `==` pins are taken (that is all requirements.txt uses); comments,
    blanks and any non-`==` line are ignored. Empty dict if the file is absent
    (pinning then degrades to today's unpinned behaviour rather than crashing)."""
    path = _find_requirements_txt()
    pins: dict[str, str] = {}
    if not path:
        logger.warning("requirements.txt not found; dependency pins unavailable")
        return pins
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if not line or "==" not in line:
                    continue
                name, _, ver = line.partition("==")
                ver = ver.strip()
                if name and ver:
                    pins[_canon(name)] = ver
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("could not read %s: %s", path, exc)
    return pins


# Loaded ONCE at import — the container's requirements.txt is immutable at runtime.
PLATFORM_PINS: dict[str, str] = _load_platform_pins()


def pin_spec(pkg: str) -> str:
    """Pin a pip requirement (which may carry extras, e.g. `uvicorn[standard]`) to
    the platform version, preserving the extras: `uvicorn[standard]` ->
    `uvicorn[standard]==0.34.0`. A package the platform does not pin is returned
    unchanged. Used by BOTH the QA venv install and the DevOps manifest so the two
    can never diverge on a platform package."""
    if "==" in pkg or ">=" in pkg or "<" in pkg:   # already version-qualified
        return pkg
    ver = PLATFORM_PINS.get(_canon(pkg))
    return f"{pkg}=={ver}" if ver else pkg


def platform_constraints_text() -> str:
    """Body of a pip `--constraint` file pinning EVERY platform package to its
    exact version. A constraint file may not carry extras, so keys are bare
    canonical names (`uvicorn==0.34.0`, not `uvicorn[standard]==...`). Constraints
    only take effect for packages pip actually touches, so this never forces an
    unused package to install — it just forbids a platform package (Pydantic above
    all) from drifting while the missing extras resolve."""
    return "\n".join(f"{name}=={ver}" for name, ver in sorted(PLATFORM_PINS.items())) + "\n"


# ---------------------------------------------------------------- Next.js prerender
# D4 (projects 274 / 342 / 860): a generated App-Router page that is a client
# component using `useSearchParams()` (or otherwise touching request-time state)
# THROWS while `next build` statically prerenders it — "useSearchParams() should be
# wrapped in a suspense boundary" -> "Error occurred prerendering page '/integrate'"
# — which fails the whole frontend image build (project 860 died exactly here at the
# deploy step, on Next 15).
#
# ⚠️ The ORIGINALLY-documented fix — inject `export const dynamic = "force-dynamic"`
# into the PAGE files — was proven WRONG for this Next.js version (15): route-segment
# config is IGNORED in Client Components, and every generated `page.tsx` here is
# `"use client"`, so the injected export does nothing and `next build` still fails.
# Verified with a real build (a client page using useSearchParams fails identically
# WITH and WITHOUT the page-level export). Do NOT reintroduce the page-level approach.
#
# The mechanism that actually works (verified with a real `next build`): export
# `dynamic = "force-dynamic"` from the ROOT SERVER `layout.tsx`. A server layout DOES
# honour route-segment config, and the root layout's config cascades to every route,
# so the whole app renders dynamically and no page is ever prerendered. We inject it
# there, deterministically, wherever the frontend is materialised for a build (the
# deploy image AND QA's opt-in `next build`).
_LAYOUT_BASENAMES = {"layout.tsx", "layout.jsx", "layout.ts", "layout.js"}
_FORCE_DYNAMIC_EXPORT = 'export const dynamic = "force-dynamic";'
_HAS_DYNAMIC_RE = re.compile(r"export\s+const\s+dynamic\b")


def _is_next_root_layout(rel: str) -> bool:
    """The ROOT App-Router layout (`app/layout.*`) — the one whose route-segment
    config cascades to every route. A nested segment layout (`app/admin/layout.*`)
    is NOT the root and is left alone; forcing the root dynamic already covers it."""
    p = "/" + (rel or "").replace("\\", "/").lstrip("/")
    parts = [seg for seg in p.split("/") if seg]
    return (os.path.basename(p) in _LAYOUT_BASENAMES
            and len(parts) >= 2 and parts[-2] == "app")


def _is_client_component(content: str) -> bool:
    """A module whose first statement is a `"use client"` directive."""
    head = (content or "").lstrip()
    return head.startswith('"use client"') or head.startswith("'use client'")


def force_dynamic_layout(rel: str, content: str) -> str:
    """Inject `export const dynamic = "force-dynamic"` into the generated ROOT
    Next.js layout so the whole app renders dynamically and `next build` never
    prerenders a page (D4). Prepended at the top; ES-module imports hoist, so this
    is valid ahead of the layout's own imports (verified with a real build).

    Skips (returns content unchanged):
      * any file that is not the root `app/layout.*`;
      * a root layout that is itself a CLIENT component — route config is ignored
        there, the exact reason the old page-level fix failed, so injecting would be
        a silent no-op we must not pretend fixes the build;
      * a layout that already exports `dynamic` (respect an explicit author choice).
    """
    if (not _is_next_root_layout(rel)
            or _is_client_component(content)
            or _HAS_DYNAMIC_RE.search(content or "")):
        return content
    return _FORCE_DYNAMIC_EXPORT + "\n" + (content or "")


def needs_email_validator(contents) -> bool:
    """Pydantic's `EmailStr` (and `pydantic[email]`) require the separate
    `email-validator` package. It is triggered by the field TYPE and referenced by
    NO import statement, so the AST import scan never sees it and the app dies at
    startup with "email-validator is not installed". Detect the usage directly so
    both the QA venv AND the deployed image include it. (Reproduced by project 487,
    2026-08-10 — the app built and passed security review, then would not boot.)"""
    for c in contents:
        if c and ("EmailStr" in c or "pydantic[email]" in c):
            return True
    return False


def needs_python_multipart(contents) -> bool:
    """FastAPI needs the separate `python-multipart` package whenever a route takes
    form/file data (an `UploadFile` annotation, or a `File(...)` / `Form(...)`
    default). It's triggered by that USAGE, not by any import statement, so the AST
    scan misses it and the app dies at startup with 'Form data requires
    "python-multipart" to be installed'. Detect the usage directly so both the QA
    venv AND the deployed image include it. (Reproduced by project 661, 2026-08-11 —
    the menu PDF upload endpoint.)"""
    for c in contents:
        if c and ("UploadFile" in c or "File(" in c or "Form(" in c
                  or "multipart/form-data" in c):
            return True
    return False

# NOTE: this used to be a regex. It was wrong: `import\s+([A-Za-z0-9_.,\s]+)`
# put \s inside the character class, so a leading `import os` greedily swallowed
# every following import line and QA tried to `pip install 'HTTPException'`.
# That made QA fabricate "hallucinated dependency" findings and burn all 3
# retries on a bug that did not exist. Parse the real syntax tree instead.


@dataclass
class Failure:
    """An assembly problem, shaped like a QA finding."""
    test_name: str
    reason: str


@dataclass
class TestEnv:
    """Handle for a running (or failed) throwaway instance."""
    ok: bool = False
    base_url: str | None = None
    root: str | None = None
    port: int | None = None
    process: subprocess.Popen | None = None
    db_name: str | None = None
    failures: list[Failure] = field(default_factory=list)
    # filepath -> content, for the static frontend checks and root-cause tracing.
    files: dict[str, str] = field(default_factory=dict)
    # ticket_id per filepath, so a failure can be traced back to its ticket.
    ticket_of: dict[str, str] = field(default_factory=dict)
    logs: str = ""
    # Structured third-party import findings (run 1496): a `from <pkg> import Y`
    # where <pkg> is installed but Y/the submodule does not exist. Populated by
    # `_third_party_import_errors`; consumed by the build-stage bounded repair.
    import_errors: list[dict] = field(default_factory=list)
    # Designed endpoints missing from the BOOTED app (run 1557: GET /orders/{order_id}
    # was never generated). Populated by `_check_designed_endpoints`; consumed by the
    # build-stage bounded repair (orchestrator.repair_missing_endpoints).
    missing_endpoints: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ helpers
def _free_port() -> int:
    """Ask the OS for a free port, then let the child bind it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((TEST_HOST, 0))
        return s.getsockname()[1]


def _safe_relpath(filepath: str, filename: str) -> str | None:
    """Reject path traversal / absolute paths — file contents are LLM output."""
    raw = (filepath or filename or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts) if parts else None


def _third_party_imports(code: str) -> set[str]:
    """Top-level import roots that look like installable packages.

    Uses the AST so multi-line and parenthesised imports are read correctly and
    imported NAMES are never mistaken for package names. Relative imports
    (`from .models import X`) are local, not installable, so they are skipped.
    A file that will not parse returns nothing — the syntax error is already
    reported as its own finding by `_syntax_check`.
    """
    found: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return found

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".")[0]
                if root and root not in _STDLIB_SKIP:
                    found.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # relative import -> local module
                continue
            root = (node.module or "").split(".")[0]
            if root and root not in _STDLIB_SKIP:
                found.add(root)
    return found


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60,
         env: dict | None = None, stdin: str | None = None) -> tuple[int, str]:
    """Run a command, capture combined output, never raise on failure."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, timeout=timeout, env=env, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {timeout}s"
    except Exception as exc:  # pragma: no cover - defensive
        return -1, str(exc)


# ------------------------------------------------------------------ steps
def _write_files(root: str, files: list[dict]) -> tuple[dict[str, str], dict[str, str], list[Failure]]:
    """Write generated files into the temp dir, preserving module layout."""
    written: dict[str, str] = {}
    ticket_of: dict[str, str] = {}
    failures: list[Failure] = []

    for f in files:
        rel = _safe_relpath(f.get("filepath", ""), f.get("filename", ""))
        if rel is None:
            failures.append(Failure(
                "assembly: unsafe file path",
                f"Generated file '{f.get('filename')}' has an unusable or unsafe "
                f"path '{f.get('filepath')}' and was not written.",
            ))
            continue
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # D4: force the app dynamic via the root server layout so QA's opt-in
        # `next build` (and anything reading this temp dir) matches the deploy image.
        content = force_dynamic_layout(rel, f.get("content") or "")
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(content)
            written[rel] = content
            ticket_of[rel] = f.get("ticket_id") or ""
        except OSError as exc:
            failures.append(Failure("assembly: could not write file",
                                    f"{rel}: {exc}"))

    # Python packages need __init__.py to import cleanly.
    for rel in list(written):
        if rel.endswith(".py"):
            parts = rel.split("/")[:-1]
            for i in range(len(parts)):
                pkg = os.path.join(root, *parts[: i + 1], "__init__.py")
                if not os.path.exists(pkg):
                    os.makedirs(os.path.dirname(pkg), exist_ok=True)
                    open(pkg, "w").close()
    return written, ticket_of, failures


def _syntax_check(root: str, written: dict[str, str]) -> list[Failure]:
    """Compile every generated .py file — a syntax error is a real QA finding."""
    failures: list[Failure] = []
    for rel, content in written.items():
        if not rel.endswith(".py"):
            continue
        try:
            compile(content, rel, "exec")
        except SyntaxError as exc:
            failures.append(Failure(
                f"assembly: syntax error in {rel}",
                f"{rel} line {exc.lineno}: {exc.msg}",
            ))
        except Exception as exc:  # pragma: no cover - defensive
            failures.append(Failure(f"assembly: could not parse {rel}", str(exc)))
    return failures


def _make_venv(root: str) -> tuple[str, list[Failure]]:
    """venv that inherits the platform's site-packages (fastapi, sqlalchemy…
    are already installed) so we only fetch what's genuinely missing."""
    venv_dir = os.path.join(root, ".qa-venv")
    code, out = _run([sys.executable, "-m", "venv", "--system-site-packages", venv_dir],
                     timeout=120)
    if code != 0:
        return venv_dir, [Failure("assembly: could not create test environment", out[-800:])]
    return venv_dir, []


def _venv_python(venv_dir: str) -> str:
    exe = os.path.join(venv_dir, "bin", "python")
    return exe if os.path.exists(exe) else sys.executable


def _install_deps(venv_dir: str, written: dict[str, str]) -> list[Failure]:
    """Install third-party imports the platform doesn't already provide.

    Every install goes through a pip `--constraint` file pinning the platform
    stack (`platform_constraints_text()`), and each missing package is itself
    pinned to the platform version where we know one (`pin_spec`). This makes the
    throwaway venv boot under the SAME dependency versions as the deployed image
    and as every other assemble() — so smoke_boot can never green-light code that
    only "boots" because it happened to get an older Pydantic (project 829)."""
    wanted: set[str] = set()
    for rel, content in written.items():
        if rel.endswith(".py"):
            wanted |= _third_party_imports(content)

    py = _venv_python(venv_dir)
    missing = []
    for mod in sorted(wanted):
        code, _ = _run([py, "-c", f"import {mod}"], timeout=30)
        if code != 0:
            missing.append(_PACKAGE_ALIASES.get(mod, mod))
    # EmailStr needs the email-validator extra, which no import statement names.
    if needs_email_validator(written.values()) and "email-validator" not in missing:
        missing.append("email-validator")
    # File/Form routes need python-multipart, also not named by any import.
    if needs_python_multipart(written.values()) and "python-multipart" not in missing:
        missing.append("python-multipart")

    # A --constraint file pins the platform stack even when a MISSING package's
    # transitive deps would otherwise pull a different Pydantic/etc. into the venv.
    # It is written unconditionally so the SAME environment is asserted whether or
    # not there is anything to install.
    constraints_path = os.path.join(venv_dir, "platform-constraints.txt")
    try:
        with open(constraints_path, "w", encoding="utf-8") as fh:
            fh.write(platform_constraints_text())
    except OSError:  # pragma: no cover - defensive
        constraints_path = None

    if not missing:
        return []

    # Pin each missing package to the platform version where we have one; unknown
    # extras (pdfplumber, python-jose, …) install latest but cannot move a pinned
    # platform package because of the constraint file.
    to_install = [pin_spec(m) for m in missing]
    cmd = [py, "-m", "pip", "install", "--no-input", "--disable-pip-version-check"]
    if constraints_path:
        cmd += ["--constraint", constraints_path]
    cmd += to_install
    code, out = _run(cmd, timeout=settings.qa_install_timeout)
    if code != 0:
        # A dependency that cannot be installed is very often a HALLUCINATED
        # import — exactly the class of bug QA exists to catch.
        return [Failure(
            "assembly: dependency install failed",
            f"Could not install {', '.join(missing)}. This usually means the "
            f"generated code imports a package that does not exist. "
            f"Installer output: {out[-600:]}",
        )]
    return []


# In-project roots — resolved by Fix #16 (import_symbol_mismatches), NOT here.
_IN_PROJECT_ROOTS = {"backend", "app"}

# A probe (run in the VENV, where the app's real deps ARE installed) that, for each
# `from <module> import <names>`, confirms the module imports and each name exists.
# Only reports a THIRD-PARTY package that IS installed but whose SUBMODULE/NAME the
# generated code guessed wrong (run 1496: `from stripe.api_resources import
# PaymentIntent` — the real path is `from stripe import PaymentIntent`). A package
# that is not installed at all is _install_deps' domain, so its root is skipped here.
_IMPORT_PROBE = r'''
import importlib, json, sys
out = []
for item in json.load(sys.stdin):
    mod, names = item["module"], item["names"]
    root = mod.split(".")[0]
    try:
        rootmod = importlib.import_module(root)
    except Exception:
        continue                      # package not installed -> not our finding
    try:
        m = importlib.import_module(mod)
    except ModuleNotFoundError as ex:
        # Only OUR finding when the MISSING module is the path itself (or a parent) —
        # NOT a transitive dependency. `starlette.middleware.sessions` is a real module
        # that raises ModuleNotFoundError('itsdangerous') when that optional dep is
        # absent: a wrong-dep problem, not a wrong path. Skip those (zero false positive).
        miss = getattr(ex, "name", "") or ""
        if miss and (miss == mod or mod.startswith(miss + ".")):
            avail = [n for n in names if n != "*" and hasattr(rootmod, n)]
            out.append({"module": mod, "kind": "no_submodule",
                        "names": names, "root": root, "on_root": avail})
        continue
    except Exception:
        continue                      # some other import-time error -> don't guess
    # A name that is neither an attribute NOR an importable submodule is missing.
    # `from jose import jwt` / `from stripe import checkout` import a SUBMODULE that
    # `import jose` does not auto-load, so hasattr() alone would false-positive.
    missing = []
    for n in names:
        if n == "*" or hasattr(m, n):
            continue
        try:
            importlib.import_module(mod + "." + n)
        except Exception:
            missing.append(n)
    if missing:
        out.append({"module": mod, "kind": "no_attr", "names": missing, "root": root})
print(json.dumps(out))
'''


def _third_party_import_candidates(written: dict[str, str]) -> list[dict]:
    """(file, line, module, names) for every `from <third-party> import ...` — skips
    in-project (backend/app), stdlib, relative, and bare `import x`. NAMES exclude
    aliases-as-written but keep the real attribute names."""
    out: list[dict] = []
    for rel, content in written.items():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            root = node.module.split(".")[0]
            if root in _IN_PROJECT_ROOTS or root in _STDLIB_SKIP:
                continue
            names = [a.name for a in node.names if a.name != "*"]
            if not names:
                continue
            out.append({"file": rel, "line": node.lineno,
                        "module": node.module, "names": names})
    return out


def _third_party_import_errors(venv_dir: str, written: dict[str, str]) -> list[dict]:
    """Structured findings for wrong third-party import PATHS/SYMBOLS, verified in the
    venv. Each: {file, line, module, kind, names, root, on_root?}. Empty when clean or
    when the probe cannot run (never a false positive). Zero-FP: only an INSTALLED
    package with a wrong submodule/name is flagged."""
    candidates = _third_party_import_candidates(written)
    if not candidates:
        return []
    # De-dupe module -> union(names) for the probe; keep per-occurrence for findings.
    by_module: dict[str, set] = {}
    for c in candidates:
        by_module.setdefault(c["module"], set()).update(c["names"])
    probe_input = json.dumps([{"module": m, "names": sorted(ns)}
                              for m, ns in by_module.items()])
    code, out = _run([_venv_python(venv_dir), "-c", _IMPORT_PROBE, ], timeout=60,
                     stdin=probe_input)
    if code != 0 or not out.strip():
        return []
    try:
        problems = {p["module"]: p for p in json.loads(out.strip().splitlines()[-1])}
    except (ValueError, KeyError):
        return []
    findings: list[dict] = []
    for c in candidates:
        p = problems.get(c["module"])
        if not p:
            continue
        if p["kind"] == "no_submodule":
            findings.append({**c, "kind": "no_submodule",
                             "root": p["root"], "on_root": p.get("on_root", [])})
        else:
            bad = [n for n in c["names"] if n in set(p["names"])]
            if bad:
                findings.append({**c, "kind": "no_attr", "root": p["root"], "names": bad})
    return findings


def _import_error_reason(e: dict) -> str:
    """Human/agent-readable reason for one third-party import finding."""
    names = ", ".join(e.get("names") or [])
    if e["kind"] == "no_submodule":
        sug = (f" Import {'/'.join(e['on_root'])} directly from `{e['root']}` "
               f"(e.g. `from {e['root']} import {(e.get('on_root') or [names])[0]}`)."
               if e.get("on_root") else
               f" `{e['module']}` is not a real submodule of `{e['root']}`.")
        return (f"{e['file']} line {e.get('line')}: `from {e['module']} import {names}` — "
                f"the submodule `{e['module']}` does not exist.{sug}")
    return (f"{e['file']} line {e.get('line')}: `{e['module']}` has no {names} — that "
            f"name is not exported by the installed `{e['root']}` package.")


def _find_app_module(written: dict[str, str]) -> str | None:
    """Locate the FastAPI entrypoint and return its FULL dotted module path
    relative to the assembly root (e.g. 'backend.app.main').

    The full path is used — not a 'backend'-stripped one — because generated
    code mixes both import styles: the binding contract says `from app.models
    import X`, but agents also emit `from backend.app.database import get_db`.
    Running from the root with BOTH the root and root/backend on PYTHONPATH
    (see `_python_path`) makes both styles resolve.
    """
    candidates = [r for r in written if r.endswith(".py") and "FastAPI(" in written[r]]
    if not candidates:
        return None
    # Prefer the conventional backend/app/main.py from the binding contract.
    candidates.sort(key=lambda r: (not r.endswith("app/main.py"), len(r)))
    return candidates[0][:-3].replace("/", ".")


def _python_path(root: str) -> str:
    """ONLY the assembly root.

    It is tempting to also add root/backend so the contract's `app.x` style
    resolves alongside `backend.app.x`. Do not: two search paths make the same
    file importable under two names, Python executes it twice, and SQLAlchemy
    dies with "Table 'users' is already defined for this MetaData instance".
    The two styles are reconciled by ALIASING instead (see `_write_alias_hook`),
    which keeps a single module object.
    """
    return root


def _write_alias_hook(root: str, module: str) -> None:
    """Make `app.x` and `backend.app.x` the SAME module.

    Generated files genuinely mix both import styles (the entrypoint used
    `from app.models`, the routers used `from backend.app.models`). Aliasing
    them to one module object is what lets a mixed-style build run at all.
    `sitecustomize` is imported automatically at interpreter start, and root is
    on sys.path, so this installs before any app code runs.
    """
    top = module.split(".")[0]
    real_pkg = ".".join(module.split(".")[:-1]) or top     # e.g. backend.app
    alias = "app" if real_pkg != "app" else "backend.app"
    if real_pkg == alias:
        return

    hook = f'''"""QA test-harness shim: alias {alias}.* -> {real_pkg}.* (single module identity)."""
import importlib
import importlib.abc
import importlib.machinery
import sys

_ALIAS = {alias!r}
_REAL = {real_pkg!r}


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == _ALIAS or fullname.startswith(_ALIAS + "."):
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        real = _REAL + spec.name[len(_ALIAS):]
        mod = importlib.import_module(real)
        sys.modules[spec.name] = mod
        return mod

    def exec_module(self, module):
        return None


sys.meta_path.insert(0, _AliasFinder())
'''
    with open(os.path.join(root, "sitecustomize.py"), "w", encoding="utf-8") as fh:
        fh.write(hook)


async def _provision_db(db_name: str) -> tuple[str | None, list[Failure]]:
    """Throwaway Postgres database on the platform's own instance, dropped on
    teardown. Without a DB nearly every endpoint 500s and QA results are noise."""
    base = settings.database_url
    try:
        import asyncpg  # noqa: F401
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text as sql_text

        admin = create_async_engine(base, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            await conn.execute(sql_text(f'CREATE DATABASE "{db_name}"'))
        await admin.dispose()
    except Exception as exc:
        return None, [Failure("assembly: could not create test database", str(exc)[:400])]

    url = re.sub(r"/[^/?]+(\?|$)", f"/{db_name}\\1", base, count=1)
    return url, []


async def _drop_db(db_name: str) -> None:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text as sql_text

        admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            await conn.execute(sql_text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}'"
            ))
            await conn.execute(sql_text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()
    except Exception:  # pragma: no cover - best effort cleanup
        logger.warning("Could not drop QA test database %s", db_name)


def _create_tables(venv_dir: str, root: str, module: str, db_url: str,
                   extra_env: dict | None = None) -> None:
    """Best effort: import the generated models and create their tables.

    Tries both import styles, since generated code uses either.
    """
    pkg = module.rsplit(".", 1)[0] if "." in module else ""      # e.g. backend.app
    candidates = [c for c in (pkg, "app", "backend.app") if c]
    boot = (
        "import asyncio, importlib\n"
        f"cands = {candidates!r}\n"
        "db = None\n"
        "for c in cands:\n"
        "    try:\n"
        "        db = importlib.import_module(c + '.database')\n"
        "        importlib.import_module(c + '.models')\n"
        "        break\n"
        "    except Exception:\n"
        "        db = None\n"
        "if db is None:\n"
        "    print('no-models'); raise SystemExit(0)\n"
        "async def go():\n"
        "    eng = getattr(db, 'engine', None)\n"
        "    Base = getattr(db, 'Base', None)\n"
        "    if eng is None or Base is None: return\n"
        "    async with eng.begin() as c:\n"
        "        await c.run_sync(Base.metadata.create_all)\n"
        "asyncio.run(go())\n"
    )
    env = {**os.environ, **(extra_env or {}), **_TEST_ENV, "DATABASE_URL": db_url,
           "PYTHONPATH": _python_path(root)}
    _run([_venv_python(venv_dir), "-c", boot], cwd=root, timeout=60, env=env)


async def _wait_healthy(base_url: str, proc: subprocess.Popen, timeout: int) -> bool:
    """Poll until the app answers anything (or dies)."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(timeout=3) as client:
        while asyncio.get_event_loop().time() < deadline:
            if proc.poll() is not None:
                return False  # process exited
            for path in ("/health", "/openapi.json", "/"):
                try:
                    r = await client.get(f"{base_url}{path}")
                    if r.status_code < 500:
                        return True
                except Exception:
                    pass
            await asyncio.sleep(0.5)
    return False


# ------------------------------------------------------------------ entrypoint
def _norm_path(path: str) -> str:
    """`/orders/{order_id}` and `/orders/{id}` are the same route shape."""
    return re.sub(r"\{[^}]*\}", "{}", (path or "").rstrip("/")) or "/"


async def _check_designed_endpoints(base_url: str, expected: list[str]
                                    ) -> tuple[list[Failure], list[str]]:
    """A partially-booted app is a FAILED assembly, not a passing test run.

    Generated entrypoints tend to guard router imports; a broken router then gets
    skipped and the app still starts, so QA would happily test the two endpoints
    that survived and report "mostly passing" on an app whose payment routes were
    never loaded. Compare what booted against what the Architect designed.
    """
    if not expected:
        return [], []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base_url}/openapi.json")
            spec = r.json() if r.status_code == 200 else {}
    except Exception as exc:
        return [Failure("assembly: app's API is unreadable", str(exc)[:300])], []

    live = {_norm_path(p) for p in (spec.get("paths") or {})}
    missing = [p for p in expected if _norm_path(p) not in live]
    if not missing:
        return [], []
    return [Failure(
        "assembly: designed features are missing from the running app",
        f"The app started but {len(missing)} of {len(expected)} designed "
        f"endpoints are not there: {', '.join(missing[:8])}. This usually means "
        f"a module failed to import and was silently skipped, so those features "
        f"would be untested and unavailable.",
    )], missing


async def assemble(files: list[dict],
                   expected_endpoints: list[str] | None = None) -> TestEnv:
    """Build and boot a throwaway instance. NEVER raises — assembly problems
    come back as `env.failures` so the QA agent can log them as findings.

    `expected_endpoints` are the blueprint's designed paths; if the booted app is
    missing any, assembly is treated as FAILED (env.ok stays False).
    """
    env = TestEnv()
    if not files:
        env.failures.append(Failure("assembly: nothing to test",
                                    "No generated files were found for this project."))
        return env

    try:
        env.root = tempfile.mkdtemp(prefix="qa-build-")
        written, ticket_of, fails = _write_files(env.root, files)
        env.files, env.ticket_of = written, ticket_of
        env.failures.extend(fails)

        # Throwaway values for any env vars the generated code fail-fast requires
        # but _TEST_ENV doesn't cover — so a CORRECT fail-fast app can boot here.
        auto_env = _discover_required_env(files)

        env.failures.extend(_syntax_check(env.root, written))

        module = _find_app_module(written)
        if module is None:
            env.failures.append(Failure(
                "assembly: no runnable app found",
                "None of the generated backend files create a FastAPI application, "
                "so there is nothing to start and test.",
            ))
            return env

        # Reconcile the two import styles BEFORE anything imports app code.
        _write_alias_hook(env.root, module)

        venv_dir, fails = _make_venv(env.root)
        env.failures.extend(fails)
        if fails:
            return env

        inst_fails = _install_deps(venv_dir, written)
        env.failures.extend(inst_fails)

        # Third-party import symbol gate (run 1496): with the real deps now installed,
        # catch a `from <pkg> import Y` whose submodule/name doesn't exist (the LLM
        # guessed an internal path) — a PRECISE, deterministic finding instead of a
        # 45s boot crash. Skipped when an install already failed (that is a different,
        # missing-package finding). A hit means the app cannot import, so stop here.
        if not inst_fails:
            env.import_errors = _third_party_import_errors(venv_dir, written)
            for e in env.import_errors:
                env.failures.append(Failure(
                    f"assembly: bad third-party import in {e['file']}",
                    _import_error_reason(e)))
            if env.import_errors:
                return env

        env.db_name = f"qa_test_{secrets.token_hex(6)}"
        db_url, fails = await _provision_db(env.db_name)
        if fails:
            env.failures.extend(fails)
            env.db_name = None
            db_url = settings.database_url
        else:
            _create_tables(venv_dir, env.root, module, db_url, extra_env=auto_env)

        # Launch on a random free port, bound to loopback only.
        env.port = _free_port()
        env.base_url = f"http://{TEST_HOST}:{env.port}"
        workdir = env.root
        child_env = {
            **os.environ,
            **auto_env,           # scanned fail-fast-required secrets (gap-fill)
            **_TEST_ENV,          # curated provider config (wins over auto_env)
            "DATABASE_URL": db_url,
            "PYTHONPATH": _python_path(env.root),
        }
        log_path = os.path.join(env.root, "qa-app.log")
        log_fh = open(log_path, "w")
        env.process = subprocess.Popen(
            [_venv_python(venv_dir), "-m", "uvicorn", f"{module}:app",
             "--host", TEST_HOST, "--port", str(env.port), "--log-level", "warning"],
            cwd=workdir, env=child_env, stdout=log_fh, stderr=subprocess.STDOUT,
        )

        healthy = await _wait_healthy(env.base_url, env.process, settings.qa_boot_timeout)
        try:
            log_fh.close()
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                env.logs = fh.read()[-4000:]
        except OSError:
            env.logs = ""

        if not healthy:
            env.failures.append(Failure(
                "assembly: app did not start",
                f"The generated app failed to start within "
                f"{settings.qa_boot_timeout}s. Startup output: {env.logs[-800:] or '(none)'}",
            ))
            return env

        # Booted — but a partially-loaded app must NOT be reported as healthy.
        ep_fails, missing_eps = await _check_designed_endpoints(
            env.base_url, expected_endpoints or [])
        if ep_fails:
            env.failures.extend(ep_fails)
            env.missing_endpoints = missing_eps
            return env      # ok stays False: this is a failed assembly

        env.ok = True
        return env
    except Exception as exc:  # pragma: no cover - QA must never crash
        logger.exception("QA assembly failed")
        env.failures.append(Failure("assembly: unexpected error", str(exc)[:500]))
        return env


async def teardown(env: TestEnv) -> None:
    """Always called, pass or fail. Nothing survives a QA run."""
    if env.process is not None and env.process.poll() is None:
        env.process.terminate()
        try:
            env.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            env.process.kill()
    if env.db_name:
        await _drop_db(env.db_name)
    if env.root and os.path.isdir(env.root):
        shutil.rmtree(env.root, ignore_errors=True)
