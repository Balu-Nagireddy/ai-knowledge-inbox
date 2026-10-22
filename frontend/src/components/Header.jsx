import React from 'react';
import { Inbox, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Header({ health }) {
  const isOnline = health?.status === "healthy";
  const isGeminiActive = health?.gemini_api_configured;

  // Format model name cleanly: e.g. "gemini-3.8-flash" -> "Gemini 3.8 Flash"
  const formatModelName = (modelKey) => {
    if (!modelKey) return "Gemini Live";
    return modelKey
      .split(/[-_]/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  };

  const activeModelDisplay = formatModelName(health?.models?.llm);

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-icon-wrapper">
          <Inbox size={24} />
        </div>
        <div>
          <h1 className="brand-title">AI Knowledge Inbox</h1>
          <p className="brand-subtitle">Production Minimal RAG Engine & Knowledge Store</p>
        </div>
      </div>

      <div className="system-status">
        <div className={`status-badge ${isOnline ? 'online' : 'offline'}`}>
          <span className="status-dot"></span>
          <span>{isOnline ? 'Backend Online' : 'Backend Offline'}</span>
        </div>

        {isOnline && (
          <div
            className="status-badge"
            style={{
              background: isGeminiActive ? 'rgba(99, 102, 241, 0.15)' : 'rgba(245, 158, 11, 0.15)',
              color: isGeminiActive ? '#a5b4fc' : '#fbbf24',
              borderColor: isGeminiActive ? 'rgba(99, 102, 241, 0.35)' : 'rgba(245, 158, 11, 0.35)',
            }}
          >
            <Sparkles size={14} />
            <span>{isGeminiActive ? `${activeModelDisplay} Live` : 'Demo Mode (Mock Emb)'}</span>
          </div>
        )}
      </div>
    </header>
  );
}
