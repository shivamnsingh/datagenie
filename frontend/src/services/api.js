// src/services/api.js
// ─────────────────────
// All HTTP calls to the FastAPI backend.

const BASE = "http://localhost:8000/api";

// ── Ingest ────────────────────────────────────────────────────────────────────

export async function uploadFiles(fileList) {
  const form = new FormData();
  for (const f of fileList) form.append("files", f);

  const res = await fetch(`${BASE}/ingest/upload`, { method: "POST", body: form });
  if (!res.ok) throw await res.json();
  return res.json(); // IngestResponse
}

export async function previewData(fileId, rows = 20) {
  const res = await fetch(`${BASE}/ingest/preview/${fileId}?rows=${rows}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

// ── Clean ─────────────────────────────────────────────────────────────────────

export async function fetchNullReport(fileId) {
  const res = await fetch(`${BASE}/clean/nulls/${fileId}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function fetchOutlierReport(fileId) {
  const res = await fetch(`${BASE}/clean/outliers/${fileId}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function fetchDuplicateReport(fileId) {
  const res = await fetch(`${BASE}/clean/duplicates/${fileId}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function previewCleaning(config) {
  const res = await fetch(`${BASE}/clean/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // CleaningSummaryPreview
}

export async function applyCleaning(config) {
  const res = await fetch(`${BASE}/clean/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw await res.json();
  return res.json(); // CleaningResult
}

// ── Export ────────────────────────────────────────────────────────────────────

export async function exportDataset(fileId, format = "csv") {
  const res = await fetch(`${BASE}/export/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_id: fileId, format }),
  });
  if (!res.ok) throw await res.json();

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cleaned_data.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}
