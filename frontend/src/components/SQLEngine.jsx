// src/components/SQLEngine.jsx
// ──────────────────────────────
// The Text-to-SQL interface.
// Props:
//   cleanFileIds  — array of {file_id, filename} from the cleaning step
//   apiKey        — Gemini API key (string)

import { useState, useRef, useEffect } from "react";
import { createSQLSession, nlQuery, rawQuery, getHistory } from "../services/sqlApi";
import ChartRenderer from "./ChartRenderer";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Badge({ children, color = "cyan" }) {
  const map = {
    cyan:   "bg-cyan-900/40 text-cyan-400 border-cyan-800",
    green:  "bg-emerald-900/40 text-emerald-400 border-emerald-800",
    yellow: "bg-yellow-900/40 text-yellow-400 border-yellow-800",
    red:    "bg-red-900/40 text-red-400 border-red-800",
    purple: "bg-purple-900/40 text-purple-400 border-purple-800",
    gray:   "bg-gray-800 text-gray-400 border-gray-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-mono ${map[color]}`}>
      {children}
    </span>
  );
}

function Spinner() {
  return (
    <div className="flex items-center gap-2 text-cyan-400 font-mono text-sm animate-pulse">
      <div className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "0ms" }} />
      <div className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "150ms" }} />
      <div className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  );
}

// ── SQL Block ─────────────────────────────────────────────────────────────────

function SQLBlock({ sql }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Very simple syntax colouring via regex replace
  const highlighted = sql
    .replace(/\b(SELECT|FROM|WHERE|JOIN|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|AS|AND|OR|NOT|IN|IS|NULL|INNER|LEFT|RIGHT|FULL|OUTER|CROSS|UNION|ALL|DISTINCT|CASE|WHEN|THEN|ELSE|END|BETWEEN|LIKE|WITH|OVER|PARTITION BY|ROWS|ASC|DESC|USING)\b/gi,
      '<span style="color:#ff7b72">$1</span>')
    .replace(/\b(COUNT|SUM|AVG|MIN|MAX|COALESCE|NULLIF|ROUND|FLOOR|CEIL|ABS|LENGTH|UPPER|LOWER|TRIM|SUBSTR|DATE_TRUNC|STRFTIME|EXTRACT|NOW|CAST|RANK|DENSE_RANK|ROW_NUMBER|LAG|LEAD)\b/gi,
      '<span style="color:#d2a8ff">$1</span>')
    .replace(/'([^']*)'/g, "<span style=\"color:#a5d6ff\">'$1'</span>")
    .replace(/\b(\d+\.?\d*)\b/g, '<span style="color:#79c0ff">$1</span>')
    .replace(/--.*/g, '<span style="color:#8b949e;font-style:italic">$&</span>');

  return (
    <div className="rounded-xl overflow-hidden border border-gray-800 my-3">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-950 border-b border-gray-800">
        <span className="text-xs font-mono text-cyan-500">⚡ generated SQL</span>
        <button
          onClick={copy}
          className="text-xs font-mono text-gray-500 hover:text-cyan-400 border border-gray-700 hover:border-cyan-700 px-2 py-0.5 rounded transition-colors">
          {copied ? "✓ copied" : "copy"}
        </button>
      </div>
      <pre
        className="p-4 text-sm font-mono leading-relaxed overflow-x-auto bg-[#0d1117]"
        dangerouslySetInnerHTML={{ __html: highlighted }}
      />
    </div>
  );
}

// ── Results Table ─────────────────────────────────────────────────────────────

