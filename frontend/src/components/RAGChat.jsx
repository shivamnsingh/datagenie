// src/components/RAGChat.jsx
// ───────────────────────────
// Freeform analytical chat grounded in the actual dataset.
// Handles index building, multi-turn conversation, source citations,
// insight type badges, suggested SQL, and follow-up chips.
//
// Props:
//   cleanFileIds  — [{file_id, filename}]  from cleaning step
//   apiKey        — Anthropic API key string

import { useState, useRef, useEffect } from "react";
import { buildIndex } from "../services/ragApi";
import { ragChat } from "../services/ragApi";

// ── Constants ─────────────────────────────────────────────────────────────────

const INSIGHT_CONFIG = {
  descriptive:   { label: "What happened",    color: "cyan",   icon: "📊" },
  diagnostic:    { label: "Why it happened",  color: "yellow", icon: "🔍" },
  predictive:    { label: "What might happen",color: "purple", icon: "🔮" },
  prescriptive:  { label: "What to do",       color: "green",  icon: "💡" },
  clarification: { label: "Clarification",    color: "gray",   icon: "❓" },
};

const STARTER_QUESTIONS = [
  "What are the key trends in this dataset?",
  "Which factors most influence sales performance?",
  "Are there any anomalies or outliers I should know about?",
  "What does the regional performance look like?",
  "Which time periods show the strongest growth?",
  "What recommendations would you make based on this data?",
];

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

