"use client";

/**
 * Admin → Menu → Review screen
 *
 * After a PDF upload (POST /admin/menu/upload), extracted items are stored as
 * PENDING and never auto-published. This screen:
 *   1. Loads the pending items via GET /admin/menu/pending
 *   2. Lets the owner EDIT any field inline
 *   3. Lets the owner REJECT (remove) wrong items via DELETE /admin/menu/{item_id}
 *   4. Publishes the approved (and possibly edited) items via POST /admin/menu/confirm
 *      -- this is the ONLY way extracted items go live.
 *
 * SECURITY NOTE (authorization / data integrity):
 *   - This client relies on cookie-based session auth (credentials: 'include').
 *     The BACKEND MUST strictly enforce that the authenticated admin owns each
 *     referenced item ID for GET /pending, DELETE /admin/menu/{id}, and
 *     POST /admin/menu/confirm. Per-item ownership/tenant scoping must be
 *     verified server-side to prevent IDOR (deleting/publishing another
 *     restaurant's items). Client code cannot enforce this.
 *   - Price validation here (validatePrice/validateRow) is a UX convenience
 *     ONLY. The BACKEND MUST independently validate and normalize price
 *     (reject negatives, enforce format/precision) before publishing to the
 *     live customer-facing menu. Never trust client-submitted prices.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ?? "";

interface PendingMenuItem {
  id: number;
  name: string;
  price: string;
  category: string;
  description: string | null;
  status: string;
  source: string;
  created_at: string;
  image_url: string | null;
}

type FieldErrors = Partial<Record<"name" | "price" | "category", string>>;

interface RowState extends PendingMenuItem {
  errors: FieldErrors;
  removing: boolean;
}

function toRowState(item: PendingMenuItem): RowState {
  return { ...item, errors: {}, removing: false };
}

function validatePrice(raw: string): boolean {
  const trimmed = raw.trim();
  if (trimmed === "") return false;
  const numeric = trimmed.replace(/^\$/, "");
  return /^\d+(\.\d{1,2})?$/.test(numeric);
}

function validateRow(row: RowState): FieldErrors {
  const errors: FieldErrors = {};
  if (!row.name.trim()) {
    errors.name = "Name is required";
  }
  if (!row.category.trim()) {
    errors.category = "Category is required";
  }
  if (!validatePrice(row.price)) {
    errors.price = "Enter a valid price (e.g. 9.99)";
  }
  return errors;
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: any) => d?.msg ?? String(d)).join(", ");
    }
  } catch {
    // ignore JSON parse failure, fall through to generic message
  }
  return `Request failed with status ${res.status}`;
}

function isValidPDF(file: File): boolean {
  return file.type === "application/pdf" && file.size <= 5 * 1024 * 1024; // 5MB limit
}

function sanitizeFileName(fileName: string): string {
  return fileName.replace(/[^a-zA-Z0-9-_\.]/g, "");
}

export default function MenuReviewPage() {
  const [rows, setRows] = useState<RowState[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadPending = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/menu/pending`, {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        throw new Error(await parseErrorMessage(res));
      }
      const data: PendingMenuItem[] = await res.json();
      if (!Array.isArray(data)) {
        throw new Error("Unexpected response format while loading pending items");
      }
      setRows(data.map(toRowState));
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "Failed to load pending menu items. Please try again."
      );
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  const updateField = useCallback(
    (id: number, field: "name" | "price" | "category" | "description", value: string) => {
      setRows((prev) =>
        prev.map((row) => {
          if (row.id !== id) return row;
          const updated: RowState = { ...row, [field]: value };
          updated.errors = validateRow(updated);
          return updated;
        })
      );
      setSubmitError(null);
      setSuccessMessage(null);
    },
    []
  );

  const removeItem = useCallback(async (id: number) => {
    const confirmed =
      typeof window === "undefined"
        ? true
        : window.confirm(
            "Reject and permanently remove this extracted item? It will not be published."
          );
    if (!confirmed) return;

    setRows((prev) =>
      prev.map((row) => (row.id === id ? { ...row, removing: true } : row))
    );
    setSubmitError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/admin/menu/${id}`, {
        method: "DELETE",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(await parseErrorMessage(res));
      }
      setRows((prev) => prev.filter((row) => row.id !== id));
      setSuccessMessage("Item rejected and removed.");
    } catch (err) {
      setRows((prev) =>
        prev.map((row) => (row.id === id ? { ...row, removing: false } : row))
      );
      setSubmitError(
        err instanceof Error ? err.message : "Failed to remove item. Please try again."
      );
    }
  }, []);

  const hasBlockingErrors = useMemo(
    () => rows.some((row) => Object.keys(row.errors).length > 0),
    [rows]
  );

  const validateAll = useCallback((): boolean => {
    let ok = true;
    setRows((prev) =>
      prev.map((row) => {
        const errors = validateRow(row);
        if (Object.keys(errors).length > 0) ok = false;
        return { ...row, errors };
      })
    );
    return ok;
  }, []);

  const handleConfirm = useCallback(async () => {
    setSubmitError(null);
    setSuccessMessage(null);

    if (rows.length === 0) {
      setSubmitError("There are no pending items to publish.");
      return;
    }

    if (!validateAll()) {
      setSubmitError("Please fix the highlighted fields before publishing.");
      return;
    }

    setSubmitting(true);
    try {
      // NOTE: Client-side price validation above is UX only. The backend must
      // re-validate and normalize each price (reject negatives / bad formats)
      // and enforce per-item ownership before publishing to the live menu.
      const payload = {
        items: rows.map((row) => ({
          id: row.id,
          name: row.name.trim(),
          price: row.price.trim(),
          category: row.category.trim(),
          description: row.description?.trim() || null,
          image_url: row.image_url || null,
        })),
      };

      const res = await fetch(`${API_BASE_URL}/admin/menu/confirm`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(await parseErrorMessage(res));
      }

      setRows([]);
      setSuccessMessage(
        "All approved items were published to the live menu."
      );
    } catch (err) {
      setSubmitError(
        err instanceof Error
          ? err.message
          : "Failed to publish items. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }, [rows, validateAll]);

  return (
    <main style={styles.page}>
      <div style={styles.container}>
        <header style={styles.header}>
          <h1 style={styles.title}>Review Extracted Menu Items</h1>
          <p style={styles.subtitle}>
            These items were <strong>auto-extracted from an uploaded PDF</strong> and
            are not yet visible to customers. Please check every field carefully,
            correct any mistakes, remove anything that looks wrong, then click
            <strong> Publish Approved Items</strong>. Nothing goes live until you
            confirm.
          </p>
        </header>

        {loading && <div style={styles.infoBox}>Loading pending items&hellip;</div>}

        {!loading && loadError && (
          <div style={styles.errorBox} role="alert">
            <span>{loadError}</span>
            <button type="button" style={styles.retryButton} onClick={loadPending}>
              Retry
            </button>
          </div>
        )}

        {!loading && !loadError && rows.length === 0 && (
          <div style={styles.infoBox}>
            No pending items awaiting review. Upload a menu PDF from the Manage
            Menu screen to extract new items.
          </div>
        )}

        {!loading && !loadError && rows.length > 0 && (
          <>
            {submitError && (
              <div style={styles.errorBox} role="alert">
                {submitError}
              </div>
            )}
            {successMessage && (
              <div style={styles.successBox} role="status">
                {successMessage}
              </div>
            )}

            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Name</th>
                    <th style={styles.th}>Price</th>
                    <th style={styles.th}>Category</th>
                    <th style={styles.th}>Description</th>
                    <th style={styles.th}>Source</th>
                    <th style={styles.th}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} style={row.removing ? styles.rowRemoving : undefined}>
                      <td style={styles.td}>
                        <input
                          style={inputStyle(row.errors.name)}
                          value={row.name}
                          disabled={row.removing || submitting}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            updateField(row.id, "name", e.target.value)
                          }
                        />
                        {row.errors.name && (
                          <span style={styles.fieldError}>{row.errors.name}</span>
                        )}
                      </td>
                      <td style={styles.td}>
                        <input
                          style={inputStyle(row.errors.price)}
                          value={row.price}
                          disabled={row.removing || submitting}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            updateField(row.id, "price", e.target.value)
                          }
                        />
                        {row.errors.price && (
                          <span style={styles.fieldError}>{row.errors.price}</span>
                        )}
                      </td>
                      <td style={styles.td}>
                        <input
                          style={inputStyle(row.errors.category)}
                          value={row.category}
                          disabled={row.removing || submitting}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            updateField(row.id, "category", e.target.value)
                          }
                        />
                        {row.errors.category && (
                          <span style={styles.fieldError}>{row.errors.category}</span>
                        )}
                      </td>
                      <td style={styles.td}>
                        <textarea
                          style={styles.textarea}
                          value={row.description ?? ""}
                          disabled={row.removing || submitting}
                          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                            updateField(row.id, "description", e.target.value)
                          }
                          rows={2}
                        />
                      </td>
                      <td style={styles.td}>
                        <span 
