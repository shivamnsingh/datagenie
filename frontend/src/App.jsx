// src/App.jsx
// ─────────────
// Master shell that connects all three stages:
//   1. Cleaning Wizard  →  produces clean_file_id
//   2. SQL Engine       →  uses clean_file_id as a table
//   3. RAG Chat         →  indexes the clean data for freeform Q&A

import { useState } from "react";
import CleaningWizard from "./components/CleaningWizard";
import SQLEngine from "./components/SQLEngine";
import RAGChat from "./components/RAGChat";

const STAGES = [
  { id: "clean", label: "Clean",   icon: "🧹", desc: "Upload & clean CSVs" },
  { id: "sql",   label: "SQL",     icon: "⚡", desc: "Text → SQL queries"  },
  { id: "rag",   label: "Analyse", icon: "🧠", desc: "Freeform AI chat"   },
];

export default function App() {
  const [stage, setStage] = useState("clean");
  const [apiKey, setApiKey] = useState(
    import.meta.env?.VITE_ANTHROPIC_KEY || ""
  );
  const [showApiKey, setShowApiKey] = useState(false);

  // Shared state passed between stages
  const [cleanedFiles, setCleanedFiles] = useState([]);
  // cleanedFiles: [{file_id, filename}]

  const handleCleaningDone = (result, filename) => {
    // Prevent duplicate entries for the same file_id
    setCleanedFiles(prev => {
      const alreadyAdded = prev.some(f => f.file_id === result.clean_file_id);
      if (alreadyAdded) return prev;
      return [...prev, { file_id: result.clean_file_id, filename }];
    });
    // Auto-advance to SQL stage
    setStage("sql");
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">
      {/* ── Top Nav ── */}
      <nav className="border-b border-gray-800 bg-gray-950/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="text-xl font-black bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
              DataGenie AI
            </div>
            <span className="text-xs font-mono text-gray-600 hidden sm:block">
              End-to-End Data Platform
            </span>
          </div>

          {/* Stage nav */}
          <div className="flex items-center gap-1">
            {STAGES.map((s, i) => {
              const isReachable = s.id === "clean" || cleanedFiles.length > 0;
              return (
                <button
                  key={s.id}
                  onClick={() => isReachable && setStage(s.id)}
                  disabled={!isReachable}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold transition-all
                    ${stage === s.id
                      ? "bg-cyan-900/40 text-cyan-400 border border-cyan-800"
                      : isReachable
                        ? "text-gray-400 hover:text-white hover:bg-gray-800"
                        : "text-gray-700 cursor-not-allowed"}`}>
                  <span>{s.icon}</span>
                  <span className="hidden sm:block">{s.label}</span>
                  {i < STAGES.length - 1 && (
                    <span className="text-gray-700 ml-1 hidden sm:block">›</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* API Key input */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${apiKey ? "bg-emerald-500" : "bg-red-500"}`} />
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="gsk_… Groq API key"
                className="w-44 bg-gray-900 border border-gray-700 focus:border-cyan-700 rounded-lg px-3 py-1.5 text-xs font-mono text-gray-300 outline-none transition-colors"
              />
              <button
                onClick={() => setShowApiKey(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 text-xs">
                {showApiKey ? "🙈" : "👁"}
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Stage indicator bar ── */}
      <div className="border-b border-gray-800/50 bg-gray-900/30">
        <div className="max-w-6xl mx-auto px-6 py-2 flex items-center gap-2 text-xs text-gray-500 font-mono">
          {STAGES.map((s, i) => (
            <span key={s.id} className="flex items-center gap-2">
              <span className={stage === s.id ? "text-cyan-400" : cleanedFiles.length > 0 && i > 0 ? "text-emerald-600" : ""}>
                {s.icon} {s.label}
              </span>
              {i < STAGES.length - 1 && <span className="text-gray-700">→</span>}
            </span>
          ))}
          {cleanedFiles.length > 0 && (
            <span className="ml-auto text-gray-600">
              {cleanedFiles.length} file{cleanedFiles.length > 1 ? "s" : ""} ready ·{" "}
              {cleanedFiles.map(f => f.filename).join(", ")}
            </span>
          )}
        </div>
      </div>

      {/* ── Main content ── */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8 flex flex-col">
        {stage === "clean" && (
          <CleaningWizard
            onCleaningDone={handleCleaningDone}
            apiKey={apiKey}
          />
        )}

        {stage === "sql" && (
          <div className="flex-1 flex flex-col min-h-0" style={{ height: "calc(100vh - 160px)" }}>
            <SQLEngine
              cleanFileIds={cleanedFiles}
              apiKey={apiKey}
            />
          </div>
        )}

        {stage === "rag" && (
          <div className="flex-1 flex flex-col min-h-0" style={{ height: "calc(100vh - 160px)" }}>
            <RAGChat
              cleanFileIds={cleanedFiles}
              apiKey={apiKey}
            />
          </div>
        )}
      </main>
    </div>
  );
}
