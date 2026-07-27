// src/components/RAGChat.jsx
// ───────────────────────────
// Freeform analytical chat grounded in the actual dataset.
// Handles index building, multi-turn conversation, source citations,
// insight type badges, suggested SQL, and follow-up chips.
//
// Props:
//   cleanFileIds  — [{file_id, filename}]  from cleaning step
//   apiKey        — Gemini API key string (optional)

import { useState, useRef, useEffect } from "react";
import { buildIndex, ragChat } from "../services/ragApi";

// ── Inline icons (SF Symbols-style: thin stroke, monochrome, no fill) ──────────

function IconCheck(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 10.5 8 14.5 16 6" />
    </svg>
  );
}

function IconWarning(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10 2.5 18 16.5H2L10 2.5Z" />
      <path d="M10 8v3.5" />
      <circle cx="10" cy="14" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconBrain(props) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M7.5 4.5a2.3 2.3 0 0 0-2.3 2.3v.4A2.3 2.3 0 0 0 4 9.3v1.4a2.3 2.3 0 0 0 1.4 2.1v.4A2.3 2.3 0 0 0 7.7 15.5" />
      <path d="M12.5 4.5a2.3 2.3 0 0 1 2.3 2.3v.4A2.3 2.3 0 0 1 16 9.3v1.4a2.3 2.3 0 0 1-1.4 2.1v.4a2.3 2.3 0 0 1-2.3 2.3" />
      <path d="M10 4.8v10.9" />
    </svg>
  );
}

function IconBars(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 16.5V11M10 16.5V4M16 16.5v-8" />
    </svg>
  );
}

function IconSearch(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="8.5" cy="8.5" r="5" />
      <path d="M15.5 15.5 12.3 12.3" />
    </svg>
  );
}

function IconTrend(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 14.5 8 9l3.5 3 5.5-6.5" />
      <path d="M13.5 5h3.5v3.5" />
    </svg>
  );
}

function IconBulb(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10 2.5a4.5 4.5 0 0 0-2.5 8.25c.4.3.6.75.6 1.25v.5h4v-.5c0-.5.2-.95.6-1.25A4.5 4.5 0 0 0 10 2.5Z" />
      <path d="M8.3 15.5h3.4M8.8 17.3h2.4" />
    </svg>
  );
}

