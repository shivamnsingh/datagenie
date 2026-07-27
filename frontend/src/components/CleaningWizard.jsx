// src/components/CleaningWizard.jsx
// ────────────────────────────────────
// Multi-step wizard: Upload → Diagnose → Configure → Preview → Done
// Drop-in ready. Uses Tailwind CSS.

import { useState, useCallback } from "react";
import {
  uploadFiles,
  fetchNullReport,
  fetchOutlierReport,
  fetchDuplicateReport,
  previewCleaning,
  applyCleaning,
  exportDataset,
  previewData,
} from "../services/api";

// ── Inline icons (SF Symbols-style: thin stroke, monochrome, no fill) ──────────

function IconCheck(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 10.5 8 14.5 16 6" />
    </svg>
  );
}

function IconUpload(props) {
  return (
    <svg width="28" height="28" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10 13V3.5M6.5 7 10 3.5 13.5 7" />
      <path d="M3.5 13.5V15a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5v-1.5" />
    </svg>
  );
}

function IconDownload(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10 3v9.5M6.5 9 10 12.5 13.5 9" />
      <path d="M3.5 14v1.5A1.5 1.5 0 0 0 5 17h10a1.5 1.5 0 0 0 1.5-1.5V14" />
    </svg>
  );
}

function IconGear(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="10" cy="10" r="2.75" />
      <path d="M10 3.5v2M10 14.5v2M16.5 10h-2M5.5 10h-2M14.6 5.4l-1.4 1.4M6.8 13.2l-1.4 1.4M14.6 14.6l-1.4-1.4M6.8 6.8 5.4 5.4" />
    </svg>
  );
}

function IconLink(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M8.5 11.5a3 3 0 0 0 4.24 0l2-2a3 3 0 0 0-4.24-4.24l-.9.9" />
      <path d="M11.5 8.5a3 3 0 0 0-4.24 0l-2 2a3 3 0 0 0 4.24 4.24l.9-.9" />
    </svg>
  );
}

// ── Constants ──────────────────────────────────────────────────────────────────

const NULL_OPTIONS = [
  { value: "fill_mean",     label: "Fill with Mean",     icon: "≈" },
  { value: "fill_median",   label: "Fill with Median",   icon: "⊕" },
  { value: "fill_mode",     label: "Fill with Mode",     icon: "⊞" },
  { value: "fill_forward",  label: "Forward Fill",       icon: "→" },
  { value: "fill_backward", label: "Backward Fill",      icon: "←" },
  { value: "drop_rows",     label: "Drop Rows",          icon: "✕", danger: true },
  { value: "drop_column",   label: "Drop Column",        icon: "⌫", danger: true },
];

const OUTLIER_OPTIONS = [
  { value: "remove_iqr",      label: "Remove (IQR)",        icon: "✕", danger: true },
  { value: "cap_percentile",  label: "Cap at Percentile",   icon: "⊟" },
  { value: "keep",            label: "Keep Unchanged",      icon: "○" },
];

const STEPS = ["Upload", "Diagnose", "Configure", "Preview", "Done"];

// ── Small reusable pieces ──────────────────────────────────────────────────────