function TypingDots() {
  return (
    <div className="flex gap-1 items-center h-5">
      {[0, 1, 2].map(i => (
        <div
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-bounce"
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
    <div className="mt-3 border-t border-gray-800/60 pt-3">
      <button
        onClick={() => setExpanded(e => !e)}
        className="text-xs text-gray-500 hover:text-gray-400 flex items-center gap-1 transition-colors">
        <span>{expanded ? "▼" : "▶"}</span>
        {chunks.length} source{chunks.length > 1 ? "s" : ""} retrieved
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {chunks.map((chunk, i) => (
            <div key={i} className="bg-gray-950/60 rounded-lg p-3 border border-gray-800/50">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-mono text-cyan-600">{chunk.source}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded font-mono
                  ${chunk.relevance_score > 0.6 ? "text-emerald-400 bg-emerald-950/40" :
                    chunk.relevance_score > 0.3 ? "text-yellow-400 bg-yellow-950/40" :
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
    <div className="mt-3 bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-800">
        <span className="text-xs font-mono text-cyan-600">💡 suggested SQL query</span>
        <button
          onClick={() => { navigator.clipboard.writeText(sql); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          className="text-xs text-gray-600 hover:text-cyan-500 transition-colors">
          {copied ? "✓ copied" : "copy"}
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
        <div className="max-w-2xl bg-purple-900/25 border border-purple-800/40 rounded-2xl rounded-tr-sm px-4 py-3">
          <p className="text-white text-sm leading-relaxed">{msg.content}</p>
        </div>
      </div>
    );
  }

  if (msg.role === "loading") {
    return (
      <div className="flex gap-3">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-900/50 to-purple-900/50 border border-cyan-800/50 flex items-center justify-center flex-shrink-0 text-sm">
          🧠
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
          <TypingDots />
        </div>
      </div>
    );
  }

  if (msg.role === "error") {
    return (
      <div className="flex gap-3">
        <div className="w-8 h-8 rounded-xl bg-red-900/30 border border-red-800 flex items-center justify-center flex-shrink-0 text-sm">⚠</div>
        <div className="bg-red-950/20 border border-red-900/40 rounded-2xl rounded-tl-sm px-4 py-3 max-w-2xl">
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
      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-900/50 to-purple-900/50 border border-cyan-800/50 flex items-center justify-center flex-shrink-0 text-sm">
        🧠
      </div>
      <div className="flex-1 max-w-3xl space-y-2">
        {/* Answer bubble */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-4">
          {/* Insight type badge */}
          <div className="flex items-center gap-2 mb-3">
            <span>{insight.icon}</span>
            <Badge color={insight.color}>{insight.label}</Badge>
          </div>

          {/* Answer text - render line breaks */}
          <div className="text-gray-200 text-sm leading-relaxed space-y-2">
            {response.answer.split("\n").map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>

          {/* Suggested SQL */}
          <SuggestedSQL sql={response.suggested_sql} />

          {/* Source citations */}
          <SourceCitations chunks={response.source_chunks} />
        </div>

        {/* Follow-up chips */}
        {response.follow_up_questions && response.follow_up_questions.length > 0 && (
          <div className="flex flex-wrap gap-2 pl-1">
            {response.follow_up_questions.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp(q)}
                className="text-xs px-3 py-1.5 rounded-full border border-gray-700 text-gray-400 hover:border-cyan-700 hover:text-cyan-400 hover:bg-cyan-950/20 transition-all">
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
      <div className="text-5xl">🧠</div>
      <div>
        <h3 className="text-xl font-black text-white">Build RAG Index</h3>
        <p className="text-gray-500 text-sm mt-2 leading-relaxed">
          Your data will be chunked, embedded, and indexed so you can ask
          freeform questions beyond what SQL can answer.
        </p>
      </div>

      {/* Files to be indexed */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 text-left space-y-2">
        {cleanFileIds.map(({ file_id, filename }) => (
          <div key={file_id} className="flex items-center gap-3">
            <span className="text-emerald-500 text-sm">✓</span>
            <span className="text-sm font-mono text-gray-300">{filename}</span>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      {building && (
        <div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-purple-500 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-2 font-mono animate-pulse">
            {progress < 30 ? "Chunking data..." :
             progress < 60 ? "Generating embeddings..." :
             progress < 90 ? "Building vector index..." :
             "Finalising..."}
          </p>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-xl bg-red-900/20 border border-red-800 text-red-400 text-sm">
          {error}
        </div>
      )}

      {!building && (
        <button
          onClick={start}
          className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-600 to-purple-600 hover:opacity-90 text-white font-bold text-sm transition-opacity">
          ⚡ Build Index & Start Chatting
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
  // Maintain conversation history in Claude API format
  const [history, setHistory] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleIndexReady = (result) => {
    setRagSessionId(result.rag_session_id);
    setIndexInfo(result);
    setMessages([{
      role: "ai",
      response: {
        answer: `Index ready! I've analysed **${result.chunks_indexed} chunks** across ${result.tables_indexed.length} table(s): **${result.tables_indexed.join(", ")}**.\n\nAsk me anything — trends, anomalies, root causes, recommendations. I'll ground every answer in your actual data.`,
        insight_type: "descriptive",
        source_chunks: [],
        suggested_sql: null,
        follow_up_questions: STARTER_QUESTIONS.slice(0, 3),
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

      // Update conversation history for Claude
      const newHistory = [
        ...history,
        { role: "user", content: q },
        { role: "assistant", content: response.answer },
      ].slice(-12); // keep last 6 turns
      setHistory(newHistory);

      setMessages(m => [
        ...m.filter(msg => msg.role !== "loading"),
        { role: "ai", response },
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
          <div className="text-lg font-black text-white">🧠 RAG Data Chat</div>
          <div className="text-xs font-mono text-gray-500 mt-0.5">
            <span className="text-cyan-600">{indexInfo?.chunks_indexed}</span> chunks indexed ·{" "}
            <span className="text-purple-500">{indexInfo?.tables_indexed?.join(", ")}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-emerald-500 font-mono">RAG ACTIVE</span>
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
        <div className="flex flex-wrap gap-2 mb-3">
          {STARTER_QUESTIONS.map(q => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-xs px-3 py-1.5 rounded-full border border-gray-700 text-gray-400 hover:border-purple-700 hover:text-purple-400 hover:bg-purple-950/20 transition-all">
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
          className="flex-1 bg-gray-900 border border-gray-800 focus:border-purple-600 rounded-xl px-4 py-3 text-sm text-white outline-none transition-colors placeholder:text-gray-600"
          disabled={loading}
        />
        <button
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-600 to-purple-600 hover:opacity-90 disabled:opacity-40 text-white font-bold text-sm transition-opacity">
          →
        </button>
      </div>
    </div>
  );
}