function IconQuestion(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M7.8 8a2.2 2.2 0 1 1 3.4 1.8c-.7.5-1.2.9-1.2 1.7" />
      <circle cx="10" cy="13.9" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

// ── Constants ─────────────────────────────────────────────────────────────────

const INSIGHT_CONFIG = {
  descriptive:   { label: "What happened",     color: "blue",    Icon: IconBars },
  diagnostic:    { label: "Why it happened",   color: "amber",   Icon: IconSearch },
  predictive:    { label: "What might happen", color: "neutral", Icon: IconTrend },
  prescriptive:  { label: "What to do",        color: "emerald", Icon: IconBulb },
  clarification: { label: "Clarification",     color: "neutral", Icon: IconQuestion },
};

const FALLBACK_QUESTIONS = [
  "Show me a summary of this dataset",
  "What are the most common values?",
  "Are there any anomalies or outliers?",
  "What patterns exist in this data?",
  "How many unique values are in each column?",
  "What does a typical row look like?",
];

// Generate starter questions heuristically from column names (no external LLM call)
function generateStarterQuestions(tableSchemas) {
  const cols = Object.values(tableSchemas).flat();
  if (!cols || cols.length === 0) return FALLBACK_QUESTIONS;

  const suggestions = new Set();
  // common heuristics
  if (cols.some(c => /price|amount|revenue|total/i.test(c))) suggestions.add("Show top 10 products by revenue");
  if (cols.some(c => /date|year|month|timestamp/i.test(c))) suggestions.add("Monthly trend of key metric");
  if (cols.some(c => /customer|user|client/i.test(c))) suggestions.add("Top customers by spending");
  if (cols.some(c => /region|country|state|city/i.test(c))) suggestions.add("Sales by region");
  if (cols.some(c => /category|type|segment/i.test(c))) suggestions.add("Breakdown by category");
  if (cols.length > 5) suggestions.add("Show a summary of this dataset");

  const out = Array.from(suggestions).slice(0, 6);
  while (out.length < 6) out.push(FALLBACK_QUESTIONS[out.length]);
  return out;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function Badge({ children, color = "neutral" }) {
  const map = {
    neutral: "bg-gray-800/60 text-gray-300 border-gray-700",
    emerald: "bg-emerald-950/30 text-emerald-400 border-emerald-900",
    amber:   "bg-amber-950/30 text-amber-400 border-amber-900",
    red:     "bg-red-950/40 text-red-400 border-red-900",
    blue:    "bg-blue-950/30 text-blue-400 border-blue-900",
  };
  return (
    <span className={`text-[11px] px-1.5 py-0.5 rounded border font-mono ${map[color]}`}>
      {children}
    </span>
  );
}

function TypingDots() {
  return (
    <div className="flex gap-1.5 items-center h-5">
      {[0, 1, 2].map(i => (
        <div
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-pulse"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}

// ── Source Citations ───────────────────────────────────────────────────────────

function SourceCitations({ chunks }) {
  const [expanded, setExpanded] = useState(false);
  if (!chunks || chunks.length === 0) return null;

  return (
    <div className="mt-3 border-t border-gray-800/70 pt-3">
      <button
        onClick={() => setExpanded(e => !e)}
        className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm">
        <span>{expanded ? "▼" : "▶"}</span>
        {chunks.length} source{chunks.length > 1 ? "s" : ""} retrieved
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {chunks.map((chunk, i) => (
            <div key={i} className="bg-gray-950/60 rounded-md p-3 border border-gray-800/60">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-mono text-gray-400">{chunk.source}</span>
                <span className={`text-[11px] px-1.5 py-0.5 rounded font-mono
                  ${chunk.relevance_score > 0.6 ? "text-emerald-400 bg-emerald-950/40" :
                    chunk.relevance_score > 0.3 ? "text-amber-400 bg-amber-950/40" :
                    "text-gray-500 bg-gray-900"}`}>
                  {Math.round(chunk.relevance_score * 100)}% match
                </span>
              </div>
              <p className="text-xs text-gray-500 font-mono leading-relaxed whitespace-pre-wrap">
                {chunk.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Suggested SQL ──────────────────────────────────────────────────────────────

function SuggestedSQL({ sql }) {
  const [copied, setCopied] = useState(false);
  if (!sql) return null;

  return (
    <div className="mt-3 bg-gray-950 rounded-lg border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-800">
        <span className="text-[11px] font-mono uppercase tracking-wide text-gray-500">Suggested SQL</span>
        <button
          onClick={() => { navigator.clipboard.writeText(sql); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm">
          {copied ? (<><IconCheck className="text-emerald-400" /> copied</>) : "copy"}
        </button>
      </div>
      <pre className="px-3 py-2 text-xs font-mono text-gray-400 overflow-x-auto leading-relaxed">
        {sql}
      </pre>
    </div>
  );
}

// ── Chat Message ──────────────────────────────────────────────────────────────

function Message({ msg, onFollowUp }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl bg-gray-800 border border-gray-700 rounded-lg px-3.5 py-2.5">
          <p className="text-gray-100 text-sm leading-relaxed">{msg.content}</p>
        </div>
      </div>
    );
  }

  if (msg.role === "loading") {
    return (
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-md bg-gray-900 border border-gray-800 flex items-center justify-center flex-shrink-0">
          <IconBrain className="text-blue-400" />
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg px-3.5 py-2.5">
          <TypingDots />
        </div>
      </div>
    );
  }

  if (msg.role === "error") {
    return (
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-md bg-red-950/40 border border-red-900 flex items-center justify-center flex-shrink-0">
          <IconWarning className="text-red-400" />
        </div>
        <div className="bg-red-950/20 border border-red-900/50 rounded-lg px-3.5 py-2.5 max-w-2xl">
          <p className="text-red-400 text-sm">{msg.content}</p>
        </div>
      </div>
    );
  }

  // AI answer
  const { response } = msg;
  const insight = INSIGHT_CONFIG[response.insight_type] || INSIGHT_CONFIG.descriptive;

  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-md bg-gray-900 border border-gray-800 flex items-center justify-center flex-shrink-0">
        <IconBrain className="text-blue-400" />
      </div>
      <div className="flex-1 max-w-3xl space-y-2">
        {/* Answer bubble */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg px-3.5 py-3.5">
          {/* Insight type badge */}
          <div className="flex items-center gap-1.5 mb-3">
            <Badge color={insight.color}>
              <span className="inline-flex items-center gap-1">
                <insight.Icon />
                {insight.label}
              </span>
            </Badge>
          </div>

          {/* Answer text - render line breaks and bullets */}
          <div className="text-gray-200 text-sm leading-relaxed space-y-1">
            {response.answer.split("\n").filter(l => l.trim()).map((line, i) => {
              const isBullet = line.trim().startsWith("*") || line.trim().startsWith("+") || line.trim().startsWith("-");
              const text = line.replace(/^\s*[\*\+\-]\s*/, "").replace(/\*\*(.*?)\*\*/g, "$1");
              return isBullet
                ? <div key={i} className="flex gap-2 ml-2"><span className="text-gray-500 mt-0.5">•</span><span>{text}</span></div>
                : <p key={i}>{text}</p>;
            })}
          </div>

          {/* Suggested SQL */}
          <SuggestedSQL sql={response.suggested_sql} />

          {/* Source citations */}
          <SourceCitations chunks={response.source_chunks} />
        </div>

        {/* Follow-up chips */}
        {response.follow_up_questions && response.follow_up_questions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pl-1">
            {response.follow_up_questions.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp(q)}
                className="text-xs px-2.5 py-1 rounded-md border border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200 transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Index Build Screen ─────────────────────────────────────────────────────────

function IndexBuilder({ cleanFileIds, apiKey, onReady }) {
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(0);

  const start = async () => {
    setBuilding(true);
    setError(null);

    // Fake progress animation while building
    const interval = setInterval(() => {
      setProgress(p => Math.min(p + Math.random() * 15, 90));
    }, 300);

    try {
      const fileIds = cleanFileIds.map(f => f.file_id);
      const tableNames = Object.fromEntries(
        cleanFileIds.map(({ file_id, filename }) => [
          file_id,
          filename.replace(/\.csv$/i, "").replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase(),
        ])
      );
      const result = await buildIndex(fileIds, tableNames, apiKey);
      clearInterval(interval);
      setProgress(100);
      setTimeout(() => onReady(result), 500);
    } catch (e) {
      clearInterval(interval);
      setError(e?.detail || "Failed to build index.");
      setBuilding(false);
      setProgress(0);
    }
  };

  return (
    <div className="max-w-lg mx-auto text-center space-y-6 py-8">
      <div className="flex justify-center">
        <span className="w-11 h-11 rounded-lg bg-gray-900 border border-gray-800 flex items-center justify-center">
          <IconBrain className="text-blue-400" width="22" height="22" />
        </span>
      </div>
      <div>
        <h3 className="text-lg font-semibold text-gray-50">Build RAG Index</h3>
        <p className="text-gray-500 text-sm mt-2 leading-relaxed">
          Your data will be chunked, embedded, and indexed so you can ask
          freeform questions beyond what SQL can answer.
        </p>
      </div>

      {/* Files to be indexed */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-left space-y-2">
        {cleanFileIds.map(({ file_id, filename }) => (
          <div key={file_id} className="flex items-center gap-2.5">
            <IconCheck className="text-emerald-400 flex-shrink-0" />
            <span className="text-sm font-mono text-gray-300">{filename}</span>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      {building && (
        <div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-2 font-mono">
            {progress < 30 ? "Chunking data…" :
             progress < 60 ? "Generating embeddings…" :
             progress < 90 ? "Building vector index…" :
             "Finalising…"}
          </p>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-red-950/30 border border-red-900 text-red-400 text-sm">
          {error}
        </div>
      )}

      {!building && (
        <button
          onClick={start}
          className="w-full h-11 rounded-md bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          Build Index & Start Chatting
        </button>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function RAGChat({ cleanFileIds = [], apiKey = "" }) {
  const [ragSessionId, setRagSessionId] = useState(null);
  const [indexInfo, setIndexInfo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [starterQuestions, setStarterQuestions] = useState(FALLBACK_QUESTIONS);
  // Maintain conversation history in simple role/content format
  const [history, setHistory] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleIndexReady = async (result) => {
    setRagSessionId(result.rag_session_id);
    setIndexInfo(result);

    // Generate dataset-specific questions from actual column names
    const questions = await generateStarterQuestions(
      result.table_schemas || {},
      apiKey
    );
    setStarterQuestions(questions);

    setMessages([{
      role: "ai",
      response: {
        answer: `Index ready! I've analysed **${result.chunks_indexed} chunks** across ${result.tables_indexed.length} table(s): **${result.tables_indexed.join(", ")}**.\n\nAsk me anything — trends, anomalies, root causes, recommendations. I'll ground every answer in your actual data.`,
        insight_type: "descriptive",
        source_chunks: [],
        suggested_sql: null,
        follow_up_questions: questions.slice(0, 3),
      },
    }]);
  };

  const sendMessage = async (question) => {
    const q = (question || input).trim();
    if (!q || loading || !ragSessionId) return;
    setInput("");
    setLoading(true);

    setMessages(m => [...m, { role: "user", content: q }, { role: "loading" }]);

    try {
      const response = await ragChat(ragSessionId, q, history, apiKey);

      // If answer looks like raw JSON, parse it client-side
      let finalResponse = response;
      if (response.answer && response.answer.trim().startsWith("{")) {
        try {
          const parsed = JSON.parse(response.answer);
          if (parsed.answer) finalResponse = { ...response, ...parsed };
        } catch {}
      }

      const newHistory = [
        ...history,
        { role: "user", content: q },
        { role: "assistant", content: finalResponse.answer },
      ].slice(-12);
      setHistory(newHistory);

      setMessages(m => [
        ...m.filter(msg => msg.role !== "loading"),
        { role: "ai", response: finalResponse },
      ]);
    } catch (e) {
      setMessages(m => [
        ...m.filter(msg => msg.role !== "loading"),
        { role: "error", content: e?.detail || "Request failed." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // ── Pre-index ────────────────────────────────────────────────
  if (!ragSessionId) {
    return (
      <IndexBuilder
        cleanFileIds={cleanFileIds}
        apiKey={apiKey}
        onReady={handleIndexReady}
      />
    );
  }

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div>
          <div className="flex items-center gap-1.5 text-base font-semibold text-gray-50">
            <IconBrain className="text-gray-500" />
            RAG Data Chat
          </div>
          <div className="text-xs font-mono text-gray-500 mt-0.5">
            <span className="text-gray-300 tabular-nums">{indexInfo?.chunks_indexed}</span> chunks indexed ·{" "}
            <span className="text-gray-300">{indexInfo?.tables_indexed?.join(", ")}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
          <span className="text-xs text-emerald-500 font-mono">RAG active</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-5 min-h-0 pr-1 mb-4">
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} onFollowUp={sendMessage} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Starter prompts (only if just started) */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {starterQuestions.map(q => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-xs px-2.5 py-1 rounded-md border border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200 transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex gap-2 flex-shrink-0">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
          placeholder='Ask anything… "Why is sales declining in Q3?" · "What drives revenue?"'
          className="flex-1 h-11 bg-gray-900 border border-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus:border-gray-700 rounded-lg px-3.5 text-sm text-gray-100 transition-colors duration-150 ease-out placeholder:text-gray-600"
          disabled={loading}
        />
        <button
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
          className="px-5 h-11 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-medium text-sm transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          →
        </button>
      </div>
    </div>
  );
}