function ResultTable({ columns, rows, truncated, rowCount }) {
  if (!rows.length) {
    return <div className="text-gray-500 text-sm italic py-4">No rows returned.</div>;
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Badge color="green">{rowCount.toLocaleString()} rows</Badge>
        {truncated && <Badge color="yellow">truncated at 500</Badge>}
      </div>
      <div className="overflow-auto max-h-72 rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-950 z-10">
            <tr>
              {columns.map(c => (
                <th key={c.name} className="px-4 py-2.5 text-left text-xs font-mono text-gray-400 border-b border-gray-800 whitespace-nowrap">
                  {c.name}
                  <span className="ml-1 text-gray-600">({c.dtype})</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={`border-t border-gray-800/40 ${i % 2 === 0 ? "bg-gray-900/20" : ""} hover:bg-gray-800/40`}>
                {columns.map(c => (
                  <td key={c.name} className="px-4 py-2 text-gray-300 font-mono text-xs whitespace-nowrap">
                    {row[c.name] === null || row[c.name] === undefined
                      ? <span className="text-gray-600">NULL</span>
                      : String(row[c.name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Chart icons (kept for reference)
const VIZ_ICONS = {
  bar: "📊", line: "📈", pie: "🥧", histogram: "📉",
  scatter: "🔵", heatmap: "🟥", table: "📋"
};

// ── Chat Message ──────────────────────────────────────────────────────────────

function QueryMessage({ item }) {
  const [showSQL, setShowSQL] = useState(false);

  if (item.type === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-purple-900/30 border border-purple-800/50 rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl">
          <p className="text-white text-sm">{item.text}</p>
        </div>
      </div>
    );
  }

  if (item.type === "error") {
    return (
      <div className="flex gap-3">
        <div className="w-8 h-8 rounded-lg bg-red-900/30 border border-red-800 flex items-center justify-center flex-shrink-0 text-sm">⚠</div>
        <div className="bg-red-950/30 border border-red-900/50 rounded-2xl rounded-tl-sm px-4 py-3 max-w-2xl">
          <p className="text-red-400 text-sm">{item.text}</p>
        </div>
      </div>
    );
  }

  // AI result
  const { result } = item;
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg bg-cyan-900/30 border border-cyan-800 flex items-center justify-center flex-shrink-0 text-sm">🤖</div>
      <div className="flex-1 max-w-3xl space-y-2">
        {/* Explanation */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-gray-200 text-sm leading-relaxed">{result.sql_explanation}</p>

          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={() => setShowSQL(s => !s)}
              className="text-xs font-mono text-cyan-500 hover:text-cyan-400 transition-colors">
              {showSQL ? "▼ hide SQL" : "▶ show SQL"}
            </button>
            <Badge color="gray">{result.execution_time_ms}ms</Badge>
          </div>

          {showSQL && <SQLBlock sql={result.sql} />}
        </div>

        {/* Results */}
        {result.rows && result.rows.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl px-4 py-3">
            <ResultTable
              columns={result.columns}
              rows={result.rows}
              truncated={result.truncated}
              rowCount={result.row_count}
            />
            <ChartRenderer viz={result.viz_suggestion} rows={result.rows} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Quick Prompt Chips ─────────────────────────────────────────────────────────

function QuickPrompts({ onSelect }) {
  const prompts = [
    "Show top 5 records by sales",
    "Count rows per category",
    "What are the column averages?",
    "Show records with missing values",
    "Group by region and sum revenue",
  ];
  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {prompts.map(p => (
        <button
          key={p}
          onClick={() => onSelect(p)}
          className="text-xs px-3 py-1.5 rounded-full border border-gray-700 text-gray-400 hover:border-cyan-700 hover:text-cyan-400 transition-colors">
          {p}
        </button>
      ))}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function SQLEngine({ cleanFileIds = [], apiKey = "" }) {
  // cleanFileIds: [{file_id, filename}]
  const [sessionId, setSessionId] = useState(null);
  const [sessionInfo, setSessionInfo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("nl");        // "nl" | "raw"
  const [rawSQL, setRawSQL] = useState("");
  const [initError, setInitError] = useState(null);
  const [initLoading, setInitLoading] = useState(false);
  const [tableNames, setTableNames] = useState({});  // file_id → table_name
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Initialize table names from filenames ──────────────────────
  useEffect(() => {
    const names = {};
    cleanFileIds.forEach(({ file_id, filename }) => {
      // "sales_2024_cleaned.csv" → "sales_2024"
      const name = filename
        .replace(/\.csv$/i, "")
        .replace(/[^a-zA-Z0-9_]/g, "_")
        .toLowerCase()
        .replace(/_+/g, "_")
        .slice(0, 40);
      names[file_id] = name;
    });
    setTableNames(names);
  }, [cleanFileIds]);

  // ── Create session ─────────────────────────────────────────────
  const initSession = async () => {
    setInitLoading(true);
    setInitError(null);
    try {
      const tables = cleanFileIds.map(({ file_id }) => ({
        file_id,
        table_name: tableNames[file_id] || file_id.slice(0, 8),
      }));
      const info = await createSQLSession(tables);
      setSessionId(info.session_id);
      setSessionInfo(info);
      setMessages([{
        type: "ai",
        result: {
          sql: "",
          sql_explanation: `✅ SQL session ready! I have access to ${info.tables.length} table(s): ${info.tables.map(t => `**${t.table_name}** (${t.row_count.toLocaleString()} rows)`).join(", ")}. Ask me anything!`,
          columns: [], rows: [], row_count: 0, truncated: false,
          execution_time_ms: 0, viz_suggestion: null,
        },
      }]);
    } catch (e) {
      setInitError(e?.detail || "Failed to create session.");
    } finally {
      setInitLoading(false);
    }
  };

  // ── Send NL query ──────────────────────────────────────────────
  const sendQuery = async () => {
    const q = input.trim();
    if (!q || !sessionId) return;
    setInput("");
    setLoading(true);
    setMessages(m => [...m, { type: "user", text: q }]);

    try {
      const result = await nlQuery(sessionId, q, apiKey);
      if (result.error) {
        setMessages(m => [...m, { type: "error", text: result.error }]);
      } else {
        setMessages(m => [...m, { type: "ai", result }]);
      }
    } catch (e) {
      setMessages(m => [...m, { type: "error", text: e?.detail || "Request failed." }]);
    } finally {
      setLoading(false);
    }
  };

  // ── Run raw SQL ────────────────────────────────────────────────
  const runRaw = async () => {
    if (!rawSQL.trim() || !sessionId) return;
    setLoading(true);
    setMessages(m => [...m, { type: "user", text: `[SQL] ${rawSQL}` }]);
    try {
      const result = await rawQuery(sessionId, rawSQL);
      if (result.error) {
        setMessages(m => [...m, { type: "error", text: result.error }]);
      } else {
        setMessages(m => [...m, { type: "ai", result }]);
      }
    } catch (e) {
      setMessages(m => [...m, { type: "error", text: e?.detail || "SQL failed." }]);
    } finally {
      setLoading(false);
    }
  };

  // ── Pre-session: configure table names ───────────────────────
  if (!sessionId) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <div className="font-bold text-white text-lg mb-1">🔗 Configure SQL Session</div>
          <div className="text-gray-500 text-sm mb-5">Name your tables — these become your SQL table names.</div>

          <div className="space-y-3">
            {cleanFileIds.map(({ file_id, filename }) => (
              <div key={file_id} className="flex items-center gap-3">
                <div className="flex-1">
                  <div className="text-xs text-gray-500 font-mono mb-1">{filename}</div>
                  <input
                    value={tableNames[file_id] || ""}
                    onChange={e => setTableNames(n => ({ ...n, [file_id]: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 focus:border-cyan-600 rounded-lg px-3 py-2 text-sm font-mono text-cyan-400 outline-none transition-colors"
                    placeholder="table_name"
                  />
                </div>
              </div>
            ))}
          </div>

          {initError && (
            <div className="mt-4 p-3 rounded-xl bg-red-900/20 border border-red-800 text-red-400 text-sm">
              {initError}
            </div>
          )}

          <button
            onClick={initSession}
            disabled={initLoading}
            className="mt-5 w-full py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-bold text-sm transition-colors">
            {initLoading ? "⚡ Creating session..." : "Start SQL Session →"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="font-bold text-white text-lg">⚡ SQL Query Engine</div>
          <div className="text-gray-500 text-xs font-mono mt-0.5">
            {sessionInfo?.tables.map(t => (
              <span key={t.table_name} className="mr-3">
                <span className="text-cyan-500">{t.table_name}</span>
                <span className="text-gray-600"> ({t.row_count.toLocaleString()} rows)</span>
              </span>
            ))}
          </div>
        </div>

        {/* Mode toggle */}
        <div className="flex bg-gray-900 border border-gray-800 rounded-xl p-1">
          <button
            onClick={() => setMode("nl")}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${mode === "nl" ? "bg-cyan-600 text-white" : "text-gray-500 hover:text-white"}`}>
            💬 Ask
          </button>
          <button
            onClick={() => setMode("raw")}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${mode === "raw" ? "bg-cyan-600 text-white" : "text-gray-500 hover:text-white"}`}>
            ⌨️ SQL
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 min-h-0 pr-1 mb-4">
        {messages.map((msg, i) => <QueryMessage key={i} item={msg} />)}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-900/30 border border-cyan-800 flex items-center justify-center flex-shrink-0 text-sm">🤖</div>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <Spinner />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      {mode === "nl" ? (
        <div className="space-y-2">
          <QuickPrompts onSelect={q => { setInput(q); }} />
          <div className="flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendQuery()}
              placeholder="Ask anything… e.g. 'Top 3 employees by total sales'"
              className="flex-1 bg-gray-900 border border-gray-800 focus:border-cyan-600 rounded-xl px-4 py-3 text-sm text-white outline-none transition-colors placeholder:text-gray-600"
              disabled={loading}
            />
            <button
              onClick={sendQuery}
              disabled={loading || !input.trim()}
              className="px-6 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white font-bold text-sm transition-colors">
              →
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={rawSQL}
            onChange={e => setRawSQL(e.target.value)}
            placeholder="SELECT * FROM sales LIMIT 10;"
            rows={4}
            className="w-full bg-gray-900 border border-gray-800 focus:border-cyan-600 rounded-xl px-4 py-3 text-sm font-mono text-cyan-300 outline-none transition-colors placeholder:text-gray-600 resize-none"
          />
          <button
            onClick={runRaw}
            disabled={loading || !rawSQL.trim()}
            className="w-full py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white font-bold text-sm transition-colors">
            {loading ? "Running..." : "▶ Execute SQL"}
          </button>
        </div>
      )}
    </div>
  );
}