function StepBar({ current }) {
  return (
    <div className="flex items-center justify-center mb-8">
      {STEPS.map((label, i) => (
        <div key={i} className="flex items-center">
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold
              border transition-colors duration-150 ease-out
              ${i < current ? "bg-gray-800 border-gray-700 text-gray-300"
                : i === current ? "bg-blue-600 border-blue-600 text-white"
                : "bg-gray-900 border-gray-700 text-gray-600"}`}>
              {i < current ? <IconCheck /> : i + 1}
            </div>
            <span className={`text-xs font-medium ${i === current ? "text-blue-400" : i < current ? "text-gray-400" : "text-gray-600"}`}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`w-10 h-px mx-3 ${i < current ? "bg-gray-700" : "bg-gray-800"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

function Badge({ children, color = "neutral" }) {
  const colors = {
    neutral: "bg-gray-800/60 text-gray-300 border-gray-700",
    red: "bg-red-950/40 text-red-400 border-red-900",
    amber: "bg-amber-950/30 text-amber-400 border-amber-900",
    emerald: "bg-emerald-950/30 text-emerald-400 border-emerald-900",
    blue: "bg-blue-950/30 text-blue-400 border-blue-900",
  };
  return (
    <span className={`text-[11px] px-1.5 py-0.5 rounded border font-mono tabular-nums ${colors[color]}`}>
      {children}
    </span>
  );
}

function StrategyButton({ option, selected, onClick }) {
  return (
    <button
      onClick={() => onClick(option.value)}
      className={`px-2.5 py-1 rounded-md text-xs font-medium border
        transition-colors duration-150 ease-out
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
        ${selected
          ? option.danger
            ? "bg-red-950/40 border-red-800 text-red-400"
            : "bg-blue-950/40 border-blue-700 text-blue-400"
          : "bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"}`}>
      <span className="font-mono mr-1 text-gray-500">{option.icon}</span>{option.label}
    </button>
  );
}

// ── Step 1: Upload ─────────────────────────────────────────────────────────────

function UploadStep({ onNext }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFiles = async (files) => {
    if (!files.length) return;
    setLoading(true);
    setError(null);
    try {
      const data = await uploadFiles(files);
      onNext(data);
    } catch (e) {
      setError(e?.detail || "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles([...e.dataTransfer.files].filter(f => f.name.endsWith(".csv")));
  }, []);

  return (
    <div className="max-w-xl mx-auto">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") document.getElementById("file-input").click(); }}
        className={`border border-dashed rounded-lg py-14 px-8 text-center cursor-pointer
          transition-colors duration-150 ease-out
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
          ${dragging ? "border-blue-500 bg-blue-950/10" : "border-gray-700 hover:border-gray-600 hover:bg-gray-900/40"}`}
        onClick={() => document.getElementById("file-input").click()}>
        <IconUpload className="mx-auto text-gray-500 mb-3" />
        <div className="text-sm font-semibold text-gray-100 mb-1">Drop CSV files here</div>
        <div className="text-xs text-gray-500 mb-4">or click to browse — supports multiple files</div>
        <Badge>CSV only</Badge>
        <input
          id="file-input"
          type="file"
          accept=".csv"
          multiple
          className="hidden"
          onChange={(e) => handleFiles([...e.target.files])}
        />
      </div>

      {loading && (
        <div className="mt-4 space-y-2" aria-live="polite" aria-label="Analysing schema">
          <div className="h-3 w-2/3 rounded bg-gray-800 animate-pulse" />
          <div className="h-3 w-full rounded bg-gray-800 animate-pulse" />
          <div className="h-3 w-5/6 rounded bg-gray-800 animate-pulse" />
        </div>
      )}
      {error && (
        <div className="mt-4 p-3 rounded-lg bg-red-950/30 border border-red-900 text-red-400 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

// ── Step 2: Diagnose ───────────────────────────────────────────────────────────

function DiagnoseStep({ ingestData, onNext, onBack }) {
  const { schemas, join_suggestions } = ingestData;

  return (
    <div className="space-y-5">
      {schemas.map((schema) => (
        <div key={schema.file_id} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <div>
              <span className="font-semibold text-sm text-gray-100">{schema.filename}</span>
              <span className="text-gray-500 text-xs ml-2.5 font-mono tabular-nums">
                {schema.row_count.toLocaleString()} rows · {schema.col_count} cols
              </span>
            </div>
            <div className="flex gap-1.5">
              {schema.duplicate_row_count > 0 && (
                <Badge color="amber">{schema.duplicate_row_count} duplicates</Badge>
              )}
              {schema.columns.filter(c => c.null_count > 0).length > 0 && (
                <Badge color="red">
                  {schema.columns.filter(c => c.null_count > 0).length} cols with nulls
                </Badge>
              )}
            </div>
          </div>

          {/* Column table */}
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-950 z-10">
                <tr className="text-gray-500 text-[11px] font-mono uppercase tracking-wide">
                  <th className="px-4 py-2 text-left font-medium">Column</th>
                  <th className="px-4 py-2 text-left font-medium">Type</th>
                  <th className="px-4 py-2 text-left font-medium">Nulls</th>
                  <th className="px-4 py-2 text-left font-medium">Unique</th>
                  <th className="px-4 py-2 text-left font-medium">Flags</th>
                  <th className="px-4 py-2 text-left font-medium">Sample</th>
                </tr>
              </thead>
              <tbody>
                {schema.columns.map((col) => (
                  <tr key={col.name} className="border-t border-gray-800/70 hover:bg-gray-800/40 transition-colors duration-150 ease-out">
                    <td className="px-4 py-2.5 font-mono text-gray-100 font-medium">{col.name}</td>
                    <td className="px-4 py-2.5">
                      <Badge>{col.dtype}</Badge>
                    </td>
                    <td className="px-4 py-2.5 font-mono tabular-nums">
                      {col.null_count > 0
                        ? <span className="text-red-400">{col.null_count} ({col.null_pct}%)</span>
                        : <span className="text-gray-600">none</span>}
                    </td>
                    <td className="px-4 py-2.5 font-mono tabular-nums text-gray-400">{col.unique_count.toLocaleString()}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1 flex-wrap">
                        {col.suggested_pk && <Badge color="blue">PK?</Badge>}
                        {col.is_datetime && <Badge>datetime</Badge>}
                        {col.is_categorical && <Badge>category</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs font-mono max-w-[200px] truncate">
                      {col.sample_values.join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {/* Join suggestions */}
      {join_suggestions.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-gray-100 mb-3">
            <IconLink className="text-gray-500" />
            Join Keys Detected
          </div>
          <div className="space-y-2">
            {join_suggestions.map((j, i) => (
              <div key={i} className="flex items-center gap-2.5 text-sm">
                <code className="text-gray-200 font-mono text-xs">{j.left_file}.{j.left_col}</code>
                <span className="text-gray-600">↔</span>
                <code className="text-gray-200 font-mono text-xs">{j.right_file}.{j.right_col}</code>
                <Badge color={j.confidence > 0.85 ? "emerald" : "amber"}>
                  {Math.round(j.confidence * 100)}% confidence
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="px-4 py-2 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          ← Back
        </button>
        <button onClick={() => onNext()} className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          Configure Cleaning →
        </button>
      </div>
    </div>
  );
}

// ── Step 3: Configure ──────────────────────────────────────────────────────────

function ConfigureStep({ ingestData, onNext, onBack }) {
  const schema = ingestData.schemas[0]; // primary file
  const fileId = ingestData.file_ids[0];

  // Build initial config state
  const nullCols = schema.columns.filter(c => c.null_count > 0);
  const [nullStrategies, setNullStrategies] = useState(
    Object.fromEntries(nullCols.map(c => [c.name, "fill_mean"]))
  );
  const [outlierStrategies, setOutlierStrategies] = useState({});
  const [standardization, setStandardization] = useState({
    lowercase_columns: true,
    replace_spaces_with_underscore: true,
    trim_whitespace: true,
    drop_constant_columns: false,
    drop_duplicates: schema.duplicate_row_count > 0,
  });
  const [loading, setLoading] = useState(false);

  const handleNext = async () => {
    setLoading(true);
    try {
      const config = {
        file_id: fileId,
        null_configs: Object.entries(nullStrategies).map(([col, strategy]) => ({
          column: col,
          strategy,
          custom_value: null,
        })),
        outlier_configs: Object.entries(outlierStrategies).map(([col, strategy]) => ({
          column: col,
          strategy,
          lower_percentile: 1.0,
          upper_percentile: 99.0,
        })),
        dtype_configs: [],
        standardization,
      };

      const preview = await previewCleaning(config);
      onNext({ config, preview });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* NULL HANDLING */}
      {nullCols.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" aria-hidden="true" />
            <span className="font-semibold text-sm text-gray-100">Null Value Handling</span>
          </div>
          <div className="text-gray-500 text-xs mb-4 font-mono ml-3.5">{nullCols.length} columns need attention</div>
          <div className="space-y-4">
            {nullCols.map(col => (
              <div key={col.name}>
                <div className="flex items-center gap-2 mb-2">
                  <code className="text-gray-200 font-mono text-sm">{col.name}</code>
                  <Badge color="red">{col.null_count} nulls · {col.null_pct}%</Badge>
                  <Badge>{col.dtype}</Badge>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {NULL_OPTIONS
                    .filter(o => col.is_numeric ? true : !["fill_mean","fill_median"].includes(o.value))
                    .map(opt => (
                      <StrategyButton
                        key={opt.value}
                        option={opt}
                        selected={nullStrategies[col.name] === opt.value}
                        onClick={(val) => setNullStrategies(s => ({ ...s, [col.name]: val }))}
                      />
                    ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* OUTLIER HANDLING */}
      {schema.columns.filter(c => c.is_numeric).length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" aria-hidden="true" />
            <span className="font-semibold text-sm text-gray-100">Outlier Handling</span>
          </div>
          <div className="text-gray-500 text-xs mb-4 font-mono ml-3.5">Numeric columns · IQR-based detection</div>
          <div className="space-y-4">
            {schema.columns.filter(c => c.is_numeric).map(col => (
              <div key={col.name}>
                <div className="flex items-center gap-2 mb-2">
                  <code className="text-gray-200 font-mono text-sm">{col.name}</code>
                  <Badge>numeric</Badge>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {OUTLIER_OPTIONS.map(opt => (
                    <StrategyButton
                      key={opt.value}
                      option={opt}
                      selected={(outlierStrategies[col.name] || "keep") === opt.value}
                      onClick={(val) => setOutlierStrategies(s => ({ ...s, [col.name]: val }))}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* STANDARDIZATION */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <IconGear className="text-gray-500" />
          <span className="font-semibold text-sm text-gray-100">Standardization</span>
        </div>
        <div className="grid grid-cols-2 gap-1">
          {[
            ["lowercase_columns", "Lowercase column names"],
            ["replace_spaces_with_underscore", "Replace spaces with _"],
            ["trim_whitespace", "Trim whitespace from strings"],
            ["drop_constant_columns", "Drop constant columns"],
            ["drop_duplicates", `Drop duplicate rows (${schema.duplicate_row_count} found)`],
          ].map(([key, label]) => (
            <label key={key} className="flex items-center gap-2.5 cursor-pointer p-2.5 rounded-md hover:bg-gray-800 transition-colors duration-150 ease-out">
              <input
                type="checkbox"
                checked={standardization[key]}
                onChange={(e) => setStandardization(s => ({ ...s, [key]: e.target.checked }))}
                className="w-3.5 h-3.5 accent-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
              <span className="text-sm text-gray-300">{label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="px-4 py-2 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          ← Back
        </button>
        <button
          onClick={handleNext}
          disabled={loading}
          className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          {loading ? "Calculating…" : "Preview Changes →"}
        </button>
      </div>
    </div>
  );
}

// ── Step 4: Preview & Confirm ──────────────────────────────────────────────────

function PreviewStep({ configData, onNext, onBack }) {
  const { config, preview } = configData;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleApply = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await applyCleaning(config);
      onNext(result);
    } catch (e) {
      setError(e?.detail || "Cleaning failed.");
    } finally {
      setLoading(false);
    }
  };

  const dropPct = preview.pct_rows_dropped_estimate;

  return (
    <div className="space-y-5">
      {/* Summary tiles */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Rows Before</div>
          <div className="text-2xl font-semibold tabular-nums text-gray-50">{preview.rows_before.toLocaleString()}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Rows After (est.)</div>
          <div className={`text-2xl font-semibold tabular-nums ${dropPct > 10 ? "text-amber-400" : "text-gray-50"}`}>
            {preview.rows_after_estimate.toLocaleString()}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Rows Dropped</div>
          <div className={`text-2xl font-semibold tabular-nums flex items-center gap-1 ${dropPct > 10 ? "text-amber-400" : "text-gray-50"}`}>
            {dropPct > 0 && <span className="text-sm">▼</span>}
            {dropPct}%
          </div>
        </div>
      </div>

      {/* Warnings */}
      {preview.warnings.map((w, i) => (
        <div key={i} className="p-3 rounded-lg bg-amber-950/20 border border-amber-900/50 text-amber-400 text-sm">
          {w}
        </div>
      ))}

      {/* Steps list */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-800 font-semibold text-gray-100 text-sm">
          Cleaning Steps ({preview.steps.length})
        </div>
        <div className="divide-y divide-gray-800/70">
          {preview.steps.map((step, i) => (
            <div key={i} className="px-4 py-2.5 flex items-center gap-3 text-sm">
              <div className="w-5 h-5 rounded-full bg-gray-800 flex items-center justify-center text-[11px] text-gray-400 font-mono tabular-nums flex-shrink-0">
                {i + 1}
              </div>
              {step.column && <code className="text-gray-200 font-mono text-xs">{step.column}</code>}
              <span className="text-gray-300">{step.action}</span>
              {step.rows_affected > 0 && (
                <Badge color="amber">
                  {step.rows_affected} rows
                </Badge>
              )}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-950/30 border border-red-900 text-red-400 text-sm">{error}</div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="px-4 py-2 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          ← Adjust Config
        </button>
        <button
          onClick={handleApply}
          disabled={loading}
          className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          {loading ? "Cleaning…" : "Apply Cleaning"}
        </button>
      </div>
    </div>
  );
}

// ── Step 5: Done ───────────────────────────────────────────────────────────────

function DoneStep({ result, filename, onProceed }) {
  const improvement = result.quality_score_after - result.quality_score_before;

  return (
    <div className="text-center space-y-6">
      <div className="flex flex-col items-center gap-2">
        <span className="w-7 h-7 rounded-full bg-emerald-950/40 border border-emerald-900 flex items-center justify-center">
          <IconCheck className="text-emerald-400" />
        </span>
        <div className="text-lg font-semibold text-gray-50">Data cleaned successfully</div>
      </div>

      <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-left">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Clean Rows</div>
          <div className="text-xl font-semibold tabular-nums text-gray-50">{result.rows_after.toLocaleString()}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-left">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Quality Score</div>
          <div className={`text-xl font-semibold tabular-nums flex items-center gap-1 ${improvement >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            <span className="text-sm">{improvement >= 0 ? "▲" : "▼"}</span>
            {Math.abs(improvement).toFixed(1)}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-left">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Score After</div>
          <div className="text-xl font-semibold tabular-nums text-blue-400">{result.quality_score_after}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-left">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-1.5">Steps Applied</div>
          <div className="text-xl font-semibold tabular-nums text-gray-50">{result.steps_applied.length}</div>
        </div>
      </div>

      {result.warnings.map((w, i) => (
        <div key={i} className="p-3 rounded-lg bg-amber-950/20 border border-amber-900/50 text-amber-400 text-sm max-w-md mx-auto text-left">
          {w}
        </div>
      ))}

      <div className="flex justify-center gap-2">
        {["csv", "json", "xlsx"].map(fmt => (
          <button
            key={fmt}
            onClick={() => exportDataset(result.clean_file_id, fmt)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-gray-900 border border-gray-700 hover:border-gray-600 text-gray-300 hover:text-gray-100 text-xs font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            <IconDownload />.{fmt.toUpperCase()}
          </button>
        ))}
      </div>

      <button
        onClick={onProceed}
        className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
        Proceed to SQL Query Engine →
      </button>
    </div>
  );
}

// ── Main Wizard ────────────────────────────────────────────────────────────────

// Props:
//   onCleaningDone(result, filename) — called when cleaning completes
//                                      so App.jsx can pass file_id to SQL + RAG
export default function CleaningWizard({ onCleaningDone }) {
  const [step, setStep] = useState(0);
  const [ingestData, setIngestData] = useState(null);
  const [configData, setConfigData] = useState(null);
  const [result, setResult] = useState(null);

  // The primary filename of the first uploaded file
  const primaryFilename = ingestData?.schemas?.[0]?.filename ?? "dataset.csv";

  const handleDone = (r) => {
    setResult(r);
    setStep(4);
    // Notify parent immediately so nav unlocks
    onCleaningDone?.(r, primaryFilename);
  };

  return (
    <div className="w-full">
      <StepBar current={step} />

      {step === 0 && (
        <UploadStep onNext={(data) => { setIngestData(data); setStep(1); }} />
      )}
      {step === 1 && ingestData && (
        <DiagnoseStep
          ingestData={ingestData}
          onNext={() => setStep(2)}
          onBack={() => setStep(0)}
        />
      )}
      {step === 2 && ingestData && (
        <ConfigureStep
          ingestData={ingestData}
          onNext={(data) => { setConfigData(data); setStep(3); }}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && configData && (
        <PreviewStep
          configData={configData}
          onNext={handleDone}
          onBack={() => setStep(2)}
        />
      )}
      {step === 4 && result && (
        <DoneStep
          result={result}
          filename={primaryFilename}
          onProceed={() => onCleaningDone?.(result, primaryFilename)}
        />
      )}
    </div>
  );
}
