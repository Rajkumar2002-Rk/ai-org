"""Step-3 verification: root-cause classification QUALITY.

Not "do the four labels look reasonable in isolation" — the question is whether
the classifier REASONS about why a failure belongs to one tier or another, or
pattern-matches on surface strings. So every case reports the PATH taken:

    which deterministic rule fired (by name), or "none -> model", and if the
    model was consulted, its own stated reason.

Cost: the deterministic probes are free. The model probes make a handful of
Gemini 2.5 Flash-Lite classification calls (fractions of a cent, no pipeline
run, no Opus). Pass --offline to skip them entirely.

Run: docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
         backend python tests/test_qa_classification.py [--offline]
"""
import asyncio
import json
import sys

from app import codegen
from app.config import settings
from app.qa import root_cause as rc
from app.qa.outcome import TestOutcome

OFFLINE = "--offline" in sys.argv
_failures: list[str] = []
_notes: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def note(msg: str) -> None:
    _notes.append(msg)
    print(f"  [NOTE] {msg}")


def known_gap(label: str, holds: bool, detail: str = "") -> None:
    """A real limitation that is an OPEN DESIGN DECISION, not a regression.

    Recorded loudly so it can never be quietly forgotten, but it does not fail
    the run — otherwise the suite is permanently red and stops being usable as a
    regression gate.
    """
    if holds:
        print(f"  [PASS] {label}")
    else:
        print(f"  [KNOWN GAP] {label}   {detail}")
        _notes.append(f"OPEN GAP — {label}: {detail}")


# ---------------------------------------------------------------- path tracing
def which_rule(o: TestOutcome) -> str | None:
    """Mirror of rc._deterministic, but reports WHICH rule matched.

    Kept in the test on purpose: if the production rules change and this drifts,
    the mismatch assertion below fails and forces the test to be updated.
    """
    reason = (o.reason or "").lower()
    name = (o.name or "").lower()

    if rc._is_environment_fault(name, reason):
        return "harness fault -> environment_fault"
    if "syntax error" in name or "syntax error" in reason:
        return "syntax error -> developer_fix"
    if "imports point at files that were never generated" in reason:
        return "unresolved import -> developer_fix"
    if "dependency install failed" in name or "package that does not exist" in reason:
        return "dependency install -> developer_fix"
    if "no default export" in reason:
        return "no default export -> developer_fix"
    if "no runnable app found" in name:
        return "no runnable app -> architect_rework"
    if "app did not start" in name:
        return "app did not start -> developer_rework"
    if "has endpoints" in name or "discoverable" in name:
        return "no endpoints -> developer_rework"
    if o.level == 2:
        if "blocks access" in name or "rejects invalid credentials" in name:
            return "L2 authz/authn -> developer_fix"
        if "sql injection" in name or "negative amounts" in name or \
                "dangerous file names" in name:
            return "L2 injection/payment/upload -> developer_fix"
    if "server error" in reason and o.level == 1:
        if not any(s in reason for s in rc._ARCHITECT_SIGNALS):
            return "'server error' + level 1, no architect signal -> developer_fix"
    return None


def outcome(name, reason, level=1, target="app") -> TestOutcome:
    return TestOutcome(name=name, level=level, passed=False, reason=reason, target=target)


async def classify_traced(o: TestOutcome, blueprint: dict, summary: dict):
    """Returns (label, path, model_why)."""
    rule = which_rule(o)
    det = rc._deterministic(o)
    # Guard: the mirror above must agree with production.
    if (rule is None) != (det is None):
        raise AssertionError(f"rule mirror drifted from production for {o.name!r}")

    if rule:
        return det, f"DETERMINISTIC: {rule}", None

    if OFFLINE:
        return None, "MODEL (skipped: --offline)", None

    # Re-run the exact model call so we can capture its stated reasoning.
    endpoints = [f"{e.get('method')} {e.get('path')}"
                 for e in (blueprint.get("api_endpoints") or [])][:25]
    ctx = {
        "failed_test": o.name,
        "what_happened": o.reason[:600],
        "target": o.target,
        "designed_endpoints": endpoints,
        "what_the_user_asked_for": (summary or {}).get("build", "")[:300],
    }
    text, _ = await codegen.generate(settings.qa_model, rc._SYS,
                                     f"Failure: {json.dumps(ctx)}",
                                     temperature=settings.qa_temperature)
    res = rc._extract_json(text) or {}
    label = await rc.classify(o, blueprint, summary)
    return label, "MODEL", res.get("why")


