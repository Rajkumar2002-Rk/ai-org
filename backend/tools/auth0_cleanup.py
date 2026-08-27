"""Auth0 tenant cleanup — remove the platform's stale per-project apps.

The platform auto-provisions a per-project Auth0 Application + API at deploy time
(`onboarding/auth0_provision.py`), each named `proj-<project_id>`. Over many test
runs these accumulate and the tenant hits its client limit → 403 on new provisioning
(deploys then degrade to login-unavailable placeholders via Fix #47).

This tool inventories and (only with --delete) removes those auto-provisioned
artifacts. It NEVER touches anything outside the `proj-` name prefix, so the tenant's
Default App and the Management (M2M) app are always left alone.

Read-only by default. Nothing is deleted unless you pass --delete.

Run it inside the backend container (which has httpx + the AUTH0_* env wired):

  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tools/auth0_cleanup.py            # inventory (dry run)

  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tools/auth0_cleanup.py --delete   # actually delete

Flags:
  --prefix P     name prefix identifying our apps (default: "proj-")
  --keep NAME    keep this exact client/API name (repeatable) — e.g. --keep proj-1950
  --delete       perform deletions (otherwise dry run)
  --clients-only / --apis-only   restrict to one resource type
"""
import argparse
import os
import sys

import httpx


def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"ERROR: {name} is not set (is .env loaded / passed into the container?)")
    return val


def _mgmt_token(client: httpx.Client, base: str, cid: str, secret: str) -> str:
    resp = client.post(f"{base}/oauth/token", json={
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": secret,
        "audience": f"{base}/api/v2/",
    })
    if resp.status_code != 200:
        sys.exit(f"ERROR: management token failed (HTTP {resp.status_code}): {resp.text[:300]}")
    tok = resp.json().get("access_token")
    if not tok:
        sys.exit("ERROR: management token response had no access_token")
    return tok


def _paged(client: httpx.Client, base: str, token: str, path: str, key: str) -> list[dict]:
    """Fetch every page of a v2 list endpoint that supports include_totals."""
    out: list[dict] = []
    page = 0
    while True:
        resp = client.get(
            f"{base}/api/v2/{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={"page": page, "per_page": 100, "include_totals": "true"},
        )
        if resp.status_code != 200:
            sys.exit(f"ERROR: list {path} failed (HTTP {resp.status_code}): {resp.text[:300]}")
        body = resp.json()
        items = body.get(key, body if isinstance(body, list) else [])
        out.extend(items)
        total = body.get("total")
        if total is None or len(out) >= total or not items:
            return out
        page += 1


def _delete(client: httpx.Client, base: str, token: str, path: str, ident: str) -> tuple[bool, str]:
    resp = client.delete(
        f"{base}/api/v2/{path}/{ident}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code in (200, 202, 204):
        return True, ""
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", default="proj-")
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--clients-only", action="store_true")
    ap.add_argument("--apis-only", action="store_true")
    args = ap.parse_args()

    domain = _env("AUTH0_TENANT_DOMAIN")
    cid = _env("AUTH0_MGMT_CLIENT_ID")
    secret = _env("AUTH0_MGMT_CLIENT_SECRET")
    base = f"https://{domain}"
    keep = set(args.keep)

    with httpx.Client(timeout=30) as client:
        token = _mgmt_token(client, base, cid, secret)
        print(f"tenant: {domain}  prefix: {args.prefix!r}  "
              f"mode: {'DELETE' if args.delete else 'dry-run (read-only)'}")
        if keep:
            print(f"keeping: {sorted(keep)}")
        print("-" * 70)

        do_clients = not args.apis_only
        do_apis = not args.clients_only

        # --- Applications (clients) ---
        client_targets: list[dict] = []
        if do_clients:
            clients = _paged(client, base, token, "clients", "clients")
            ours = [c for c in clients if str(c.get("name", "")).startswith(args.prefix)]
            client_targets = [c for c in ours if c.get("name") not in keep]
            print(f"CLIENTS: {len(clients)} total, {len(ours)} match {args.prefix!r}, "
                  f"{len(client_targets)} eligible for deletion")
            for c in ours:
                mark = "KEEP" if c.get("name") in keep else "DEL "
                print(f"  [{mark}] {c.get('name'):<16} {c.get('client_id')}")

        # --- APIs (resource servers) ---
        api_targets: list[dict] = []
        if do_apis:
            apis = _paged(client, base, token, "resource-servers", "resource_servers")
            ours = [a for a in apis if str(a.get("name", "")).startswith(args.prefix)]
            api_targets = [a for a in ours if a.get("name") not in keep]
            print(f"APIS:    {len(apis)} total, {len(ours)} match {args.prefix!r}, "
                  f"{len(api_targets)} eligible for deletion")
            for a in ours:
                mark = "KEEP" if a.get("name") in keep else "DEL "
                print(f"  [{mark}] {a.get('name'):<16} {a.get('identifier')}")

        print("-" * 70)
        if not args.delete:
            print(f"DRY RUN — nothing deleted. Would delete {len(client_targets)} client(s) "
                  f"+ {len(api_targets)} API(s). Re-run with --delete to apply.")
            return

        ok = fail = 0
        for c in client_targets:
            good, err = _delete(client, base, token, "clients", c.get("client_id"))
            if good:
                ok += 1
                print(f"  deleted client {c.get('name')}")
            else:
                fail += 1
                print(f"  FAILED client {c.get('name')}: {err}")
        for a in api_targets:
            good, err = _delete(client, base, token, "resource-servers", a.get("id"))
            if good:
                ok += 1
                print(f"  deleted API    {a.get('name')}")
            else:
                fail += 1
                print(f"  FAILED API     {a.get('name')}: {err}")
        print("-" * 70)
        print(f"done: {ok} deleted, {fail} failed")
        if fail:
            print("NOTE: 403s here mean the Management (M2M) app lacks delete:clients / "
                  "delete:resource_servers scopes — grant them in the Auth0 dashboard "
                  "(APIs → Auth0 Management API → Machine to Machine Applications), or "
                  "delete the listed apps manually.")


if __name__ == "__main__":
    main()
