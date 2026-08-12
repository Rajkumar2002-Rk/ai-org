"""D4 — force generated Next.js apps to render dynamically so `next build` never
prerenders a page (project 860, 2026-08-12).

Project 860 was the first run to fully pass QA, then FAILED at the deploy step:
`next build` died prerendering `/integrate` — a `"use client"` page calling
`useSearchParams()` without a Suspense boundary ("useSearchParams() should be
wrapped in a suspense boundary" -> "Error occurred prerendering page '/integrate'").

⚠️ HISTORY — do not re-introduce the page-level approach. CONTEXT.md originally
documented the fix as injecting `export const dynamic = "force-dynamic"` into the
PAGE files. That was DISPROVEN on Next 15 with a real build: route-segment config is
IGNORED in Client Components, and every generated `page.tsx` here is `"use client"`,
so the page-level export does nothing and the build still fails. The mechanism that
actually works (real-build proven) is exporting `dynamic = "force-dynamic"` from the
ROOT SERVER `layout.tsx`, whose config cascades to every route and makes the whole
app dynamic.

This suite is the fast, deterministic guard on the INJECTION LOGIC
(`assembly.force_dynamic_layout`). The end-to-end real-`next build` proof (a page
fails to build without the layout fix, succeeds with it) needs the Node toolchain and
lives in `test_d4_real_build.sh` (excluded from the free suite, like the live Docker
tests). Zero LLM spend, no network.

Run:
  docker compose run --rm --no-deps -e PYTHONPATH=/app -v "$PWD/backend:/app" \
      backend python tests/test_d4_force_dynamic_offline.py
"""
import sys

from app.qa import assembly

_failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


_EXPORT = 'export const dynamic = "force-dynamic";'

# A realistic generated ROOT layout (server component, with imports + a metadata
# export) — the exact shape project 860 shipped.
_ROOT_LAYOUT = (
    'import type { Metadata } from "next";\n'
    'import "./globals.css";\n\n'
    'export const metadata: Metadata = { title: "Restaurant" };\n\n'
    "export default function RootLayout({ children }: { children: React.ReactNode }) {\n"
    "  return (<html lang=\"en\"><body>{children}</body></html>);\n}\n"
)
# A generated CLIENT page using useSearchParams — the D4 trigger. Route config is
# ignored here, so it must be LEFT ALONE (injecting would be a silent no-op).
_CLIENT_PAGE = (
    '"use client";\n'
    'import { useSearchParams } from "next/navigation";\n'
    "export default function P() { const s = useSearchParams(); return <div>{s.get(\"x\")}</div>; }\n"
)


def test_injects_into_root_server_layout():
    out = assembly.force_dynamic_layout("frontend/app/layout.tsx", _ROOT_LAYOUT)
    check("root server layout: force-dynamic injected", _EXPORT in out, out[:80])
    check("root server layout: export is the FIRST line (before imports)",
          out.startswith(_EXPORT + "\n"), out[:60])
    check("root server layout: original body preserved",
          "RootLayout" in out and 'import "./globals.css";' in out)
    # Path handling: the deploy manifest strips the leading `frontend/`, so the same
    # file arrives as `app/layout.tsx`. Both must be recognised as the root.
    check("root recognised with frontend/ prefix stripped (deploy path)",
          assembly.force_dynamic_layout("app/layout.tsx", _ROOT_LAYOUT).startswith(_EXPORT))


def test_skips_where_it_would_be_wrong():
    # A CLIENT root layout: route config is ignored in client components, so injecting
    # would be a lie. Must be left untouched (this is the whole 829/860 lesson).
    client_layout = '"use client";\n' + _ROOT_LAYOUT
    check("client root layout is SKIPPED (route config ignored there)",
          assembly.force_dynamic_layout("app/layout.tsx", client_layout) == client_layout)
    # A layout that already chose a mode is respected.
    already = _EXPORT.replace("force-dynamic", "force-static") + "\n" + _ROOT_LAYOUT
    check("layout that already exports dynamic is left untouched",
          assembly.force_dynamic_layout("app/layout.tsx", already) == already)
    # Nested segment layouts are not the root — forcing the root already covers them.
    check("nested segment layout (app/admin/layout.tsx) is untouched",
          assembly.force_dynamic_layout("frontend/app/admin/layout.tsx", _ROOT_LAYOUT) == _ROOT_LAYOUT)


def test_leaves_pages_and_other_files_alone():
    # The proven-wrong page-level approach must NOT resurface: pages are never touched.
    check("client page.tsx is NOT modified (page-level fix was disproven)",
          assembly.force_dynamic_layout("frontend/app/integrate/page.tsx", _CLIENT_PAGE) == _CLIENT_PAGE)
    check("a non-layout component is untouched",
          assembly.force_dynamic_layout("frontend/app/components/Nav.tsx", _ROOT_LAYOUT) == _ROOT_LAYOUT)
    check("a backend .py file is untouched",
          assembly.force_dynamic_layout("backend/app/main.py", "print('x')\n") == "print('x')\n")


def test_idempotent():
    once = assembly.force_dynamic_layout("app/layout.tsx", _ROOT_LAYOUT)
    twice = assembly.force_dynamic_layout("app/layout.tsx", once)
    check("injection is idempotent (no double export)", once == twice and once.count(_EXPORT) == 1)


def main() -> None:
    test_injects_into_root_server_layout()
    test_skips_where_it_would_be_wrong()
    test_leaves_pages_and_other_files_alone()
    test_idempotent()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) FAILED:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED ✓")


if __name__ == "__main__":
    main()
