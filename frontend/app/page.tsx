"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    | "securing" | "secured" | "error"
  >("idle");
  const [review, setReview] = useState<any>(null);
  const [designExplain, setDesignExplain] = useState<any>(null);
  const [showDesign, setShowDesign] = useState(false);
  const [build, setBuild] = useState<any>(null);
  const [security, setSecurity] = useState<any>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    start();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, ui, researching]);

  async function start() {
    const res = await fetch(`${API_URL}/conversation/start`, { method: "POST" });
    const data = await res.json();
    setProjectId(data.project_id);
    setMessages([{ role: "ba", text: data.reply }]);
    setUi(data.ui);
  }

  async function send(text: string) {
    if (!text.trim() || projectId == null || loading) return;
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
        body: JSON.stringify({ project_id: projectId, message: text }),
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
    await start();
  }

  const inputHidden = ui.kind === "done" || ui.kind === "blocked";

  return (
    <main style={s.main}>
      <div style={s.card}>
        <h1 style={s.header}>Let&apos;s build your idea</h1>

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
          {pipeline === "secured" && (
            <div style={s.reviewCard}>
              <div style={s.reviewTitle}>Security check passed ✓</div>
              <div style={s.designBody}>
                Your app passed all security checks. Your data is protected.
                Security review completed by our most advanced AI model.
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

        {!inputHidden && (
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

const PURPLE = "#7c3aed";

const s: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    display: "flex",
    justifyContent: "center",
    padding: "24px",
  },
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
