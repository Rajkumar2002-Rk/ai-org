"""TEMPORARY verification driver (not part of the product, not committed).

Drives ONE real project through the full chain over the real HTTP API:
BA -> Product Intelligence -> Architect -> Developers -> Code Reviewer -> QA.

Everything here is real: real LLM calls, real generated code, real Opus security
review, real QA against a real running instance. No fixtures.
"""
import asyncio
import json
import os
import sys
import time

import httpx

API = "http://backend:8000"
LOG_PATH = "/app/tests/_verify_run.log"

# Opening the log must never be able to kill a PAID run. A transient bind-mount
# hiccup once took this whole driver down at import time, before a single API
# call — the run cost nothing that time, but it would have been maddening at
# minute forty. stdout is the real transcript; the file is a convenience.
try:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    LOG = open(LOG_PATH, "a", buffering=1)
except OSError as exc:
    print(f"(run log unavailable: {exc} — continuing, stdout still has everything)",
          flush=True)
    LOG = None


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if LOG is not None:
        LOG.write(line + "\n")


# Deliberately small coffee-shop idea. Mentions ordering + paying + tips so the
# payment path (Stripe Connect) is exercised on genuine output.
IDEA = ("A small coffee shop website where customers can see the menu, "
        "order a coffee for pickup, pay by card, and leave a tip for the baristas.")

ANSWERS = {
    "ask_build": IDEA,
    "ask_platform": "website",
    "ask_business_name": "Brew and Bean",
    "ask_location": "Austin, Texas",
    "ask_audience": "local customers who want to order coffee ahead of time",
    "ask_user_count": "about 200 people a week",
    "ask_budget": "$20 a month",
    "ask_timeline": "about a month",
    "ask_growth": "maybe add a loyalty program later",
    "present_ci": "skip",
    "present_plan": "quick",
    "ask_design_vibe": "Warm friendly",
    "ask_design_refs": "skip",
    "ask_design_color": "warm brown",
    "confirm": "Yes, this is right",
    "mobile_choice": "just a website",
}


async def poll(client, url, key="status", done=("done",), bad=("error",),
               limit=900, label=""):
    """Poll a status endpoint until done/error."""
    start = time.time()
    last = None
    while time.time() - start < limit:
        r = await client.get(url)
        data = r.json()
        s = data.get(key)
        if s != last:
            log(f"    {label} status -> {s}  {json.dumps({k: v for k, v in data.items() if k != 'certificate'})[:200]}")
            last = s
        if s in done:
            return data
        if s in bad:
            return data
        await asyncio.sleep(3)
    log(f"    {label} TIMED OUT after {limit}s")
    return {"status": "timeout"}


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        log("=" * 70)
        log("STEP 1 — REAL end-to-end pipeline run (no fixtures)")
        log("=" * 70)

        r = await client.post(f"{API}/conversation/start")
        data = r.json()
        pid = data["project_id"]
        log(f"project_id = {pid}")
        log(f"  BA: {data['reply'][:150]}")

        stage = data["stage"]
        for turn in range(40):
            if stage in ("done", "blocked"):
                break
            answer = ANSWERS.get(stage)
            if answer is None:
                kind = data.get("ui", {}).get("kind")
                answer = "skip" if kind in ("ci_findings",) else "yes"
                log(f"  !! no scripted answer for stage '{stage}' (ui={kind}) -> '{answer}'")
            log(f"  -> [{stage}] answering: {answer[:70]}")
            r = await client.post(f"{API}/conversation/message",
                                  json={"project_id": pid, "message": answer})
            data = r.json()
            stage = data["stage"]
            log(f"     BA[{stage}]: {data['reply'][:160]}")
            if data.get("researching"):
                log("     (competitive research running…)")
                for _ in range(30):
                    await asyncio.sleep(3)
                    rs = await client.get(f"{API}/conversation/{pid}/research-status")
                    if rs.json().get("ready"):
                        break

        log(f"BA finished at stage={stage}")
        if stage != "done":
            log("ABORT: BA did not reach 'done'")
            return

        log("\n-- Product Intelligence review-gate --")
        r = await client.post(f"{API}/pipeline/review", json={"project_id": pid})
        review = r.json().get("review", {})
        log(f"  verdict: {json.dumps(review)[:400]}")

        log("\n-- Architect --")
        await client.post(f"{API}/pipeline/start", json={"project_id": pid})
        await poll(client, f"{API}/pipeline/{pid}/status", label="architect")
        bp = (await client.get(f"{API}/pipeline/{pid}/blueprint")).json()
        tickets = bp.get("sprint_tickets", [])
        log(f"  blueprint: {len(tickets)} tickets, "
            f"{len(bp.get('database_schema', []))} tables, "
            f"{len(bp.get('api_endpoints', []))} endpoints")
        log(f"  ticket ids: {[t.get('id') for t in tickets]}")
        log(f"  third_party: {[a.get('name') for a in bp.get('third_party_apis', [])]}")

        log("\n-- Developers --")
        await client.post(f"{API}/pipeline/build", json={"project_id": pid})
        b = await poll(client, f"{API}/pipeline/{pid}/build-status", label="build", limit=1200)
        log(f"  files built: {b.get('complete')}/{b.get('total')}")
        for f in b.get("files", []):
            log(f"    {f.get('status'):<13} {f.get('agent_type'):<11} {f.get('filename')}")

        log("\n-- Code Reviewer (Opus security) --")
        await client.post(f"{API}/pipeline/secure", json={"project_id": pid})
        sec = await poll(client, f"{API}/pipeline/{pid}/security-status", label="secure",
                         limit=1800)
        log(f"  certificate: {json.dumps(sec.get('certificate'))}")

        # PRODUCTION FLOW: the real UI only chains to QA when the security
        # status is "done". Mirror that exactly — do not force QA onto code the
        # security gate rejected.
        if sec.get("status") != "done":
            log(f"\n!! SECURITY GATE BLOCKED (status={sec.get('status')}) — "
                f"production flow does NOT run QA here. Stopping.")
            log(f"\nPROJECT_ID={pid}")
            return

        log("\n-- QA AGENT --")
        t0 = time.time()
        await client.post(f"{API}/pipeline/qa", json={"project_id": pid})
        qa = await poll(client, f"{API}/pipeline/{pid}/qa-status", label="qa", limit=2400)
        log(f"  QA wall-clock: {time.time() - t0:.1f}s")
        log(f"  QA result: {json.dumps(qa)}")
        log(f"\nPROJECT_ID={pid}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
