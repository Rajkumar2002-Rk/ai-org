"use client";

import { useEffect, useRef, useState } from "react";
import { BuildCharacter, Pose } from "./character";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Rotating hero placeholder examples (Section 1).
const PLACEHOLDERS = [
  "I want an app to manage my grocery store…",
  "Build me a booking system for my salon…",
  "I need an inventory tracker for my warehouse…",
];

// Section 3 — three audience buckets mapped to the LOCKED plan pricing.
const BUCKETS = [
  {
    audience: "Just for me",
    desc: "Personal apps, just for you.",
    tier: "Starter",
    price: 19,
  },
  {
    audience: "My small team",
    desc: "Shared access for your whole team.",
    tier: "Growth",
    price: 49,
  },
  {
    audience: "My customers",
    desc: "Customer-facing apps your customers use.",
    tier: "Business",
    price: 99,
  },
];

// Section 4 — the trust promises (exact wording from the brief).
const TRUST = [
  "Security reviewed by the most advanced AI available",
  "Tested on every button and screen before going live",
  "Monitored 24/7 after launch",
  "Automatically fixed if anything goes wrong",
  "Backed up daily",
];

// Section 5 — six plain-English FAQs (no technical words).
const FAQS = [
  {
    q: "Do I need to know anything about building apps?",
    a: "Not at all. You describe what you want in plain words, and the whole thing is built for you — you never have to touch anything technical.",
  },
  {
    q: "How much does it cost?",
    a: "You can try it for free. When you're ready to keep your app online, plans start at $19 a month — and that covers building it, keeping it running, and any changes you want. No surprise fees.",
  },
  {
    q: "How long does it take?",
    a: "Most ideas go from a description to a working app in one sitting. You watch it come together on your screen as it happens.",
  },
  {
    q: "Is my app safe?",
    a: "Yes. Every app is checked for safety by the most advanced AI available before it ever goes live, and it's watched around the clock afterwards.",
  },
  {
    q: "What if something breaks later?",
    a: "We keep an eye on your app day and night. If something goes wrong, it's usually put right on its own before you even notice — and your app is backed up every single day.",
  },
  {
    q: "Can I make changes after it's built?",
    a: "Of course. Just tell us what you'd like changed in plain words, as often as you like. Changes are always included — you're never charged for each one.",
  },
];

type Msg = { role: "ba" | "user"; text: string };
type UI = {
  kind: string;
  options?: string[];
  plans?: any[];
  findings?: any[];
  sources?: { name: string; maps_url?: string }[];
  attribution?: string;
  prompt?: string;
  confirm_label?: string;
};

