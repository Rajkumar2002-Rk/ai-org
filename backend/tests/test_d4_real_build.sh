#!/usr/bin/env bash
# D4 real-`next build` proof (project 860) — EXCLUDED from the free suite: it needs
# the Node toolchain + Docker, like test_devops_local_live / the AWS shakeout.
#
# Proves the MECHANISM end to end, on a real `next build`:
#   Build A: a generated CLIENT page using useSearchParams(), with the root layout
#            UNMODIFIED  -> `next build` FAILS prerendering the page (the 860 defect).
#   Build B: the SAME fixture, root layout transformed by the REAL helper
#            (assembly.force_dynamic_layout) -> `next build` SUCCEEDS, page is dynamic.
#
# It uses the running frontend container's Node/Next (15.x) and the backend
# container's Python helper, so it exercises the actual shipped code.
#
# Run from the repo root:
#   bash backend/tests/test_d4_real_build.sh
set -uo pipefail

FE=ai-org-frontend-1
WORK=/tmp/d4_real_build
FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1${2:+   ($2)}"; FAIL=1; }

docker ps --format '{{.Names}}' | grep -q "^${FE}$" || {
  echo "SKIP: ${FE} is not running (needs the frontend container). Nothing proven."; exit 0; }

tmp="$(mktemp -d)"
mkdir -p "$tmp/app/integrate"
cat > "$tmp/package.json" <<'JSON'
{ "name": "d4-real", "version": "0.0.0", "private": true, "scripts": { "build": "next build" },
  "dependencies": { "next": "15.1.3", "react": "19.0.0", "react-dom": "19.0.0" } }
JSON
printf 'body{margin:0;}\n' > "$tmp/app/globals.css"
# Server root layout (no force-dynamic yet) — the shape a generated app ships.
cat > "$tmp/app/layout.tsx" <<'TSX'
import "./globals.css";
export const metadata = { title: "D4" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
TSX
# Client page using useSearchParams() with no Suspense — the exact D4 prerender trigger.
cat > "$tmp/app/integrate/page.tsx" <<'TSX'
"use client";
import { useSearchParams } from "next/navigation";
export default function IntegratePage() {
  const params = useSearchParams();
  return <div>connected: {params.get("connected")}</div>;
}
TSX

docker exec "$FE" rm -rf "$WORK" >/dev/null 2>&1
docker cp "$tmp" "$FE:$WORK" >/dev/null 2>&1
docker exec "$FE" sh -c "cd $WORK && ln -sfn /app/node_modules node_modules && cp /app/tsconfig.json . 2>/dev/null; cp /app/next.config.js . 2>/dev/null" >/dev/null 2>&1

echo "== Build A: root layout UNMODIFIED (expect FAILURE) =="
outA="$(docker exec "$FE" sh -c "cd $WORK && rm -rf .next && npx --no-install next build 2>&1")"; codeA=$?
if [ $codeA -ne 0 ] && echo "$outA" | grep -qi "prerendering page \"/integrate\""; then
  pass "without the layout fix, next build FAILS prerendering /integrate"
else
  fail "expected a prerender failure without the fix" "exit=$codeA"
  echo "$outA" | tail -6 | sed 's/^/      /'
fi

# Transform the layout with the REAL shipped helper (source mounted so it is the
# CURRENT code, not the baked image; -T so the layout pipes in on stdin).
fixed="$(docker compose run -T --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" backend python -c '
import sys; from app.qa import assembly
sys.stdout.write(assembly.force_dynamic_layout("app/layout.tsx", sys.stdin.read()))
' < "$tmp/app/layout.tsx" 2>/dev/null)"
if ! printf '%s' "$fixed" | grep -q 'force-dynamic'; then
  fail "helper transform produced no force-dynamic output (setup problem, not the fix)"; echo "RESULT: CHECKS FAILED"; exit 1
fi
printf '%s' "$fixed" | docker exec -i "$FE" sh -c "cat > $WORK/app/layout.tsx"

echo "== Build B: root layout transformed by force_dynamic_layout (expect SUCCESS) =="
outB="$(docker exec "$FE" sh -c "cd $WORK && rm -rf .next && npx --no-install next build 2>&1")"; codeB=$?
if [ $codeB -eq 0 ] && ! echo "$outB" | grep -qi "prerendering page"; then
  pass "with the root-layout fix, next build SUCCEEDS (no prerender error)"
else
  fail "expected a clean build with the fix" "exit=$codeB"
  echo "$outB" | tail -6 | sed 's/^/      /'
fi
if echo "$outB" | grep -qE 'ƒ .*/integrate'; then
  pass "/integrate is rendered dynamically (ƒ), not statically prerendered"
else
  echo "  [warn] could not confirm the dynamic marker in build output (non-fatal)"
fi

docker exec "$FE" rm -rf "$WORK" >/dev/null 2>&1
rm -rf "$tmp"
echo ""
echo "============================================================"
[ $FAIL -eq 0 ] && { echo "RESULT: ALL CHECKS PASSED ✓"; exit 0; } || { echo "RESULT: CHECKS FAILED"; exit 1; }
