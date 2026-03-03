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
    <div className="flex items-center justify-center gap-0 mb-8">
      {STEPS.map((label, i) => (
        <div key={i} className="flex items-center">
          <div className={`flex flex-col items-center`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2
              ${i < current ? "bg-emerald-500 border-emerald-500 text-white"
                : i === current ? "bg-cyan-500 border-cyan-500 text-white"
                : "bg-gray-800 border-gray-600 text-gray-500"}`}>
              {i < current ? "✓" : i + 1}
            </div>
            <span className={`text-xs mt-1 font-medium ${i === current ? "text-cyan-400" : "text-gray-500"}`}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`w-16 h-0.5 mx-1 mb-4 ${i < current ? "bg-emerald-500" : "bg-gray-700"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

function Badge({ children, color = "cyan" }) {
  const colors = {
    cyan: "bg-cyan-900/40 text-cyan-400 border-cyan-800",
    red: "bg-red-900/40 text-red-400 border-red-800",
    yellow: "bg-yellow-900/40 text-yellow-400 border-yellow-800",
    green: "bg-emerald-900/40 text-emerald-400 border-emerald-800",
    purple: "bg-purple-900/40 text-purple-400 border-purple-800",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-mono ${colors[color]}`}>
      {children}
    </span>
  );
}

function StrategyButton({ option, selected, onClick }) {
  return (
    <button
      onClick={() => onClick(option.value)}
      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all
        ${selected
          ? option.danger
            ? "bg-red-900/50 border-red-500 text-red-300"
            : "bg-cyan-900/50 border-cyan-500 text-cyan-300"
          : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500"}`}>
      {option.icon} {option.label}
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
        className={`border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition-all
          ${dragging ? "border-cyan-500 bg-cyan-950/20" : "border-gray-700 hover:border-cyan-700 hover:bg-gray-900/50"}`}
        onClick={() => document.getElementById("file-input").click()}>
        <div className="text-5xl mb-4">📁</div>
        <div className="text-lg font-bold text-white mb-2">Drop CSV files here</div>
        <div className="text-sm text-gray-500 mb-4">or click to browse · supports multiple files</div>
        <Badge color="purple">CSV only</Badge>
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
        <div className="mt-6 text-center text-cyan-400 animate-pulse font-mono text-sm">
          ⚡ Analysing schema...
        </div>
      )}
      {error && (
        <div className="mt-4 p-3 rounded-xl bg-red-900/30 border border-red-800 text-red-400 text-sm">
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
    <div className="space-y-6">
      {schemas.map((schema) => (
        <div key={schema.file_id} className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
            <div>
              <span className="font-bold text-white">{schema.filename}</span>
              <span className="text-gray-500 text-sm ml-3 font-mono">
                {schema.row_count.toLocaleString()} rows · {schema.col_count} cols
              </span>
            </div>
            <div className="flex gap-2">
              {schema.duplicate_row_count > 0 && (
                <Badge color="yellow">{schema.duplicate_row_count} duplicates</Badge>
              )}
              {schema.columns.filter(c => c.null_count > 0).length > 0 && (
                <Badge color="red">
                  {schema.columns.filter(c => c.null_count > 0).length} cols with nulls
                </Badge>
              )}
            </div>
          </div>

          {/* Column table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-950">
                <tr className="text-gray-500 text-xs font-mono">
                  <th className="px-4 py-2 text-left">Column</th>
                  <th className="px-4 py-2 text-left">Type</th>
                  <th className="px-4 py-2 text-left">Nulls</th>
                  <th className="px-4 py-2 text-left">Unique</th>
                  <th className="px-4 py-2 text-left">Flags</th>
                  <th className="px-4 py-2 text-left">Sample</th>
                </tr>
              </thead>
              <tbody>
                {schema.columns.map((col) => (
                  <tr key={col.name} className="border-t border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-2.5 font-mono text-cyan-400 font-medium">{col.name}</td>
                    <td className="px-4 py-2.5">
                      <Badge color={col.is_numeric ? "cyan" : col.is_datetime ? "yellow" : col.is_categorical ? "purple" : "cyan"}>
                        {col.dtype}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      {col.null_count > 0
                        ? <span className="text-red-400 font-mono">{col.null_count} ({col.null_pct}%)</span>
                        : <span className="text-emerald-500 text-xs">✓ none</span>}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-gray-400">{col.unique_count.toLocaleString()}</td>
                    <td className="px-4 py-2.5 flex gap-1 flex-wrap">
                      {col.suggested_pk && <Badge color="green">PK?</Badge>}
                      {col.is_datetime && <Badge color="yellow">datetime</Badge>}
                      {col.is_categorical && <Badge color="purple">category</Badge>}
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
        <div className="bg-purple-950/20 border border-purple-800/50 rounded-2xl p-5">
          <div className="font-bold text-purple-300 mb-3">🔗 Join Keys Detected</div>
          {join_suggestions.map((j, i) => (
            <div key={i} className="flex items-center gap-3 text-sm mb-2">
              <code className="text-cyan-400 font-mono">{j.left_file}.{j.left_col}</code>
              <span className="text-gray-500">↔</span>
              <code className="text-purple-400 font-mono">{j.right_file}.{j.right_col}</code>
              <Badge color={j.confidence > 0.85 ? "green" : "yellow"}>
                {Math.round(j.confidence * 100)}% confidence
              </Badge>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="px-5 py-2 rounded-xl bg-gray-800 text-gray-400 hover:bg-gray-700 text-sm font-semibold">
          ← Back
        </button>
        <button onClick={() => onNext()} className="px-6 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-bold">
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
    <div className="space-y-6">
      {/* NULL HANDLING */}
      {nullCols.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
          <div className="font-bold text-white mb-1">🔴 Null Value Handling</div>
          <div className="text-gray-500 text-xs mb-4 font-mono">{nullCols.length} columns need attention</div>
          <div className="space-y-4">
            {nullCols.map(col => (
              <div key={col.name}>
                <div className="flex items-center gap-2 mb-2">
                  <code className="text-cyan-400 font-mono text-sm">{col.name}</code>
                  <Badge color="red">{col.null_count} nulls · {col.null_pct}%</Badge>
                  <Badge color={col.is_numeric ? "cyan" : "purple"}>{col.dtype}</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
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
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
          <div className="font-bold text-white mb-1">🟡 Outlier Handling</div>
          <div className="text-gray-500 text-xs mb-4 font-mono">Numeric columns · IQR-based detection</div>
          <div className="space-y-4">
            {schema.columns.filter(c => c.is_numeric).map(col => (
              <div key={col.name}>
                <div className="flex items-center gap-2 mb-2">
                  <code className="text-cyan-400 font-mono text-sm">{col.name}</code>
                  <Badge color="cyan">numeric</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
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
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
        <div className="font-bold text-white mb-4">⚙️ Standardization</div>
        <div className="grid grid-cols-2 gap-3">
          {[
            ["lowercase_columns", "Lowercase column names"],
            ["replace_spaces_with_underscore", "Replace spaces with _"],
            ["trim_whitespace", "Trim whitespace from strings"],
            ["drop_constant_columns", "Drop constant columns"],
            ["drop_duplicates", `Drop duplicate rows (${schema.duplicate_row_count} found)`],
          ].map(([key, label]) => (
            <label key={key} className="flex items-center gap-3 cursor-pointer p-3 rounded-xl hover:bg-gray-800 transition-colors">
              <input
                type="checkbox"
                checked={standardization[key]}
                onChange={(e) => setStandardization(s => ({ ...s, [key]: e.target.checked }))}
                className="w-4 h-4 accent-cyan-500"
              />
              <span className="text-sm text-gray-300">{label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="px-5 py-2 rounded-xl bg-gray-800 text-gray-400 hover:bg-gray-700 text-sm font-semibold">
          ← Back
        </button>
        <button
          onClick={handleNext}
          disabled={loading}
          className="px-6 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-bold">
          {loading ? "⚡ Calculating..." : "Preview Changes →"}
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
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
          <div className="text-3xl font-black text-white">{preview.rows_before.toLocaleString()}</div>
          <div className="text-gray-500 text-xs mt-1">Rows Before</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
          <div className={`text-3xl font-black ${dropPct > 10 ? "text-yellow-400" : "text-emerald-400"}`}>
            {preview.rows_after_estimate.toLocaleString()}
          </div>
          <div className="text-gray-500 text-xs mt-1">Rows After (est.)</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
          <div className={`text-3xl font-black ${dropPct > 10 ? "text-yellow-400" : "text-white"}`}>
            {dropPct}%
          </div>
          <div className="text-gray-500 text-xs mt-1">Rows Dropped</div>
        </div>
      </div>

      {/* Warnings */}
      {preview.warnings.map((w, i) => (
        <div key={i} className="p-3 rounded-xl bg-yellow-900/20 border border-yellow-800/50 text-yellow-400 text-sm">
          {w}
        </div>
      ))}

      {/* Steps list */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800 font-bold text-white text-sm">
          📋 Cleaning Steps ({preview.steps.length})
        </div>
        <div className="divide-y divide-gray-800/50">
          {preview.steps.map((step, i) => (
            <div key={i} className="px-5 py-3 flex items-center gap-3 text-sm">
              <div className="w-6 h-6 rounded-full bg-gray-800 flex items-center justify-center text-xs text-gray-400 font-mono flex-shrink-0">
                {i + 1}
              </div>
              {step.column && <code className="text-cyan-400 font-mono">{step.column}</code>}
              <span className="text-gray-300">{step.action}</span>
              {step.rows_affected > 0 && (
                <Badge color={step.rows_affected > 0 ? "yellow" : "green"}>
                  {step.rows_affected} rows
                </Badge>
              )}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-900/30 border border-red-800 text-red-400 text-sm">{error}</div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="px-5 py-2 rounded-xl bg-gray-800 text-gray-400 hover:bg-gray-700 text-sm font-semibold">
          ← Adjust Config
        </button>
        <button
          onClick={handleApply}
          disabled={loading}
          className="px-6 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-bold">
          {loading ? "🧹 Cleaning..." : "✅ Apply Cleaning"}
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
      <div className="text-6xl">🎉</div>
      <div className="text-2xl font-black text-white">Data Cleaned Successfully!</div>

      <div className="grid grid-cols-2 gap-4 max-w-md mx-auto">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-black text-white">{result.rows_after.toLocaleString()}</div>
          <div className="text-gray-500 text-xs mt-1">Clean Rows</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-black text-emerald-400">+{improvement.toFixed(1)}</div>
          <div className="text-gray-500 text-xs mt-1">Quality Score</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-black text-cyan-400">{result.quality_score_after}</div>
          <div className="text-gray-500 text-xs mt-1">Score After</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-2xl font-black text-white">{result.steps_applied.length}</div>
          <div className="text-gray-500 text-xs mt-1">Steps Applied</div>
        </div>
      </div>

      {result.warnings.map((w, i) => (
        <div key={i} className="p-3 rounded-xl bg-yellow-900/20 border border-yellow-800/50 text-yellow-400 text-sm max-w-md mx-auto text-left">
          {w}
        </div>
      ))}

      <div className="flex justify-center gap-3">
        {["csv", "json", "xlsx"].map(fmt => (
          <button
            key={fmt}
            onClick={() => exportDataset(result.clean_file_id, fmt)}
            className="px-4 py-2 rounded-xl bg-gray-800 border border-gray-700 hover:border-cyan-600 text-gray-300 hover:text-cyan-400 text-sm font-bold transition-all">
            ⬇️ .{fmt.toUpperCase()}
          </button>
        ))}
      </div>

      <button
        onClick={onProceed}
        className="px-6 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm transition-colors">
        → Proceed to SQL Query Engine
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
