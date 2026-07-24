// src/services/sqlApi.js
// ─────────────────────────
// All HTTP calls for the SQL engine.

import { API_BASE_URL } from "../config";

const BASE = `${API_BASE_URL}/sql`;

// ── Session management ────────────────────────────────────────────────────────

/**
 * Create a SQL session by registering cleaned file_ids as named tables.
 * @param {Array<{file_id: string, table_name: string}>} tables
 */
export async function createSQLSession(tables) {
  const res = await fetch(`${BASE}/session`, {  
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tables }),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // SQLSessionInfo
}

export async function getSession(sessionId) {
  const res = await fetch(`${BASE}/session/${sessionId}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function deleteSession(sessionId) {
  await fetch(`${BASE}/session/${sessionId}`, { method: "DELETE" });
}

// ── Queries ───────────────────────────────────────────────────────────────────

/**
 * Natural language → SQL → execute.
 * @param {string} sessionId
 * @param {string} question   - plain English question
 * @param {string} apiKey     - Gemini API key (optional; server can use GEMINI_API_KEY)
 */
export async function nlQuery(sessionId, question, apiKey) {
  const res = await fetch(`${BASE}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
    },
    body: JSON.stringify({ session_id: sessionId, question, max_rows: 500 }),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // QueryResult
}

/**
 * Execute raw SQL directly (no LLM).
 */
export async function rawQuery(sessionId, sql) {
  const res = await fetch(`${BASE}/raw`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, sql, max_rows: 500 }),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getHistory(sessionId) {
  const res = await fetch(`${BASE}/history/${sessionId}`);
  if (!res.ok) throw await res.json();
  return res.json(); // QueryHistoryResponse
}
