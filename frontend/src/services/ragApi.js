// src/services/ragApi.js
// ─────────────────────────
// HTTP calls for the RAG chat engine.

import { API_BASE_URL } from "../config";

const BASE = `${API_BASE_URL}/rag`;

/**
 * Build a vector index from cleaned file_ids.
 * @param {string[]} fileIds
 * @param {Object} tableNames  - { file_id: table_name }
 * @param {string} apiKey
 */
export async function buildIndex(fileIds, tableNames, apiKey) {
  const res = await fetch(`${BASE}/index`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
    },
    body: JSON.stringify({
      file_ids: fileIds,
      table_names: tableNames,
      extra_context: [],
    }),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // BuildIndexResponse
}

export async function getIndexStatus(ragSessionId) {
  const res = await fetch(`${BASE}/index/${ragSessionId}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

/**
 * Send a chat message with full conversation history.
 * @param {string} ragSessionId
 * @param {string} question
 * @param {Array}  history   - [{role, content}]
 * @param {string} apiKey
 */
export async function ragChat(ragSessionId, question, history, apiKey) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
    },
    body: JSON.stringify({
      rag_session_id: ragSessionId,
      question,
      conversation_history: history,
    }),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // RAGChatResponse
}
