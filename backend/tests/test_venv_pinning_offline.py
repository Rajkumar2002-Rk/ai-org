"""Gate integrity: the smoke_boot / QA venv is version-PINNED and IDENTICAL to
the deployed image's environment (project 829, 2026-08-12).

Project 829 booted clean at the smoke_boot gate, passed the paid Opus review, then
FAIL-booted at QA on the SAME files: generated `order.py` used the Pydantic v1
spelling `conlist(OrderItem, min_items=1)`, which raises TypeError at import under
Pydantic v2. The bug was in the one and only version of order.py the whole time
(never regenerated) — so the gate did not leak because it ran too few times, it
leaked because the throwaway venv's dependency versions were not pinned and not
guaranteed to match either the deploy or QA. A gate that boots under a DIFFERENT
Pydantic than the deploy can green-light un-bootable code.

The fix makes the platform's own tested `requirements.txt` the SINGLE source of
truth that both the QA/smoke_boot venv (a pip `--constraint` file, in
`assembly._install_deps`) and the deployed image (`manifest._backend_requirements`)
install from. This suite proves the two environments are IDENTICAL, not merely
similar, and that under the pinned Pydantic the exact 829 defect is caught.

Zero LLM spend, no venv/boot, no network — pure function + source assertions.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_venv_pinning_offline.py
"""
import inspect
import os
import sys