async def report(title, o, blueprint, summary, expected=None, defensible=()):
    label, path, why = await classify_traced(o, blueprint, summary)
    print(f"\n  --- {title} ---")
    print(f"      test   : {o.name}")
    print(f"      path   : {path}")
    print(f"      label  : {label}")
    if why:
        print(f"      model's reason: {why}")
    if expected:
        check(f"{title}: classified {expected}", label == expected, f"got {label}")
    elif defensible:
        check(f"{title}: label is defensible {defensible}", label in defensible, f"got {label}")
    return label, path, why


# ================================================================== fixtures
COFFEE = {"build": "a coffee shop website where customers see the menu, "
                   "order a coffee for pickup and pay by card"}
COFFEE_BP = {"api_endpoints": [{"method": "GET", "path": "/api/menu"},
                               {"method": "POST", "path": "/api/orders"},
                               {"method": "GET", "path": "/api/orders/{order_id}"}]}

# Blueprint that has nothing to do with what the user asked for.
VET_BP = {"api_endpoints": [{"method": "GET", "path": "/api/pets"},
                            {"method": "POST", "path": "/api/appointments"},
                            {"method": "GET", "path": "/api/vaccinations"}]}


# ================================================================== part 3
async def part3_borderline():
    print("\n=== PART 3: developer_rework / architect_rework boundary (borderline) ===")

    # B1 — a column referenced by THREE files. One typo, or a schema the
    # Architect never defined? Genuinely ambiguous.
    b1 = outcome(
        "POST /api/orders — happy path",
        "Server error 500 — the app crashed instead of handling this. Response: "
        "sqlalchemy.exc.ProgrammingError: column orders.customer_email does not "
        "exist. The same column is referenced by orders.py, notifications.py and "
        "receipts.py, and it is not present in the blueprint's database schema.",
        level=1, target="POST /api/orders")
    l1, p1, _ = await report("B1 missing column referenced by 3 files", b1,
                             COFFEE_BP, COFFEE)

    # B2 — endpoint exists but returns the wrong shape. Implementation bug, or
    # the blueprint specified the wrong contract?
    b2 = outcome(
        "GET /api/orders — happy path",
        "Server error 500 — the app crashed. Response: TypeError: expected a list "
        "of orders but the handler returns a single object. The blueprint "
        "specifies this endpoint returns a collection.",
        level=1, target="GET /api/orders")
    l2, p2, _ = await report("B2 wrong return shape", b2, COFFEE_BP, COFFEE)

    # B3 — an undeclared dependency between tickets. Developer oversight, or a
    # gap in the Architect's ticket graph? This one does NOT hit a rule.
    b3 = outcome(
        "assembly: designed features are missing from the running app",
        "The app started but 1 of 3 designed endpoints is not there: /api/orders. "
        "orders.py imports a payments module that was never generated — no ticket "
        "in the blueprint commissioned it, and no ticket declared the dependency.",
        level=1, target="app")
    l3, p3, why3 = await report("B3 undeclared ticket dependency", b3,
                                COFFEE_BP, COFFEE)

    print()
    short_circuited = [t for t, p in (("B1", p1), ("B2", p2), ("B3", p3))
                       if p.startswith("DETERMINISTIC")]
    check("at least one borderline case reaches the model rather than a rule",
          len(short_circuited) < 3,
          f"all short-circuited: {short_circuited}")
    if short_circuited:
        note(f"{len(short_circuited)}/3 borderline cases were decided by a STRING "
             f"MATCH before any reasoning happened: {short_circuited}")
    return {"B1": (l1, p1), "B2": (l2, p2), "B3": (l3, p3)}


# ================================================================== part 2
async def part2_ba_rework():
    print("\n=== PART 2: can a ba_rework case be produced at all? ===")

    # The most blatant requirements mismatch that QA can actually surface: the
    # user asked for a coffee shop, the build is a veterinary clinic.
    ba = outcome(
        "assembly: designed features are missing from the running app",
        "The app started but 2 of 3 designed endpoints are not there: "
        "/api/appointments, /api/vaccinations. The running app exposes pet and "
        "appointment features. The user asked for a coffee shop ordering site — "
        "there is no menu, ordering or payment capability anywhere in this build.",
        level=1, target="app")
    label, path, why = await report("BA blatant domain mismatch", ba, VET_BP, COFFEE)

    check("blatant requirements mismatch is classified ba_rework",
          label == rc.BA_REWORK, f"got {label}")
    if label != rc.BA_REWORK:
        note("Even a total domain mismatch did not yield ba_rework.")

    # The label is reachable — but only because the mismatch was WRITTEN INTO the
    # failure text above. Nothing in QA produces that sentence on its own.
    note("ba_rework is reachable ONLY when evidence of a requirements mismatch is "
         "already in the failure text. No Level 1 or Level 2 test compares the "
         "built app against summary_json — `summary` reaches QA solely inside "
         "root_cause.classify(). An app that flawlessly implements the WRONG "
         "product passes every QA test and produces no failure to classify.")
    return label


