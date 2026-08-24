"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useApi, AuthStatus } from "../providers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StripeStatusResponse {
  connected: boolean;
  stripe_account_id?: string | null;
}

type LoadState = "idle" | "loading" | "ready" | "error";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { apiFetch, isAuthenticated, isLoading: authLoading } = useApi();

  const [status, setStatus] = useState<StripeStatusResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [statusError, setStatusError] = useState<string | null>(null);

  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const [payNowMessage, setPayNowMessage] = useState<string | null>(null);

  // -------------------------------------------------------------------
  // Load Stripe connection status
  // -------------------------------------------------------------------

  const loadStatus = useCallback(async () => {
    if (!isAuthenticated) {
      setLoadState("idle");
      return;
    }

    setLoadState("loading");
    setStatusError(null);

    try {
      const res = await apiFetch("/admin/stripe/status", { method: "GET" });

      if (res.status === 401 || res.status === 403) {
        setStatusError(
          "You are not authorized to view Stripe settings. Please log in as the shop owner."
        );
        setLoadState("error");
        return;
      }

      if (!res.ok) {
        throw new Error(`Failed to load Stripe status (status ${res.status})`);
      }

      const data = (await res.json()) as StripeStatusResponse;

      if (typeof data?.connected !== "boolean") {
        throw new Error("Malformed response from /admin/stripe/status");
      }

      setStatus(data);
      setLoadState("ready");
    } catch (err) {
      setStatusError(
        err instanceof Error ? err.message : "Failed to load Stripe connection status."
      );
      setLoadState("error");
    }
  }, [apiFetch, isAuthenticated]);

  useEffect(() => {
    if (authLoading) return;
    loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated]);

  // -------------------------------------------------------------------
  // Kick off Stripe Connect OAuth flow
  // -------------------------------------------------------------------

  const handleConnect = useCallback(async () => {
    setConnectError(null);
    setConnecting(true);

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (!apiBase) {
        throw new Error(
          "NEXT_PUBLIC_API_BASE_URL is not configured — cannot start Stripe Connect."
        );
      }

      const res = await apiFetch("/admin/stripe/connect", { method: "GET" });

      if (res.status === 401 || res.status === 403) {
        throw new Error("You must be logged in as the shop owner to connect Stripe.");
      }

      if (!res.ok) {
        throw new Error(`Failed to start Stripe Connect (status ${res.status})`);
      }

      // The backend may either:
      //   1) respond with an HTTP redirect that the browser's fetch already
      //      followed (res.redirected / res.url points at Stripe's hosted page), or
      //   2) respond with JSON containing the authorize URL under a common key.
      let target: string | null = null;

      if (res.redirected && res.url) {
        target = res.url;
      } else {
        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const data = await res.json().catch(() => null as any);
          target =
            (data && (data.url || data.authorize_url || data.redirect_url)) || null;
        }
      }

      // Fallback: navigate the browser directly to the backend endpoint and
      // let it perform the redirect to Stripe's hosted OAuth flow.
      if (!target) {
        target = `${apiBase}/admin/stripe/connect`;
      }

      window.location.href = target;
    } catch (err) {
      setConnectError(
        err instanceof Error ? err.message : "Failed to connect to Stripe."
      );
      setConnecting(false);
    }
  }, [apiFetch]);

  // -------------------------------------------------------------------
  // Demo "Pay Now" control — disabled until Stripe is connected.
  // -------------------------------------------------------------------

  const handlePayNow = useCallback(() => {
    setPayNowMessage(
      "Stripe-hosted checkout would open here. No card data is ever handled by this site."
    );
  }, []);

  const isConnected = status?.connected === true;

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------

  if (authLoading) {
    return (
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1rem" }}>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1rem" }}>
        <h1>Settings</h1>
        <p>Please log in as the shop owner to manage payment settings.</p>
        <AuthStatus />
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0 }}>Settings</h1>
        <AuthStatus />
      </header>

      {/* Stripe connection card */}
      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <h2>Stripe Connection</h2>

        {loadState === "loading" && <p className="muted">Checking Stripe connection status…</p>}

        {loadState === "error" && (
          <div role="alert" style={{ color: "#b91c1c", marginBottom: "1rem" }}>
            <p>{statusError}</p>
            <button type="button" onClick={loadStatus}>
              Retry
            </button>
          </div>
        )}

        {loadState === "ready" && (
          <div style={{ marginBottom: "1rem" }}>
            <p>
              Status:{" "}
              <strong style={{ color: isConnected ? "#15803d" : "#b45309" }}>
                {isConnected ? "Connected" : "Not connected"}
              </strong>
            </p>
            {isConnected && status?.stripe_account_id && (
              <p className="muted" style={{ fontSize: "0.9rem" }}>
                Account: {status.stripe_account_id}
              </p>
            )}
          </div>
        )}

        {!isConnected && (
          <p className="muted" style={{ marginBottom: "1rem" }}>
            Connect Stripe to start accepting payments.
          </p>
        )}

        {connectError && (
          <p role="alert" style={{ color: "#b91c1c", marginBottom: "1rem" }}>
            {connectError}
          </p>
        )}

        <button
          type="button"
          onClick={handleConnect}
          disabled={connecting || isConnected}
        >
          {isConnected ? "Stripe Connected" : connecting ? "Connecting…" : "Connect Stripe"}
        </button>

        {isConnected && (
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
            Your Stripe account is linked. Reconnect isn't necessary unless you disconnect it
            from your Stripe dashboard.
          </p>
        )}
      </section>

      {/* Payment controls — disabled until Stripe is connected */}
      <section className="card">
        <h2>Payments</h2>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Payments are processed entirely through Stripe's hosted checkout — this site never
          handles raw card details.
        </p>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <button type="button" onClick={handlePayNow} disabled={!isConnected}>
            Pay Now
          </button>

          {!isConnected && (
            <span className="muted" style={{ fontSize: "0.9rem" }}>
              Connect Stripe to start accepting payments.{" "}
              <a
                href="#connect-stripe"
                onClick={(e) => {
                  e.preventDefault();
                  handleConnect();
                }}
              >
                Connect now
              </a>
            </span>
          )}
        </div>

        {payNowMessage && (
          <p style={{ marginTop: "1rem" }} className="muted">
            {payNowMessage}
          </p>
        )}
      </section>
    </main>
  );
}
