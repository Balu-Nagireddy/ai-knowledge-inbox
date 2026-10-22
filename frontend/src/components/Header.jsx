import React from 'react';
import { Inbox, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Header({ health }) {
  const isOnline = health?.status === "healthy";
  const isGeminiActive = health?.gemini_api_configured;

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-icon-wrapper">
          <Inbox size={24} />
        </div>
        <div>
          <h1 className="brand-title">AI Knowledge Inbox</h1>
          <p className="brand-subtitle">Minimal Production RAG Engine & Knowledge Store</p>
        </div>
      </div>

      <div className="system-status">
        <div className={`status-badge ${isOnline ? 'online' : 'offline'}`}>
          <span className="status-dot"></span>
          <span>{isOnline ? 'Backend Online' : 'Backend Offline'}</span>
        </div>

        {isOnline && (
          <div className="status-badge" style={{
            background: isGeminiActive ? 'rgba(99, 102, 241, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            color: isGeminiActive ? '#a5b4fc' : '#fbbf24',
            borderColor: isGeminiActive ? 'rgba(99, 102, 241, 0.3)' : 'rgba(245, 158, 11, 0.3)'
          }}>
            <Sparkles size={14} />
            <span>{isGeminiActive ? 'Gemini 2.0 Live' : 'Demo Mode (Mock Emb)'}</span>
          </div>
        )}
      </div>
    </header>
  );
}
