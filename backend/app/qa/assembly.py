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
import asyncio
import logging
import os
import re
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
}

_IMPORT_RE = re.compile(r"^\s*(?:from\s+([A-Za-z0-9_.]+)|import\s+([A-Za-z0-9_.,\s]+))",
                        re.MULTILINE)


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
    """Top-level import roots that look like installable packages."""
    found: set[str] = set()
    for from_mod, import_mod in _IMPORT_RE.findall(code):
        mods = [from_mod] if from_mod else import_mod.split(",")
        for m in mods:
            root = m.strip().split(".")[0].split(" as ")[0].strip()
            if root and not root.startswith(".") and root not in _STDLIB_SKIP:
                found.add(root)
    return found


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 60,
         env: dict | None = None) -> tuple[int, str]:
    """Run a command, capture combined output, never raise on failure."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, timeout=timeout, env=env,
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
        content = f.get("content") or ""
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
    """Install third-party imports the platform doesn't already provide."""
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
    if not missing:
        return []

    code, out = _run([py, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                      *missing], timeout=settings.qa_install_timeout)
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


def _find_app_module(written: dict[str, str]) -> tuple[str | None, str | None]:
    """Locate the FastAPI entrypoint -> (import path, working dir prefix)."""
    candidates = [r for r in written if r.endswith(".py") and "FastAPI(" in written[r]]
    if not candidates:
        return None, None
    # Prefer the conventional backend/app/main.py from the binding contract.
    candidates.sort(key=lambda r: (not r.endswith("app/main.py"), len(r)))
    rel = candidates[0]

    # Run with cwd = the dir ABOVE the top package so `app.main` resolves like
    # it does in the real project layout.
    parts = rel[:-3].split("/")
    if parts[0] == "backend":
        return ".".join(parts[1:]), "backend"
    return ".".join(parts), ""


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


def _create_tables(venv_dir: str, root: str, cwd_prefix: str, db_url: str) -> None:
    """Best effort: import the generated models and create their tables."""
    boot = (
        "import asyncio, importlib, pkgutil, sys\n"
        "mods = []\n"
        "for m in list(sys.modules): pass\n"
        "try:\n"
        "    db = importlib.import_module('app.database')\n"
        "    importlib.import_module('app.models')\n"
        "except Exception as e:\n"
        "    print('no-models', e); raise SystemExit(0)\n"
        "async def go():\n"
        "    eng = getattr(db, 'engine', None)\n"
        "    Base = getattr(db, 'Base', None)\n"
        "    if eng is None or Base is None: return\n"
        "    async with eng.begin() as c:\n"
        "        await c.run_sync(Base.metadata.create_all)\n"
        "asyncio.run(go())\n"
    )
    env = {**os.environ, "DATABASE_URL": db_url, "PYTHONPATH": os.path.join(root, cwd_prefix)}
    _run([_venv_python(venv_dir), "-c", boot],
         cwd=os.path.join(root, cwd_prefix), timeout=60, env=env)


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
async def assemble(files: list[dict]) -> TestEnv:
    """Build and boot a throwaway instance. NEVER raises — assembly problems
    come back as `env.failures` so the QA agent can log them as findings."""
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

        env.failures.extend(_syntax_check(env.root, written))

        module, cwd_prefix = _find_app_module(written)
        if module is None:
            env.failures.append(Failure(
                "assembly: no runnable app found",
                "None of the generated backend files create a FastAPI application, "
                "so there is nothing to start and test.",
            ))
            return env

        venv_dir, fails = _make_venv(env.root)
        env.failures.extend(fails)
        if fails:
            return env

        env.failures.extend(_install_deps(venv_dir, written))

        env.db_name = f"qa_test_{secrets.token_hex(6)}"
        db_url, fails = await _provision_db(env.db_name)
        if fails:
            env.failures.extend(fails)
            env.db_name = None
            db_url = settings.database_url
        else:
            _create_tables(venv_dir, env.root, cwd_prefix, db_url)

        # Launch on a random free port, bound to loopback only.
        env.port = _free_port()
        env.base_url = f"http://{TEST_HOST}:{env.port}"
        workdir = os.path.join(env.root, cwd_prefix) if cwd_prefix else env.root
        child_env = {
            **os.environ,
            "DATABASE_URL": db_url,
            "PYTHONPATH": workdir,
            # Generated apps read secrets from env per the binding contract.
            "SECRET_KEY": "qa-test-secret",
            "STRIPE_TOKEN_ENC_KEY": "qa-test-enc-key-0123456789abcdef",
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
