"""Step 5+6 cost report for ONE paid run. Throwaway analysis script, not product.

Rows are bounded by id > BOUNDARY rather than by timestamp: the boundary was
recorded immediately before the run started, so it is exact and needs no clock
reasoning.

Reports per the two rules already written into CONTEXT.md:
  - every dollar figure is quoted WITH its row count (a cheap run and a run whose
    usage writes failed produce the same small total; only the count separates them)
  - capture_ok=false rows are counted and reported separately, never folded in

The llm.py-path check is not an assumption carried over from the pre-flight. It is
decided by this run's own rows: EVERY codegen.generate() call in a pipeline run
happens inside developers / reviewer / qa, all of which set a stage. So a row with
stage IS NULL can only have come from app/llm.py — BA, Product Intelligence or the
Architect. Zero such rows would mean that path is still invisible.
"""
import asyncio
import sys

from sqlalchemy import select

from app.database import async_session
from app.models import LLMUsage

BOUNDARY = int(sys.argv[1]) if len(sys.argv) > 1 else 40
OPUS = "claude-opus-4-8"


def money(x) -> str:
    return f"${float(x):.6f}"


async def main():
    async with async_session() as db:
        rows = (await db.execute(
            select(LLMUsage).where(LLMUsage.id > BOUNDARY).order_by(LLMUsage.id)
        )).scalars().all()

    if not rows:
        print(f"NO ROWS above id={BOUNDARY}. The run captured nothing — a total of "
              f"$0.00 here would be a measurement failure, not a free build.")
        return

    ok = [r for r in rows if r.capture_ok]
    bad = [r for r in rows if not r.capture_ok]

    print("=" * 78)
    print(f"COST REPORT — rows with id > {BOUNDARY}")
    print("=" * 78)
    print(f"total rows           : {len(rows)}")
    print(f"  capture_ok = true  : {len(ok)}")
    print(f"  capture_ok = FALSE : {len(bad)}"
          + ("   <-- spend happened here but was NOT measured" if bad else "   (none)"))

    # ---------------------------------------------------------- by model
    print("\n" + "-" * 78)
    print("BY MODEL (rows / prompt / completion / total tokens / cost)")
    print("-" * 78)
    by_model: dict[str, list] = {}
    for r in ok:
        by_model.setdefault(r.model_used, []).append(r)
    for model in sorted(by_model, key=lambda m: -sum(
            float(x.cost_usd or 0) for x in by_model[m])):
        g = by_model[model]
        p = sum(x.prompt_tokens or 0 for x in g)
        c = sum(x.completion_tokens or 0 for x in g)
        cost = sum(float(x.cost_usd or 0) for x in g)
        unpriced = sum(1 for x in g if x.cost_usd is None)
        note = f"  ({unpriced} unpriced)" if unpriced else ""
        print(f"  {model:26} {len(g):>4} rows  {p:>8} + {c:>7} = {p + c:>8} tok  "
              f"{money(cost):>12}{note}")

    # ------------------------------------------------- THE SPLIT (by model)
    opus = [r for r in ok if r.model_used == OPUS]
    rest = [r for r in ok if r.model_used != OPUS]
    opus_cost = sum(float(r.cost_usd or 0) for r in opus)
    rest_cost = sum(float(r.cost_usd or 0) for r in rest)
    total_cost = opus_cost + rest_cost

    print("\n" + "=" * 78)
    print("THE SPLIT — security review (Opus) vs everything else")
    print("=" * 78)
    print(f"  Opus security review : {money(opus_cost):>12}   "
          f"{len(opus):>4} rows   "
          f"{(opus_cost / total_cost * 100) if total_cost else 0:5.1f}% of spend")
    print(f"  Everything else      : {money(rest_cost):>12}   "
          f"{len(rest):>4} rows   "
          f"{(rest_cost / total_cost * 100) if total_cost else 0:5.1f}% of spend")
    print(f"  {'TOTAL':21}{money(total_cost):>12}   {len(ok):>4} rows")
    if bad:
        print(f"  ⚠ EXCLUDES {len(bad)} unmeasured call(s) — the true total is HIGHER.")

    # ------------------------------------- BOTH PATHS PRESENT? (the near-miss)
    print("\n" + "=" * 78)
    print("PATH COVERAGE — is app/llm.py spend actually here, or only codegen.py?")
    print("=" * 78)
    tagged = [r for r in rows if r.stage]
    untagged = [r for r in rows if not r.stage]
    print("  Every codegen.generate() call in a pipeline run happens inside a")
    print("  stage-tagged orchestrator, so stage IS NULL can ONLY be app/llm.py.")
    print(f"\n  stage-tagged rows (codegen path) : {len(tagged)}")
    for st in sorted({r.stage for r in tagged}):
        g = [r for r in tagged if r.stage == st]
        print(f"      stage={st:12} {len(g):>4} rows  "
              f"{money(sum(float(x.cost_usd or 0) for x in g))}")
    print(f"\n  stage=NULL rows (llm.py path)    : {len(untagged)}")
    models = sorted({r.model_used for r in untagged})
    for m in models:
        g = [r for r in untagged if r.model_used == m]
        print(f"      {m:26} {len(g):>4} rows  "
              f"{money(sum(float(x.cost_usd or 0) for x in g))}")
    verdict = ("CLOSED — BA / Product Intelligence / Architect spend IS captured"
               if untagged else
               "STILL OPEN — zero llm.py rows; that path is invisible")
    print(f"\n  VERDICT: {verdict}")


if __name__ == "__main__":
    asyncio.run(main())