# ================================================================== part 4
async def part4_over_escalation():
    print("\n=== PART 4: over-escalation — trivial bugs wearing architect clothing ===")

    # O1 — a one-character typo, but the text is stuffed with architect words.
    o1 = outcome(
        "assembly: designed features are missing from the running app",
        "The app started but 1 of 3 designed endpoints is not there: /api/menu. "
        "The blueprint's database schema and endpoint design are correct and fully "
        "implemented; main.py simply mis-spells the router import as 'menue' "
        "instead of 'menu'. A one-character typo in a single file.",
        level=1, target="app")
    l1, p1, w1 = await report("O1 typo described with schema/blueprint wording", o1,
                              COFFEE_BP, COFFEE,
                              defensible=(rc.DEVELOPER_FIX, rc.DEVELOPER_REWORK))

    # O2 — plain missing validation, but mentions 'architecture'.
    o2 = outcome(
        "POST /api/orders — missing required field 'quantity'",
        "The endpoint accepted a request with no quantity and stored a null. The "
        "overall architecture and schema are correct; the handler is missing a "
        "single validation check.",
        level=1, target="POST /api/orders")
    l2, p2, w2 = await report("O2 missing validation, mentions architecture", o2,
                              COFFEE_BP, COFFEE,
                              defensible=(rc.DEVELOPER_FIX, rc.DEVELOPER_REWORK))

    over = [t for t, l in (("O1", l1), ("O2", l2))
            if l in (rc.ARCHITECT_REWORK, rc.BA_REWORK)]
    check("no trivial Developer bug was over-escalated", not over, str(over))
    return over


# ================================================================== part 5
async def part5_env_faults():
    print("\n=== PART 5: harness/environment faults — who gets blamed? ===")

    # Every one of Step 1's six defects surfaced looking like this.
    env1 = outcome(
        "assembly: app did not start",
        "The generated app failed to start within 45s. Startup output: "
        "ModuleNotFoundError: No module named 'backend'",
        level=1, target="app")
    l1, p1, _ = await report("E1 harness PYTHONPATH fault", env1, COFFEE_BP, COFFEE)

    env2 = outcome(
        "assembly: app did not start",
        "The generated app failed to start within 45s. Startup output: "
        "RuntimeError: Missing required authentication environment variables: "
        "AUTH0_DOMAIN. Refusing to start with an insecure auth configuration.",
        level=1, target="app")
    l2, p2, _ = await report("E2 correct fail-fast, config absent from test env",
                             env2, COFFEE_BP, COFFEE)

    # E3 — the harness could not build its own sandbox.
    env3 = outcome(
        "assembly: could not create test database",
        "connection refused while creating the throwaway Postgres database",
        level=1, target="app")
    l3, p3, _ = await report("E3 harness could not build its sandbox", env3,
                             COFFEE_BP, COFFEE)

    blamed = [t for t, l in (("E1", l1), ("E2", l2), ("E3", l3))
              if l in (rc.DEVELOPER_FIX, rc.DEVELOPER_REWORK)]
    check("no environment fault is blamed on the Developer", not blamed, str(blamed))
    check("all three classify as environment_fault",
          all(l == rc.ENVIRONMENT_FAULT for l in (l1, l2, l3)),
          f"E1={l1} E2={l2} E3={l3}")
    check("environment_fault never auto-retries",
          not rc.is_auto_fixable(
              TestOutcome("x", 1, False, "", "", root_cause_agent=rc.ENVIRONMENT_FAULT)))

    # Guard the other direction: a REAL code bug must not be excused as an
    # environment fault just because it happens at startup.
    real_bug = outcome(
        "assembly: app did not start",
        "The generated app failed to start within 45s. Startup output: "
        "NameError: name 'UNDEFINED_SETTINGS' is not defined",
        level=1, target="app")
    l4, p4, _ = await report("E4 genuine code bug at startup (must NOT be excused)",
                             real_bug, COFFEE_BP, COFFEE,
                             expected=rc.DEVELOPER_REWORK)
    return blamed


async def main():
    print(f"(model probes: {'SKIPPED (--offline)' if OFFLINE else settings.qa_model})")
    await part3_borderline()
    await part2_ba_rework()
    await part4_over_escalation()
    await part5_env_faults()

    print("\n" + "=" * 64)
    if _notes:
        print("FINDINGS:")
        for n in _notes:
            print(f"   • {n}")
        print()
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) did not hold:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