export default function Home() {
  // "landing" until the user starts building; "app" is the chat + build flow.
  const [view, setView] = useState<"landing" | "app">("landing");
  const [landingInput, setLandingInput] = useState("");
  const [phIndex, setPhIndex] = useState(0);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [ui, setUi] = useState<UI>({ kind: "text" });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [researching, setResearching] = useState(false);
  const [picks, setPicks] = useState<number[]>([]);
  const [showSources, setShowSources] = useState(false);
  const [pipeline, setPipeline] = useState<
    | "idle" | "reviewing" | "review" | "designing" | "building"
    | "securing" | "secured" | "testing" | "tested"
    | "deploying" | "live" | "deploy_failed" | "boot_failed" | "error"
  >("idle");
  const [review, setReview] = useState<any>(null);
  const [designExplain, setDesignExplain] = useState<any>(null);
  const [showDesign, setShowDesign] = useState(false);
  const [build, setBuild] = useState<any>(null);
  const [security, setSecurity] = useState<any>(null);
  const [qa, setQa] = useState<any>(null);
  const [deploy, setDeploy] = useState<any>(null);
  const [documenting, setDocumenting] = useState(false);
  const [docs, setDocs] = useState<any>(null);
  // Post-launch dashboard (Week 9): reached at ?dashboard=<projectId>.
  const [dashboardMode, setDashboardMode] = useState(false);
  const [dashboard, setDashboard] = useState<any>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dash = new URLSearchParams(window.location.search).get("dashboard");
    if (dash) {
      const pid = parseInt(dash, 10);
      setProjectId(pid);
      setDashboardMode(true);
      (async () => {
        try {
          const d = await (await fetch(`${API_URL}/dashboard/${pid}`)).json();
          setDashboard(d);
        } catch {}
      })();
      return;
    }
    // Otherwise the landing page shows first; building starts on the CTA.
  }, []);

  // Rotate the hero placeholder examples while on the landing page.
  useEffect(() => {
    if (view !== "landing" || dashboardMode) return;
    const t = setInterval(
      () => setPhIndex((i) => (i + 1) % PLACEHOLDERS.length),
      2800
    );
    return () => clearInterval(t);
  }, [view, dashboardMode]);

  // Section 1 / Section 6 CTA — leave the landing page and start the build.
  async function startBuilding(idea: string) {
    if (loading) return;
    setView("app");
    setDashboardMode(false);
    setDashboard(null);
    setPipeline("idle");
    setMessages([]);
    const pid = await start();
    const trimmed = idea.trim();
    if (pid != null && trimmed) await send(trimmed, pid);
    setLandingInput("");
  }

  async function makeAChange() {
    // "Make a change to my app" — starts a fresh BA conversation.
    setView("app");
    setDashboardMode(false);
    setDashboard(null);
    setPipeline("idle");
    setMessages([]);
    await start();
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, ui, researching]);

  async function start(): Promise<number | null> {
    const res = await fetch(`${API_URL}/conversation/start`, { method: "POST" });
    const data = await res.json();
    setProjectId(data.project_id);
    setMessages([{ role: "ba", text: data.reply }]);
    setUi(data.ui);
    return data.project_id ?? null;
  }

  async function send(text: string, pidOverride?: number) {
    // pidOverride lets the very first message be sent right after start(),
    // before the projectId state update has flushed.
    const pid = pidOverride ?? projectId;
    if (!text.trim() || pid == null || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setUi({ kind: "text" });
    setPicks([]);
    setShowSources(false);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: pid, message: text }),
      });
      const data = await res.json();
      setMessages((m) => [...m, { role: "ba", text: data.reply }]);
      setUi(data.ui);
      setResearching(Boolean(data.researching));
      // BA is done and confirmed -> Product Intelligence review-gate first.
      if (data.stage === "done") runReview();
    } catch {
      setMessages((m) => [
        ...m,
        { role: "ba", text: "Sorry, something went wrong. Could you try again?" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // Stop the research indicator once the market scan is ready.
  useEffect(() => {
    if (!researching || projectId == null) return;
    const t = setInterval(async () => {
      const res = await fetch(
        `${API_URL}/conversation/${projectId}/research-status`
      );
      const data = await res.json();
      if (data.ready) {
        setResearching(false);
        clearInterval(t);
      }
    }, 1500);
    return () => clearInterval(t);
  }, [researching, projectId]);

  async function runReview() {
    if (projectId == null) return;
    setPipeline("reviewing");
    try {
      const res = await fetch(`${API_URL}/pipeline/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      const data = await res.json();
      setReview(data.review);
      setPipeline("review");
    } catch {
      setPipeline("error");
    }
  }

  async function startPipeline(planOverride?: string) {
    if (projectId == null) return;
    setPipeline("designing");
    try {
      await fetch(`${API_URL}/pipeline/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          plan_override: planOverride ?? null,
        }),
      });
    } catch {
      setPipeline("error");
    }
  }

  // Poll the Architect until the design is complete, then auto-start the build.
  useEffect(() => {
    if (pipeline !== "designing" || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/status`);
        const data = await res.json();
        if (data.status === "done") {
          clearInterval(t);
          try {
            const ex = await fetch(
              `${API_URL}/pipeline/${projectId}/design-explanation`
            );
            if (ex.ok) setDesignExplain(await ex.json());
          } catch {}
          startBuild();
        } else if (data.status === "error") {
          setPipeline("error");
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [pipeline, projectId]);

  async function startBuild() {
    if (projectId == null) return;
    setPipeline("building");
    try {
      await fetch(`${API_URL}/pipeline/build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setPipeline("error");
    }
  }

  // Poll the Developer agents while they build.
  useEffect(() => {
    if (pipeline !== "building" || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/build-status`);
        const data = await res.json();
        setBuild(data);
        if (data.status === "done") {
          clearInterval(t);
          startSecure();
        } else if (data.status === "boot_failed") {
          // The free smoke-boot gate caught that the app doesn't start — it never
          // reached the security review. Say so honestly.
          setPipeline("boot_failed");
          clearInterval(t);
        } else if (data.status === "error") {
          setPipeline("error");
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [pipeline, projectId]);

  async function startSecure() {
    if (projectId == null) return;
    setPipeline("securing");
    try {
      await fetch(`${API_URL}/pipeline/secure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setPipeline("error");
    }
  }

  // Poll the Code Reviewer until the security check completes.
  useEffect(() => {
    if (pipeline !== "securing" || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/security-status`);
        const data = await res.json();
        if (data.status === "done") {
          setSecurity(data.certificate);
          setPipeline("secured");
          clearInterval(t);
          startQA();
        } else if (data.status === "error") {
          setSecurity(data.certificate);
          setPipeline("error");
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [pipeline, projectId]);

  async function startQA() {
    if (projectId == null) return;
    setPipeline("testing");
    try {
      await fetch(`${API_URL}/pipeline/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setPipeline("error");
    }
  }

  // Poll the QA agent. Counts only — never test names or technical details.
  useEffect(() => {
    if (pipeline !== "testing" || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/qa-status`);
        const data = await res.json();
        if (data.status === "done") {
          setQa(data);
          clearInterval(t);
          // Everything passed — take it live.
          startDeploy();
        } else if (data.status === "error") {
          setQa(data);
          setPipeline("tested");     // failures shown; nothing goes live
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [pipeline, projectId]);

  async function startDeploy() {
    if (projectId == null) return;
    setPipeline("deploying");
    try {
      await fetch(`${API_URL}/pipeline/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setPipeline("error");
    }
  }

  // Poll the DevOps agent. The climax: a live URL, or an honest snag.
  useEffect(() => {
    if (pipeline !== "deploying" || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/deploy-status`);
        const data = await res.json();
        if (data.status === "live") {
          setDeploy(data);
          setPipeline("live");
          clearInterval(t);
          startDocumentation();   // generate the guides for the finale
        } else if (data.status === "failed" || data.status === "blocked") {
          setDeploy(data);
          setPipeline("deploy_failed");
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 3000);
    return () => clearInterval(t);
  }, [pipeline, projectId]);

  async function startDocumentation() {
    if (projectId == null) return;
    setDocumenting(true);
    try {
      await fetch(`${API_URL}/pipeline/document`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setDocumenting(false);
    }
  }

  // Poll the Documentation agent; when done, show the final completion table.
  useEffect(() => {
    if (!documenting || projectId == null) return;
    const t = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/pipeline/${projectId}/documents-status`);
        const data = await res.json();
        if (data.status === "done" || data.status === "error") {
          setDocs(data);
          setDocumenting(false);
          clearInterval(t);
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [documenting, projectId]);

  async function restart() {
    setMessages([]);
    setUi({ kind: "text" });
    setPicks([]);
    setShowSources(false);
    setPipeline("idle");
    setReview(null);
    setDesignExplain(null);
    setShowDesign(false);
    setBuild(null);
    setSecurity(null);
    setQa(null);
    setDeploy(null);
    setDocumenting(false);
    setDocs(null);
    await start();
  }

  const inputHidden = ui.kind === "done" || ui.kind === "blocked";

  // Which mascot pose fits the current stage (null = no character shown).
  const pose: Pose | null =
    pipeline === "reviewing" || pipeline === "review" || pipeline === "designing"
      ? "thinking"
      : pipeline === "building"
      ? "typing"
      : pipeline === "securing" ||
        pipeline === "secured" ||
        pipeline === "testing"
      ? "inspecting"
      : pipeline === "deploying"
      ? "launching"
      : pipeline === "live"
      ? "celebrating"
      : pipeline === "idle" && !inputHidden
      ? "thinking" // BA conversation
      : null;
  const poseCaption =
    pipeline === "idle" ? "Getting to know your idea…" : undefined;

  // ---- Landing page (Sections 1–6). Shown until the user starts building. ----
  if (view === "landing" && !dashboardMode) {
    const ctaForm = (big: boolean) => (
      <form
        style={big ? s.heroForm : s.ctaForm}
        onSubmit={(e) => {
          e.preventDefault();
          startBuilding(landingInput);
        }}
      >
        <input
          style={s.heroInput}
          value={landingInput}
          onChange={(e) => setLandingInput(e.target.value)}
          placeholder={PLACEHOLDERS[phIndex]}
          aria-label="Describe your idea"
        />
        <button style={s.heroBtn} type="submit">
          Start building — it&apos;s free to try
        </button>
      </form>
    );

    return (
      <main style={s.landing}>
        {/* SECTION 1 — HERO */}
        <section style={s.hero}>
          <div style={s.heroBadge}>✦</div>
          <h1 style={s.heroH1}>Describe your idea. We&apos;ll build the app.</h1>
          {ctaForm(true)}
          <div style={s.heroNote}>No signup required to start.</div>
        </section>

        {/* SECTION 2 — SOCIAL PROOF (honest, not fabricated) */}
        <section style={s.statsRow}>
          <div style={s.stat}>
            <div style={s.statNum}>15</div>
            <div style={s.statLabel}>specialized AI agents</div>
          </div>
          <div style={s.stat}>
            <div style={s.statNum}>9</div>
            <div style={s.statLabel}>
              development phases, built &amp; verified
            </div>
          </div>
          <div style={s.stat}>
            <div style={s.statNum}>✓</div>
            <div style={s.statLabel}>
              security-reviewed by the most advanced AI available
            </div>
          </div>
        </section>

        {/* SECTION 3 — THREE AUDIENCE BUCKETS */}
        <section style={s.section}>
          <h2 style={s.sectionH2}>Who is it for?</h2>
          <div style={s.bucketRow}>
            {BUCKETS.map((b) => (
              <div key={b.tier} style={s.bucket}>
                <div style={s.bucketAudience}>{b.audience}</div>
                <div style={s.bucketDesc}>{b.desc}</div>
                <div style={s.bucketPrice}>
                  ${b.price}
                  <span style={s.bucketPer}>/month</span>
                </div>
                <div style={s.bucketTier}>{b.tier}</div>
                <div style={s.bucketIncl}>
                  Everything included — building, unlimited changes, and
                  keeping it online.
                </div>
                <button
                  style={s.bucketBtn}
                  onClick={() => startBuilding(landingInput)}
                >
                  Start building
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* SECTION 4 — TRUST */}
        <section style={s.section}>
          <h2 style={s.sectionH2}>Every app we build is:</h2>
          <div style={s.trustWrap}>
            {TRUST.map((t, i) => (
              <div
                key={i}
                style={{
                  ...s.trustItem,
                  ...(i === TRUST.length - 1 ? { borderBottom: "none" } : {}),
                }}
              >
                <span style={s.checkCircle}>✓</span>
                <span>{t}</span>
              </div>
            ))}
          </div>
        </section>

        {/* SECTION 5 — FAQ */}
        <section style={s.section}>
          <h2 style={s.sectionH2}>Questions, answered</h2>
          <div style={s.faqWrap}>
            {FAQS.map((f, i) => (
              <details key={i} className="faqItem">
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* SECTION 6 — BOTTOM CTA (same headline + input as the hero) */}
        <section style={s.section}>
          <div style={s.ctaBand}>
            <h2 style={s.ctaH2}>
              Describe your idea. We&apos;ll build the app.
            </h2>
            {ctaForm(false)}
            <div style={s.heroNote}>No signup required to start.</div>
          </div>
        </section>

        <footer style={s.footer}>
          Built by 15 AI agents, from your first sentence to a live app.
        </footer>
      </main>
    );
  }

  return (
    <main style={s.main}>
      <div style={s.card}>
        <h1 style={s.header}>
          {dashboardMode ? "Your app dashboard" : "Let’s build your idea"}
        </h1>

        {/* Build-dashboard character — pose follows the current stage. */}
        {!dashboardMode && pose && (
          <BuildCharacter pose={pose} caption={poseCaption} />
        )}

        {/* Post-launch dashboard (Week 9) — four sections, no technical words. */}
        {dashboardMode && dashboard && (
          <div style={s.reviewCard}>
            {/* 1. App status */}
            <div style={s.dashRow}>
              <span style={s.dashLabel}>App status</span>
              <span style={s.dashVal}>
                {dashboard.app_status === "live"
                  ? "Live ✓"
                  : dashboard.app_status === "issue_detected"
                  ? "Issue detected"
                  : "Not live"}
              </span>
            </div>
            {dashboard.live_url && (
              <a href={dashboard.live_url} target="_blank" rel="noopener noreferrer"
                 style={s.doneLink}>
                {dashboard.live_url}
              </a>
            )}

            {/* 2. This month cost */}
            <div style={s.reviewSection}>
              <div style={s.reviewHead}>This month</div>
              {dashboard.cost ? (
                <>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>This month so far</span>
                    <span style={s.dashVal}>${dashboard.cost.this_month_so_far?.toFixed(2)}</span>
                  </div>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>Projected by end of month</span>
                    <span style={s.dashVal}>
                      {dashboard.cost.projected_month_end != null
                        ? `$${dashboard.cost.projected_month_end.toFixed(2)}` : "—"}
                    </span>
                  </div>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>Your budget</span>
                    <span style={s.dashVal}>
                      {dashboard.cost.budget != null
                        ? `$${dashboard.cost.budget.toFixed(0)}/month` : "not set"}
                    </span>
                  </div>
                  <div style={{
                    ...s.budgetBox,
                    ...(dashboard.cost.over_budget ? s.budgetWarn : s.budgetOk),
                  }}>
                    {dashboard.cost.status_text}
                  </div>
                </>
              ) : (
                <div style={s.designBody}>
                  Cost tracking will appear once your app has been running for a day.
                </div>
              )}
            </div>

            {/* 3. Recent activity */}
            <div style={s.reviewSection}>
              <div style={s.reviewHead}>Recent activity</div>
              {dashboard.activity ? (
                <>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>Uptime</span>
                    <span style={s.dashVal}>{dashboard.activity.uptime_pct}%</span>
                  </div>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>Response time</span>
                    <span style={s.dashVal}>
                      {dashboard.activity.avg_response_ms ?? "—"} ms
                    </span>
                  </div>
                  <div style={s.dashRow}>
                    <span style={s.dashLabel}>Errors</span>
                    <span style={s.dashVal}>{dashboard.activity.error_count}</span>
                  </div>
                </>
              ) : (
                <div style={s.designBody}>
                  We&apos;ll show activity once your app has been checked a few times.
                </div>
              )}
            </div>

            {/* Level-3 issues needing the user */}
            {dashboard.issues && dashboard.issues.length > 0 && (
              <div style={s.reviewSection}>
                <div style={s.reviewHead}>Needs your attention</div>
                {dashboard.issues.map((iss: any, i: number) => (
                  <div key={i} style={s.designBody}>
                    <strong>{iss.title}</strong>
                    <div style={{ whiteSpace: "pre-wrap" }}>{iss.instructions}</div>
                  </div>
                ))}
              </div>
            )}

            {/* 4. One button */}
            <button style={{ ...s.choiceBtn, ...s.confirmBtn, marginTop: "8px" }}
                    onClick={makeAChange}>
              Make a change to my app
            </button>
          </div>
        )}

        <div style={s.chat}>
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                ...s.bubble,
                ...(m.role === "ba" ? s.ba : s.user),
              }}
            >
              {m.text}
            </div>
          ))}

          {loading && <div style={{ ...s.bubble, ...s.ba }}>…</div>}

          {researching && (
            <div style={s.research}>
              <span style={s.dot} /> Researching your market…
            </div>
          )}

          {/* Quick-pick choices */}
          {ui.kind === "choices" && (
            <div style={s.choices}>
              {ui.options?.map((o) => (
                <button key={o} style={s.choiceBtn} onClick={() => send(o)}>
                  {o}
                </button>
              ))}
            </div>
          )}

          {/* Mobile options */}
          {ui.kind === "mobile_options" && (
            <div style={s.cards}>
              {(ui as any).options?.map((o: any) => (
                <div key={o.id} style={s.optCard} onClick={() => send(o.id)}>
                  <div style={s.optTitle}>{o.title}</div>
                  <div style={s.optDetail}>{o.detail}</div>
                </div>
              ))}
            </div>
          )}

          {/* Competitor findings */}
          {ui.kind === "ci_findings" && (
            <div style={s.cards}>
              {ui.findings?.map((fnd: any) => {
                const on = picks.includes(fnd.index);
                return (
                  <div
                    key={fnd.index}
                    style={{ ...s.findCard, ...(on ? s.findOn : {}) }}
                    onClick={() =>
                      setPicks((p) =>
                        on ? p.filter((x) => x !== fnd.index) : [...p, fnd.index]
                      )
                    }
                  >
                    <div style={s.findTop}>
                      <strong>{fnd.theme}</strong>
                      <span style={s.count}>{fnd.count} mentions</span>
                    </div>
                    <div style={s.optDetail}>{fnd.suggestion}</div>
                    <div style={s.check}>{on ? "✓ Added" : "Tap to add"}</div>
                  </div>
                );
              })}
              {ui.sources && ui.sources.length > 0 && (
                <div style={s.sources}>
                  <button
                    style={s.sourcesToggle}
                    onClick={() => setShowSources((v) => !v)}
                  >
                    Based on {ui.sources.length} real {showSources ? "▴" : "▾"}{" "}
                    place{ui.sources.length === 1 ? "" : "s"} near you
                  </button>
                  {showSources && (
                    <div style={s.sourceList}>
                      {ui.sources.map((sc, i) =>
                        sc.maps_url ? (
                          <a
                            key={i}
                            href={sc.maps_url}
                            target="_blank"
                            rel="noreferrer"
                            style={s.sourceLink}
                          >
                            {sc.name} ↗
                          </a>
                        ) : (
                          <span key={i} style={s.sourceLink}>
                            {sc.name}
                          </span>
                        )
                      )}
                    </div>
                  )}
                  {ui.attribution && (
                    <div style={s.attribution}>{ui.attribution}</div>
                  )}
                </div>
              )}
              <div style={s.choices}>
                <button
                  style={s.choiceBtn}
                  onClick={() => send(picks.length ? picks.join(",") : "none")}
                >
                  {picks.length ? `Add ${picks.length} feature(s)` : "No thanks"}
                </button>
              </div>
            </div>
          )}

          {/* Plan options */}
          {ui.kind === "plan_options" && (
            <div style={s.cards}>
              {ui.plans?.map((p: any) => (
                <div
                  key={p.id}
                  style={{
                    ...s.planCard,
                    ...(p.recommended ? s.planRecommended : {}),
                  }}
                  onClick={() => send(p.id)}
                >
                  <div style={s.optTitle}>
                    {p.name}
                    {p.recommended && <span style={s.recBadge}>Fits your budget</span>}
                    {p.over_budget && <span style={s.overBadge}>Above your budget</span>}
                  </div>
                  <div style={s.optDetail}>{p.summary}</div>
                  <div style={s.planMeta}>
                    {p.price} · {p.time}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Design vibe */}
          {ui.kind === "design_vibe" && (
            <div style={s.choices}>
              {ui.options?.map((o) => (
                <button key={o} style={s.choiceBtn} onClick={() => send(o)}>
                  {o}
                </button>
              ))}
            </div>
          )}

          {/* Confirmation */}
          {ui.kind === "summary" && (
            <div style={s.choices}>
              <button
                style={{ ...s.choiceBtn, ...s.confirmBtn }}
                onClick={() => send(ui.confirm_label ?? "Yes")}
              >
                {ui.confirm_label ?? "Confirm"}
              </button>
              <button style={s.choiceBtn} onClick={() => send("No, I'd like to change something")}>
                Change something
              </button>
            </div>
          )}

          {ui.kind === "blocked" && (
            <div style={s.choices}>
              <button style={{ ...s.choiceBtn, ...s.confirmBtn }} onClick={restart}>
                Start over with a different idea
              </button>
            </div>
          )}

          {/* Product Intelligence: reviewing */}
          {pipeline === "reviewing" && (
            <div style={s.pipeline}>
              <span style={s.spinner} />
              <span>Reviewing your plan…</span>
            </div>
          )}

          {/* Product Intelligence: review-gate card */}
          {pipeline === "review" && review && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>Before we build — a quick review</div>
              {review.product_read && (
                <div style={s.reviewRead}>{review.product_read}</div>
              )}

              {review.budget_assessment && (
                <div
                  style={{
                    ...s.budgetBox,
                    ...(review.budget_assessment.verdict === "comfortable"
                      ? s.budgetOk
                      : s.budgetWarn),
                  }}
                >
                  <strong>Budget:</strong> {review.budget_assessment.detail}
                </div>
              )}

              {review.recommendations?.length > 0 && (
                <div style={s.reviewSection}>
                  <div style={s.reviewHead}>Recommendations</div>
                  {review.recommendations.map((r: any, i: number) => (
                    <div key={i} style={s.recItem}>
                      <strong>{r.title}:</strong> {r.detail}
                    </div>
                  ))}
                </div>
              )}

              {review.features_dropped?.length > 0 && (
                <div style={s.reviewSection}>
                  <div style={s.reviewHead}>Set aside (didn’t fit)</div>
                  {review.features_dropped.map((f: any, i: number) => (
                    <div key={i} style={s.dropItem}>
                      • {f.feature} <span style={s.dropReason}>— {f.reason}</span>
                    </div>
                  ))}
                </div>
              )}

              {review.priorities?.must_have?.length > 0 && (
                <div style={s.reviewSection}>
                  <div style={s.reviewHead}>We’ll build first</div>
                  {review.priorities.must_have.map((m: string, i: number) => (
                    <div key={i} style={s.priItem}>✓ {m}</div>
                  ))}
                </div>
              )}

              {review.missing_essentials?.length > 0 && (
                <div style={s.reviewSection}>
                  <div style={s.reviewHead}>We’ll also include</div>
                  {review.missing_essentials.map((m: string, i: number) => (
                    <div key={i} style={s.priItem}>+ {m}</div>
                  ))}
                </div>
              )}

              {(() => {
                const rec = review.budget_assessment?.recommended_tier;
                const verdict = review.budget_assessment?.verdict;
                const tierNames: Record<string, string> = {
                  quick: "Quick launch (~$15/mo)",
                  production: "Production ready (~$50/mo)",
                  scale: "Scale ready (~$150/mo)",
                };
                const showDowngrade =
                  (verdict === "tight" || verdict === "unrealistic") &&
                  rec &&
                  tierNames[rec];
                return (
                  <div style={{ ...s.choices, marginTop: "12px" }}>
                    {showDowngrade && (
                      <button
                        style={{ ...s.choiceBtn, ...s.confirmBtn }}
                        onClick={() => startPipeline(rec)}
                      >
                        Start smaller — {tierNames[rec]}
                      </button>
                    )}
                    <button
                      style={
                        showDowngrade
                          ? s.choiceBtn
                          : { ...s.choiceBtn, ...s.confirmBtn }
                      }
                      onClick={() => startPipeline()}
                    >
                      {showDowngrade ? "Build it anyway" : "Looks good — build it"}
                    </button>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Architect handoff */}
          {pipeline === "designing" && (
            <div style={s.pipeline}>
              <span style={s.spinner} />
              <span>Designing your app…</span>
            </div>
          )}

          {/* Design complete — professional message + collapsible explanation */}
          {designExplain && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>✓ {designExplain.headline}</div>
              <button
                style={s.sourcesToggle}
                onClick={() => setShowDesign((v) => !v)}
              >
                {showDesign ? "▴ Hide" : "▸ See what we designed & why"}
              </button>
              {showDesign && (
                <div style={s.designBody}>{designExplain.explanation}</div>
              )}
            </div>
          )}

          {/* Building — file list + X of Y (never any code) */}
          {pipeline === "building" && (
            <div style={s.reviewCard}>
              <div style={s.pipeline}>
                <span style={s.spinner} />
                <span>Building your app…</span>
              </div>
              {build && (
                <>
                  <div style={s.buildCount}>
                    {build.complete} of {build.total || "…"} files complete
                  </div>
                  <div style={s.fileList}>
                    {build.files?.map((f: any, i: number) => (
                      <div key={i} style={s.fileRow}>
                        <span style={s.fileTick}>
                          {f.status === "needs_review" ? "⚠" : "✓"}
                        </span>
                        {f.filename}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Security review — no technical details, no model names */}
          {pipeline === "securing" && (
            <div style={s.pipeline}>
              <span style={s.spinner} />
              <span>Making sure everything is safe and secure…</span>
            </div>
          )}
          {security &&
            (pipeline === "secured" || pipeline === "testing" ||
              pipeline === "tested" || pipeline === "deploying" ||
              pipeline === "live" || pipeline === "deploy_failed") && (
              <div style={s.reviewCard}>
                <div style={s.reviewTitle}>Security check passed ✓</div>
                <div style={s.designBody}>
                  Your app passed all security checks. Your data is protected.
                  Security review completed by our most advanced AI model.
                </div>
              </div>
            )}

          {/* QA — one plain sentence, no test names or technical details */}
          {pipeline === "testing" && (
            <div style={s.pipeline}>
              <span style={s.spinner} />
              <span>Testing every button and screen…</span>
            </div>
          )}
          {qa &&
            (pipeline === "tested" || pipeline === "deploying" ||
              pipeline === "live" || pipeline === "deploy_failed") && (
              <div style={s.reviewCard}>
                <div style={s.reviewTitle}>
                  {qa.failed === 0
                    ? `${qa.total} tests run. Everything passed. ✓`
                    : `${qa.total} tests run.`}
                </div>
                <div style={s.designBody}>
                  {qa.failed === 0
                    ? "We tried every button, form and screen — including the ways people accidentally break things. It all held up."
                    : "We tried every button, form and screen. We hit something we couldn't fix automatically, so we stopped rather than ship something broken — our team needs to take a look."}
                </div>
              </div>
            )}

          {/* DevOps: deploying — the friendly wait before the climax */}
          {pipeline === "deploying" && (
            <div style={s.deployWait}>
              <div style={s.rocket}>🚀</div>
              <div style={s.deployWaitText}>Getting your app ready for the world…</div>
              <div style={s.deployWaitSub}>
                Setting up your own private space, turning on security, and giving
                it a web address.
              </div>
            </div>
          )}

          {/* DevOps: THE CLIMAX — your app is live */}
          {pipeline === "live" && deploy && (
            <div style={s.climax}>
              <div style={s.confetti}>🎉</div>
              <div style={s.climaxTitle}>Your app is ready!</div>
              <a
                href={deploy.live_url}
                target="_blank"
                rel="noopener noreferrer"
                style={s.liveLink}
              >
                {deploy.live_url}
              </a>
              <div style={s.badgeRow}>
                {deploy.security_certified && (
                  <span style={s.badge}>Security verified ✓</span>
                )}
                <span style={s.badge}>
                  {(deploy.tests_passed ?? 0)} tests passed ✓
                </span>
              </div>
              {deploy.monthly_cost_estimate != null && (
                <div style={s.cost}>
                  Running cost: <strong>${Number(deploy.monthly_cost_estimate).toFixed(2)}/month</strong>
                </div>
              )}
              {deploy.auto_fixed && (
                <div style={s.honestNote}>
                  Recovered automatically after one hiccup during setup.
                </div>
              )}
            </div>
          )}

          {/* Documentation: putting the guides together */}
          {documenting && (
            <div style={s.pipeline}>
              <span style={s.spinner} />
              <span>Putting together your guides…</span>
            </div>
          )}

          {/* Documentation: FINAL completion table — real values only */}
          {docs && docs.status === "done" && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>All done — here&apos;s everything</div>
              <table style={s.doneTable}>
                <tbody>
                  <tr>
                    <td style={s.doneCell}>Live app link</td>
                    <td style={s.doneVal}>
                      {docs.is_live && docs.live_url ? (
                        <a href={docs.live_url} target="_blank"
                           rel="noopener noreferrer" style={s.doneLink}>
                          {docs.live_url} ✓
                        </a>
                      ) : ("Not live yet")}
                    </td>
                  </tr>
                  <tr>
                    <td style={s.doneCell}>Security review</td>
                    <td style={s.doneVal}>
                      {docs.security_passed ? "Passed ✓" : "Not passed yet"}
                    </td>
                  </tr>
                  <tr>
                    <td style={s.doneCell}>Tests passed</td>
                    <td style={s.doneVal}>
                      {docs.tests_available
                        ? `${docs.tests_passed} of ${docs.tests_total} ✓`
                        : "Not available yet"}
                    </td>
                  </tr>
                  <tr>
                    <td style={s.doneCell}>User guide</td>
                    <td style={s.doneVal}>
                      {docs.user_guide_ready ? "Ready ✓" : "—"}
                    </td>
                  </tr>
                  <tr>
                    <td style={s.doneCell}>Demo video script</td>
                    <td style={s.doneVal}>
                      {docs.demo_script_ready ? "Ready ✓" : "—"}
                    </td>
                  </tr>
                  <tr>
                    <td style={s.doneCell}>Monthly running cost</td>
                    <td style={s.doneVal}>
                      {docs.monthly_cost_estimate != null
                        ? `$${Number(docs.monthly_cost_estimate).toFixed(2)}/month ✓`
                        : "Not available yet"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {/* DevOps: honest snag (blocked/failed) — never a fake success */}
          {pipeline === "deploy_failed" && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>Not live yet</div>
              <div style={s.designBody}>
                Your app passed its tests, but we hit a snag putting it online and
                stopped rather than launch something that isn&apos;t right. It&apos;s
                been flagged for a final pass.
              </div>
            </div>
          )}

          {pipeline === "boot_failed" && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>Not ready yet</div>
              <div style={s.designBody}>
                It didn&apos;t start correctly, so we&apos;ve sent it back to be
                rebuilt. We caught this early — before the full safety review — so
                nothing was wasted.
              </div>
            </div>
          )}

          {pipeline === "error" && (
            <div style={s.pipeline}>
              <span>Something went wrong. Please try again.</span>
            </div>
          )}

          <div ref={endRef} />
        </div>

        {!inputHidden && !dashboardMode && (
          <form
            style={s.form}
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <input
              style={s.input}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your answer…"
            />
            <button style={s.send} type="submit" disabled={loading}>
              Send
            </button>
          </form>
        )}
      </div>
    </main>
  );
}

const PURPLE = "#534AB7";

const s: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    display: "flex",
    justifyContent: "center",
    padding: "24px",
  },

  // ================= Landing page (Week 10 Part 1) =================
  landing: { width: "100%", color: "#1f2937", background: "#ffffff" },

  // Section 1 — hero
  hero: {
    maxWidth: "860px",
    margin: "0 auto",
    padding: "72px 24px 48px",
    textAlign: "center",
  },
  heroBadge: {
    width: "56px",
    height: "56px",
    margin: "0 auto 28px",
    borderRadius: "16px",
    background: PURPLE,
    color: "#ffffff",
    fontSize: "28px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 8px 24px rgba(83,74,183,0.28)",
  },
  heroH1: {
    fontSize: "clamp(34px, 6vw, 58px)",
    fontWeight: 800,
    lineHeight: 1.08,
    letterSpacing: "-0.02em",
    color: "#1f2937",
  },
  heroForm: {
    display: "flex",
    flexWrap: "wrap",
    gap: "12px",
    marginTop: "36px",
    justifyContent: "center",
  },
  heroInput: {
    flex: "1 1 320px",
    minWidth: 0,
    padding: "18px 22px",
    fontSize: "18px",
    border: "2px solid #e5e0f7",
    borderRadius: "14px",
    outline: "none",
    color: "#1f2937",
    background: "#ffffff",
  },
  heroBtn: {
    padding: "18px 28px",
    fontSize: "18px",
    fontWeight: 700,
    color: "#ffffff",
    background: PURPLE,
    border: "none",
    borderRadius: "14px",
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  heroNote: { marginTop: "16px", fontSize: "15px", color: "#6b7280" },

  // Section 2 — social proof
  statsRow: {
    maxWidth: "960px",
    margin: "0 auto",
    padding: "24px",
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: "16px",
  },
  stat: { flex: "1 1 220px", maxWidth: "300px", textAlign: "center", padding: "20px" },
  statNum: { fontSize: "52px", fontWeight: 800, color: PURPLE, lineHeight: 1 },
  statLabel: { marginTop: "12px", fontSize: "16px", color: "#4b5563", lineHeight: 1.45 },

  // Shared section wrapper + heading
  section: { maxWidth: "1000px", margin: "0 auto", padding: "52px 24px" },
  sectionH2: {
    textAlign: "center",
    fontSize: "clamp(26px, 4vw, 36px)",
    fontWeight: 800,
    color: "#1f2937",
    marginBottom: "8px",
  },

  // Section 3 — audience buckets
  bucketRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "20px",
    justifyContent: "center",
    marginTop: "32px",
  },
  bucket: {
    flex: "1 1 260px",
    maxWidth: "320px",
    background: "#ffffff",
    border: "1px solid #e5e0f7",
    borderRadius: "20px",
    padding: "30px 26px",
    textAlign: "center",
    boxShadow: "0 4px 20px rgba(83,74,183,0.07)",
    display: "flex",
    flexDirection: "column",
  },
  bucketAudience: { fontSize: "22px", fontWeight: 800, color: "#1f2937" },
  bucketDesc: { marginTop: "6px", fontSize: "16px", color: "#6b7280", lineHeight: 1.4 },
  bucketPrice: {
    marginTop: "22px",
    fontSize: "44px",
    fontWeight: 800,
    color: PURPLE,
    lineHeight: 1,
  },
  bucketPer: { fontSize: "16px", fontWeight: 600, color: "#9ca3af" },
  bucketTier: {
    marginTop: "6px",
    fontSize: "14px",
    fontWeight: 700,
    color: PURPLE,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  bucketIncl: {
    marginTop: "16px",
    fontSize: "14px",
    color: "#6b7280",
    lineHeight: 1.55,
    flex: 1,
  },
  bucketBtn: {
    marginTop: "22px",
    padding: "14px 18px",
    fontSize: "16px",
    fontWeight: 700,
    color: "#ffffff",
    background: PURPLE,
    border: "none",
    borderRadius: "12px",
    cursor: "pointer",
  },

  // Section 4 — trust
  trustWrap: {
    maxWidth: "660px",
    margin: "32px auto 0",
    background: "#faf9ff",
    border: "1px solid #e5e0f7",
    borderRadius: "22px",
    padding: "20px 32px",
  },
  trustItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: "16px",
    padding: "16px 0",
    fontSize: "18px",
    lineHeight: 1.4,
    color: "#1f2937",
    borderBottom: "1px solid #efedfb",
  },
  checkCircle: {
    flex: "0 0 auto",
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    background: PURPLE,
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "15px",
    fontWeight: 800,
  },

  // Section 5 — FAQ
  faqWrap: { maxWidth: "740px", margin: "32px auto 0" },

  // Section 6 — bottom CTA
  ctaBand: {
    background: "linear-gradient(160deg, #faf5ff 0%, #eef0ff 100%)",
    border: "1px solid #e5e0f7",
    borderRadius: "24px",
    maxWidth: "880px",
    margin: "0 auto",
    padding: "52px 28px",
    textAlign: "center",
  },
  ctaH2: {
    fontSize: "clamp(26px, 4vw, 40px)",
    fontWeight: 800,
    letterSpacing: "-0.02em",
    color: "#1f2937",
    lineHeight: 1.12,
  },
  ctaForm: {
    display: "flex",
    flexWrap: "wrap",
    gap: "12px",
    marginTop: "28px",
    justifyContent: "center",
  },
  footer: {
    textAlign: "center",
    padding: "48px 24px",
    color: "#9ca3af",
    fontSize: "14px",
  },
  // ================= End landing page =================

  card: { width: "100%", maxWidth: "560px", display: "flex", flexDirection: "column" },
  header: { fontSize: "22px", fontWeight: 600, marginBottom: "16px" },
  chat: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    paddingBottom: "16px",
  },
  bubble: {
    maxWidth: "85%",
    padding: "12px 16px",
    borderRadius: "16px",
    fontSize: "15px",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
  },
  ba: { alignSelf: "flex-start", background: "#f3f0ff", color: "#1f2937" },
  user: { alignSelf: "flex-end", background: PURPLE, color: "#ffffff" },
  pipeline: {
    alignSelf: "flex-start",
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "12px 16px",
    background: "#f3f0ff",
    borderRadius: "16px",
    fontSize: "15px",
    color: "#1f2937",
  },
  spinner: {
    width: "18px",
    height: "18px",
    borderRadius: "50%",
    border: "2px solid #d6ccff",
    borderTopColor: PURPLE,
    display: "inline-block",
    animation: "spin 0.8s linear infinite",
  },
  doneMark: {
    color: "#16a34a",
    fontWeight: 700,
    fontSize: "18px",
  },
  reviewCard: {
    alignSelf: "stretch",
    background: "#faf9ff",
    border: "1px solid #e5e0f7",
    borderRadius: "16px",
    padding: "16px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  reviewTitle: { fontSize: "16px", fontWeight: 700, color: "#1f2937" },
  reviewRead: { fontSize: "14px", color: "#4b5563", fontStyle: "italic" },
  budgetBox: { fontSize: "13px", padding: "10px 12px", borderRadius: "10px" },
  budgetOk: { background: "#dcfce7", color: "#166534" },
  budgetWarn: { background: "#fef3c7", color: "#92400e" },
  reviewSection: { display: "flex", flexDirection: "column", gap: "4px" },
  reviewHead: {
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
    color: "#6b7280",
    letterSpacing: "0.03em",
  },
  recItem: { fontSize: "13px", color: "#374151", lineHeight: 1.4 },
  designBody: {
    fontSize: "14px",
    color: "#374151",
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    marginTop: "4px",
  },
  // ---- DevOps: deploying wait ----
  deployWait: {
    alignSelf: "stretch",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "8px",
    padding: "28px 16px",
    background: "#f3f0ff",
    borderRadius: "16px",
    textAlign: "center",
  },
  rocket: { fontSize: "40px", animation: "float 1.6s ease-in-out infinite" },
  deployWaitText: { fontSize: "16px", fontWeight: 700, color: "#1f2937" },
  deployWaitSub: {
    fontSize: "13px", color: "#6b7280", lineHeight: 1.5, maxWidth: "360px",
  },
  // ---- DevOps: the climax ----
  climax: {
    alignSelf: "stretch",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "14px",
    padding: "32px 20px",
    background: "linear-gradient(160deg, #faf5ff 0%, #eef2ff 100%)",
    border: "1px solid #e5e0f7",
    borderRadius: "20px",
    textAlign: "center",
  },
  confetti: { fontSize: "48px", animation: "pop 0.5s ease-out" },
  climaxTitle: { fontSize: "26px", fontWeight: 800, color: "#4c1d95" },
  liveLink: {
    fontSize: "18px",
    fontWeight: 700,
    color: PURPLE,
    wordBreak: "break-all",
    textDecoration: "none",
    padding: "12px 18px",
    background: "#ffffff",
    border: `2px solid ${PURPLE}`,
    borderRadius: "12px",
    maxWidth: "100%",
  },
  badgeRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
    justifyContent: "center",
  },
  badge: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#166534",
    background: "#dcfce7",
    padding: "6px 12px",
    borderRadius: "999px",
  },
  cost: { fontSize: "15px", color: "#374151" },
  honestNote: { fontSize: "12px", color: "#92400e", fontStyle: "italic" },
  // ---- final completion table ----
  doneTable: { width: "100%", borderCollapse: "collapse", fontSize: "14px" },
  doneCell: {
    padding: "10px 8px", color: "#6b7280", borderBottom: "1px solid #eee",
    width: "45%",
  },
  doneVal: {
    padding: "10px 8px", color: "#1f2937", fontWeight: 600,
    borderBottom: "1px solid #eee",
  },
  doneLink: { color: PURPLE, fontWeight: 700, textDecoration: "none",
              wordBreak: "break-all" },
  // ---- post-launch dashboard ----
  dashRow: {
    display: "flex", justifyContent: "space-between", alignItems: "baseline",
    gap: "12px", fontSize: "14px", padding: "3px 0",
  },
  dashLabel: { color: "#6b7280" },
  dashVal: { color: "#1f2937", fontWeight: 600, textAlign: "right" },
  buildCount: { fontSize: "13px", fontWeight: 600, color: PURPLE, marginTop: "4px" },
  fileList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    marginTop: "8px",
    maxHeight: "220px",
    overflowY: "auto",
  },
  fileRow: { fontSize: "13px", color: "#374151", fontFamily: "monospace" },
  fileTick: { color: "#16a34a", marginRight: "8px" },
  dropItem: { fontSize: "13px", color: "#374151" },
  dropReason: { color: "#9ca3af" },
  priItem: { fontSize: "13px", color: "#374151" },
  research: {
    alignSelf: "flex-start",
    fontSize: "13px",
    color: "#6b7280",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontStyle: "italic",
  },
  dot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: PURPLE,
    display: "inline-block",
    animation: "pulse 1s infinite",
  },
  choices: { display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "4px" },
  choiceBtn: {
    padding: "10px 16px",
    borderRadius: "20px",
    border: `1px solid ${PURPLE}`,
    background: "#ffffff",
    color: PURPLE,
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
  },
  confirmBtn: { background: PURPLE, color: "#ffffff" },
  cards: { display: "flex", flexDirection: "column", gap: "10px", marginTop: "4px" },
  optCard: {
    border: "1px solid #e5e7eb",
    borderRadius: "12px",
    padding: "14px",
    cursor: "pointer",
  },
  optTitle: { fontWeight: 600, fontSize: "15px", marginBottom: "4px" },
  optDetail: { fontSize: "14px", color: "#4b5563", lineHeight: 1.4 },
  findCard: {
    border: "1px solid #e5e7eb",
    borderRadius: "12px",
    padding: "14px",
    cursor: "pointer",
  },
  findOn: { borderColor: PURPLE, background: "#faf5ff" },
  findTop: { display: "flex", justifyContent: "space-between", marginBottom: "6px" },
  count: { fontSize: "12px", color: PURPLE, fontWeight: 600 },
  check: { marginTop: "8px", fontSize: "13px", color: PURPLE, fontWeight: 600 },
  planCard: {
    border: "1px solid #e5e7eb",
    borderRadius: "12px",
    padding: "14px",
    cursor: "pointer",
  },
  planMeta: { marginTop: "8px", fontSize: "13px", color: PURPLE, fontWeight: 600 },
  planRecommended: { borderColor: PURPLE, borderWidth: "2px" },
  recBadge: {
    marginLeft: "8px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#16a34a",
    background: "#dcfce7",
    padding: "2px 8px",
    borderRadius: "999px",
  },
  overBadge: {
    marginLeft: "8px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#b91c1c",
    background: "#fee2e2",
    padding: "2px 8px",
    borderRadius: "999px",
  },
  sources: { marginTop: "4px" },
  sourcesToggle: {
    background: "none",
    border: "none",
    color: "#6b7280",
    fontSize: "13px",
    cursor: "pointer",
    padding: "4px 0",
    textAlign: "left",
  },
  sourceList: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    padding: "4px 0 4px 8px",
  },
  sourceLink: { fontSize: "13px", color: PURPLE, textDecoration: "none" },
  attribution: { fontSize: "11px", color: "#9ca3af", marginTop: "4px" },
  form: { display: "flex", gap: "10px", position: "sticky", bottom: 0, background: "#fff", paddingTop: "8px" },
  input: {
    flex: 1,
    padding: "12px 16px",
    fontSize: "15px",
    border: "1px solid #d1d5db",
    borderRadius: "10px",
    outline: "none",
  },
  send: {
    padding: "12px 22px",
    fontSize: "15px",
    fontWeight: 600,
    color: "#fff",
    background: PURPLE,
    border: "none",
    borderRadius: "10px",
    cursor: "pointer",
  },
};
