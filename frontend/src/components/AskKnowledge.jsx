import React, { useState } from 'react';
import { Sparkles, Send, Loader2, BookOpen, Copy, Check, AlertCircle, Quote } from 'lucide-react';
import { queryKnowledge } from '../api';

export default function AskKnowledge({ itemsCount }) {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const sampleQuestions = [
    "What key concepts are covered in my notes?",
    "Summarize the main takeaways from the saved content.",
    "What are the best practices or architectural highlights mentioned?"
  ];

  const handleAsk = async (queryText) => {
    const q = (queryText || question).trim();
    if (!q) return;

    setError(null);
    setLoading(true);
    setResult(null);

    try {
      const data = await queryKnowledge(q, 4);
      setResult(data);
    } catch (err) {
      setError(err.message || 'Failed to retrieve answer');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (!result?.answer) return;
    navigator.clipboard.writeText(result.answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="glass-card query-box-container">
      <div className="card-header">
        <h2 className="card-title">
          <Sparkles size={20} color="var(--accent-primary)" />
          Semantic Search & RAG Q&A
        </h2>
      </div>

      <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)' }}>
        Ask any question across your entire saved inbox. The RAG pipeline embeds your query, retrieves the most relevant chunks via cosine similarity, and synthesizes an answer grounded in cited sources.
      </p>

      {error && (
        <div className="alert-box error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); handleAsk(); }}>
        <div className="query-input-bar">
          <input
            type="text"
            className="query-input"
            placeholder={itemsCount > 0 ? "Ask a question about your saved knowledge..." : "Add items to your inbox first, then ask anything..."}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-ask"
            disabled={loading || !question.trim()}
          >
            {loading ? <Loader2 size={18} className="spinner" /> : <Send size={18} />}
            <span>Ask</span>
          </button>
        </div>
      </form>

      {/* Suggested Questions */}
      <div className="suggestions-row">
        {sampleQuestions.map((sq, i) => (
          <button
            key={i}
            type="button"
            className="suggestion-pill"
            onClick={() => { setQuestion(sq); handleAsk(sq); }}
            disabled={loading}
          >
            "{sq}"
          </button>
        ))}
      </div>

      {/* Answer and Citations View */}
      {result && (
        <div className="answer-panel">
          <div className="answer-header">
            <span className="answer-badge">
              <Sparkles size={16} />
              Grounded AI Response
            </span>

            <button
              type="button"
              className="suggestion-pill"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              onClick={copyToClipboard}
              title="Copy Answer"
            >
              {copied ? <Check size={14} color="var(--accent-emerald)" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>

          <div className="answer-body">{result.answer}</div>

          {result.sources && result.sources.length > 0 && (
            <div className="sources-section">
              <div className="sources-title">
                <BookOpen size={15} />
                Cited Sources ({result.sources.length})
              </div>

              <div className="source-cards-grid">
                {result.sources.map((src, idx) => (
                  <div key={idx} className="source-card">
                    <div className="source-card-header">
                      <span className="source-card-title" title={src.source_title}>
                        [{idx + 1}] {src.source_title}
                      </span>
                      <span className="score-badge" title="Cosine similarity score">
                        {(src.similarity_score * 100).toFixed(1)}% match
                      </span>
                    </div>

                    <div className="source-card-content">
                      <Quote size={12} style={{ display: 'inline', marginRight: '4px', opacity: 0.6 }} />
                      {src.content}
                    </div>

                    {src.source_url && (
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {src.source_url}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