import app
from app.qa import assembly
from app.devops import manifest

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def _pinned_map(text: str) -> dict[str, str]:
    """Parse `name==version` lines (ignoring comments/extras) into {canon: ver}."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" not in line:
            continue
        name, _, ver = line.partition("==")
        out[assembly._canon(name)] = ver.strip()
    return out


def test_platform_pins_are_real():
    """PLATFORM_PINS is parsed from the real requirements.txt and reflects the
    versions actually installed in the container — otherwise the pin is a fiction."""
    import pydantic

    pins = assembly.PLATFORM_PINS
    check("PLATFORM_PINS is non-empty (requirements.txt was found + parsed)", bool(pins),
          str(pins))
    for pkg in ("pydantic", "fastapi", "sqlalchemy", "uvicorn"):
        check(f"PLATFORM_PINS pins {pkg}", pkg in pins, str(sorted(pins)))
    # The pinned Pydantic version must equal what is actually importable here — the
    # container is built from this same requirements.txt, so they cannot disagree.
    check("pinned Pydantic == the Pydantic actually installed in the container",
          pins.get("pydantic") == pydantic.VERSION,
          f"pinned={pins.get('pydantic')} installed={pydantic.VERSION}")


def test_pin_spec():
    """pin_spec pins platform packages, preserves extras, and leaves the rest alone."""
    pins = assembly.PLATFORM_PINS
    pyd = pins["pydantic"]
    uvi = pins["uvicorn"]

    check("pin_spec('pydantic') pins to the platform version",
          assembly.pin_spec("pydantic") == f"pydantic=={pyd}",
          assembly.pin_spec("pydantic"))
    check("pin_spec preserves extras: uvicorn[standard] -> ...==<ver>",
          assembly.pin_spec("uvicorn[standard]") == f"uvicorn[standard]=={uvi}",
          assembly.pin_spec("uvicorn[standard]"))
    check("pin_spec canonicalises case: SQLAlchemy is pinned",
          assembly.pin_spec("SQLAlchemy") == f"SQLAlchemy=={pins['sqlalchemy']}",
          assembly.pin_spec("SQLAlchemy"))
    check("pin_spec leaves an unknown extra unpinned (pdfplumber)",
          assembly.pin_spec("pdfplumber") == "pdfplumber",
          assembly.pin_spec("pdfplumber"))
    check("pin_spec does not double-pin an already-qualified spec",
          assembly.pin_spec("pydantic==9.9.9") == "pydantic==9.9.9")


def test_constraints_file():
    """The pip --constraint body pins the platform stack, carries NO extras (pip
    forbids them in a constraint file), and includes Pydantic explicitly."""
    body = assembly.platform_constraints_text()
    pyd = assembly.PLATFORM_PINS["pydantic"]
    check("constraint body pins Pydantic to the platform version",
          f"pydantic=={pyd}" in body, body)
    check("constraint body carries NO extras ('[' would make pip reject it)",
          "[" not in body, body)
    for pkg in ("fastapi", "sqlalchemy", "uvicorn"):
        check(f"constraint body pins {pkg}", any(
            line.split("==")[0].strip() == pkg for line in body.splitlines() if "==" in line), body)


def test_pinned_pydantic_catches_the_829_bug():
    """Under the PINNED Pydantic (v2), the exact 829 call site fails — so a gate
    that boots under this version WILL reject `min_items`, deterministically. This
    is the whole point: pin the version, and the defect can no longer sneak past."""
    from pydantic import conlist

    check("pinned Pydantic is v2.x (matches the pin)",
          assembly.PLATFORM_PINS["pydantic"].startswith("2."),
          assembly.PLATFORM_PINS["pydantic"])
    raised = False
    try:
        conlist(int, min_items=1)          # the 829 spelling
    except TypeError:
        raised = True
    check("conlist(min_items=1) raises TypeError under the pinned Pydantic (829 bug)",
          raised)
    ok = True
    try:
        conlist(int, min_length=1)         # the v2 spelling the prompt now mandates
    except TypeError:
        ok = False
    check("conlist(min_length=1) is accepted under the pinned Pydantic", ok)


# A representative backend app: a FastAPI entrypoint plus a route that imports an
# unpinned extra (pdfplumber) and a platform package (pydantic) and uses conlist —
# exactly the shape of the 829 build.
_FILES = [
    {"filepath": "backend/app/main.py", "ticket_id": "APP-1", "agent_type": "backend",
     "content": "from fastapi import FastAPI\n"
                "from backend.app.routes.order import router\n"
                "app = FastAPI()\napp.include_router(router)\n"},
    {"filepath": "backend/app/routes/order.py", "ticket_id": "BE-1", "agent_type": "backend",
     "content": "import pdfplumber\n"
                "from jose import jwt\n"
                "from fastapi import APIRouter\n"
                "from pydantic import BaseModel, conlist\n"
                "router = APIRouter()\n"
                "class Item(BaseModel):\n    name: str\n"
                "class Order(BaseModel):\n    items: conlist(Item, min_length=1)\n"},
]


def test_deploy_and_gate_environments_are_identical():
    """THE core proof: for the same fileset, every platform package the DEPLOY
    pins is pinned to the SAME version the GATE constrains to. Identical, not
    similar — a package cannot be one version in the image and another at the
    gate."""
    deploy = _pinned_map(manifest._backend_requirements(_FILES))
    gate = _pinned_map(assembly.platform_constraints_text())

    check("deploy requirements pin Pydantic (not a bare name)", "pydantic" in deploy,
          str(sorted(deploy)))
    check("gate constraints pin Pydantic", "pydantic" in gate, str(sorted(gate)))
    check("deploy and gate pin Pydantic to the IDENTICAL version",
          deploy.get("pydantic") == gate.get("pydantic"),
          f"deploy={deploy.get('pydantic')} gate={gate.get('pydantic')}")

    # Every platform package the deploy pins must match the gate exactly.
    mismatches = {p: (deploy[p], gate.get(p)) for p in deploy
                  if p in gate and deploy[p] != gate[p]}
    check("no platform package differs between deploy and gate", not mismatches,
          str(mismatches))
    # And the platform core is genuinely covered by both (not an empty intersection).
    common = set(deploy) & set(gate)
    check("deploy∩gate covers the platform core (fastapi, sqlalchemy, pydantic)",
          {"fastapi", "sqlalchemy", "pydantic"} <= common, str(sorted(common)))
    # The unpinned extra stays unpinned in the deploy (we only pin what the platform
    # knows) — so the pin is scoped, not a blanket freeze of every transitive dep.
    reqs = manifest._backend_requirements(_FILES)
    check("an unknown extra (pdfplumber) is present but unpinned in the deploy reqs",
          "pdfplumber" in reqs and "pdfplumber==" not in reqs, reqs)


def test_smoke_boot_and_qa_share_one_pinned_environment_builder():
    """Structural: smoke_boot AND QA both build their app through the ONE
    assembly.assemble(), which installs via _install_deps() with the pinned
    --constraint file. They cannot drift apart because there is a single builder."""
    app_dir = os.path.dirname(app.__file__)
    main_src = open(os.path.join(app_dir, "main.py"), encoding="utf-8").read()
    qa_orch_src = open(os.path.join(app_dir, "qa", "orchestrator.py"), encoding="utf-8").read()

    # Both entry points go through the same assemble().
    check("smoke_boot (main._smoke_boot) boots via assembly.assemble",
          "_smoke_boot" in main_src and "assembly.assemble" in main_src)
    check("QA (qa.orchestrator) boots via assembly.assemble",
          "assembly.assemble" in qa_orch_src)
    # assemble() installs deps via _install_deps, which applies the constraint file.
    assemble_src = inspect.getsource(assembly.assemble)
    install_src = inspect.getsource(assembly._install_deps)
    check("assembly.assemble installs deps via _install_deps", "_install_deps" in assemble_src)
    check("_install_deps writes + passes the platform constraint file to pip",
          "platform_constraints_text" in install_src and "--constraint" in install_src)
    check("_install_deps pins each missing package via pin_spec",
          "pin_spec" in install_src)


def main() -> None:
    test_platform_pins_are_real()
    test_pin_spec()
    test_constraints_file()
    test_pinned_pydantic_catches_the_829_bug()
    test_deploy_and_gate_environments_are_identical()
    test_smoke_boot_and_qa_share_one_pinned_environment_builder()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    main()
