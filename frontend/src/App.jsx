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

// ── Inline icons (SF Symbols-style: 20x20, 1.5px stroke, no fill) ──────────────

function IconBroom(props) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M11.5 2.5 8 9M13 4l3 3-6.5 6.5a3 3 0 0 1-2.2.9H4l.4-3.3a3 3 0 0 1 .9-2.2L11.5 2.5 13 4Z" />
      <path d="M4.5 14.5 2.5 17.5M7 14.5 5.5 17.5M9.5 14.5 8.5 17.5" />
    </svg>
  );
}

function IconTerminal(props) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect x="2.5" y="3.5" width="15" height="13" rx="1.5" />
      <path d="M5.5 7.5 8.5 10l-3 2.5M10.5 12.5h4" />
    </svg>
  );
}

function IconMessage(props) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 4.5h14a1 1 0 0 1 1 1V13a1 1 0 0 1-1 1H8.5L5 17v-3H3a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1Z" />
      <path d="M6 8h8M6 11h5" />
    </svg>
  );
}

function IconCheck(props) {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 10.5 8 14.5 16 6" />
    </svg>
  );
}

function IconChevron(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M7.5 4.5 13 10l-5.5 5.5" />
    </svg>
  );
}

function IconEye(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M1.5 10S4.5 4.5 10 4.5 18.5 10 18.5 10 15.5 15.5 10 15.5 1.5 10 1.5 10Z" />
      <circle cx="10" cy="10" r="2.25" />
    </svg>
  );
}

function IconEyeOff(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M1.5 10S4.5 4.5 10 4.5s8.5 5.5 8.5 5.5-3 5.5-8.5 5.5S1.5 10 1.5 10Z" />
      <circle cx="10" cy="10" r="2.25" />
      <path d="M3 17 17 3" />
    </svg>
  );
}

const STAGES = [
  { id: "clean", label: "Clean",   desc: "Upload & clean CSVs", Icon: IconBroom },
  { id: "sql",   label: "SQL",     desc: "Text → SQL queries",  Icon: IconTerminal },
  { id: "rag",   label: "Analyse", desc: "Freeform AI chat",    Icon: IconMessage },
];

export default function App() {
  const [stage, setStage] = useState("clean");
  const [apiKey, setApiKey] = useState(
    import.meta.env?.VITE_GEMINI_KEY || ""
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

  const currentIndex = STAGES.findIndex(s => s.id === stage);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-50 flex flex-col">
      {/* ── Top Nav ── */}
      <nav className="border-b border-gray-800 bg-gray-950 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-5 h-12 flex items-center justify-between gap-6">
          {/* Logo */}
          <div className="flex items-center gap-2.5 shrink-0">
            <span className="text-sm font-semibold tracking-tight text-gray-50">
              DataGenie
            </span>
            <span className="text-[11px] font-mono text-gray-500 hidden md:inline-block border-l border-gray-800 pl-2.5">
              Data Platform
            </span>
          </div>

          {/* Stage nav */}
          <div className="flex items-center gap-0.5">
            {STAGES.map((s, i) => {
              const isReachable = s.id === "clean" || cleanedFiles.length > 0;
              const isActive = stage === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => isReachable && setStage(s.id)}
                  disabled={!isReachable}
                  className={`flex items-center gap-1.5 px-3 h-8 rounded-md text-[13px] font-medium
                    transition-colors duration-150 ease-out
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                    ${isActive
                      ? "bg-gray-900 text-blue-400"
                      : isReachable
                        ? "text-gray-400 hover:text-gray-100 hover:bg-gray-900"
                        : "text-gray-700 cursor-not-allowed"}`}
                >
                  <s.Icon className={isActive ? "text-blue-400" : ""} />
                  <span className="hidden sm:inline-block">{s.label}</span>
                </button>
              );
            })}
          </div>

          {/* API Key input */}
          <div className="flex items-center gap-2 shrink-0">
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${apiKey ? "bg-emerald-500" : "bg-red-500"}`}
              aria-hidden="true"
            />
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="Gemini API key"
                aria-label="Gemini API key"
                className="w-40 h-8 bg-gray-900 border border-gray-700 focus-visible:outline-none
                  focus-visible:ring-2 focus-visible:ring-blue-500 focus:border-gray-600
                  rounded-md pl-2.5 pr-8 text-xs font-mono text-gray-200
                  placeholder:text-gray-600 transition-colors duration-150 ease-out"
              />
              <button
                onClick={() => setShowApiKey(v => !v)}
                aria-label={showApiKey ? "Hide API key" : "Show API key"}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm
                  transition-colors duration-150 ease-out"
              >
                {showApiKey ? <IconEyeOff /> : <IconEye />}
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Stage indicator bar ── */}
      <div className="border-b border-gray-800 bg-gray-950">
        <div className="max-w-6xl mx-auto px-5 h-9 flex items-center gap-2">
          {STAGES.map((s, i) => {
            const isActive = stage === s.id;
            const isComplete = i < currentIndex || (i === 0 && cleanedFiles.length > 0 && currentIndex > 0);
            const state = isActive ? "active" : isComplete ? "complete" : "upcoming";
            return (
              <span key={s.id} className="flex items-center gap-2">
                <span
                  className={`flex items-center gap-1.5 text-xs font-medium ${
                    state === "active" ? "text-blue-400"
                    : state === "complete" ? "text-gray-300"
                    : "text-gray-600"
                  }`}
                >
                  {state === "complete" ? (
                    <IconCheck className="text-gray-500" />
                  ) : (
                    <s.Icon />
                  )}
                  {s.label}
                </span>
                {i < STAGES.length - 1 && (
                  <IconChevron className="text-gray-800" />
                )}
              </span>
            );
          })}
          {cleanedFiles.length > 0 && (
            <span className="ml-auto text-xs font-mono text-gray-500 truncate max-w-xs">
              {cleanedFiles.length} file{cleanedFiles.length > 1 ? "s" : ""} ready · {" "}
              {cleanedFiles.map(f => f.filename).join(", ")}
            </span>
          )}
        </div>
      </div>

      {/* ── Main content ── */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-5 py-6 flex flex-col">
        {stage === "clean" && (
          <CleaningWizard
            onCleaningDone={handleCleaningDone}
            apiKey={apiKey}
          />
        )}

        {stage === "sql" && (
          <div className="flex-1 flex flex-col min-h-0" style={{ height: "calc(100vh - 148px)" }}>
            <SQLEngine
              cleanFileIds={cleanedFiles}
              apiKey={apiKey}
            />
          </div>
        )}

        {stage === "rag" && (
          <div className="flex-1 flex flex-col min-h-0" style={{ height: "calc(100vh - 148px)" }}>
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
