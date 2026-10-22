import React, { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Sparkles,
  Send,
  Loader2,
  BookOpen,
  Copy,
  Check,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  FileText,
  Globe,
  Quote
} from 'lucide-react';
import { queryKnowledgeStream, queryKnowledge } from '../api';

export default function AskKnowledge({ itemsCount }) {
  const [question, setQuestion] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const [sources, setSources] = useState([]);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [expandedSourceIdx, setExpandedSourceIdx] = useState(null);

  const sampleQuestions = [
    "What key concepts are covered in my notes?",
    "Summarize the main takeaways from the saved content.",
    "What are the best practices or architectural highlights mentioned?"
  ];

  const handleAsk = async (queryText) => {
    const q = (queryText || question).trim();
    if (!q) return;

    setError(null);
    setIsStreaming(true);
    setAnswerText('');
    setSources([]);
    setExpandedSourceIdx(null);

    try {
      // Use real-time streaming endpoint
      await queryKnowledgeStream(q, 4, {
        onSources: (retrievedSources) => {
          setSources(retrievedSources || []);
        },
        onToken: (token) => {
          setAnswerText((prev) => prev + token);
        },
        onDone: () => {
          setIsStreaming(false);
        },
        onError: async (err) => {
          console.warn('Streaming error, falling back to standard query:', err);
          // Fallback to standard POST /query
          try {
            const data = await queryKnowledge(q, 4);
            setAnswerText(data.answer);
            setSources(data.sources || []);
          } catch (fallbackErr) {
            setError(fallbackErr.message || 'Failed to retrieve answer');
          } finally {
            setIsStreaming(false);
          }
        }
      });
    } catch (err) {
      setError(err.message || 'Failed to execute query');
      setIsStreaming(false);
    }
  };

  const copyToClipboard = () => {
    if (!answerText) return;
    navigator.clipboard.writeText(answerText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleSourceExpand = (idx) => {
    setExpandedSourceIdx(expandedSourceIdx === idx ? null : idx);
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
        Ask any question across your knowledge inbox. The pipeline retrieves the most relevant chunks via vector similarity and synthesizes a grounded answer powered by Gemini with footnote citations.
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
            placeholder={
              itemsCount > 0
                ? "Ask a question about your saved knowledge..."
                : "Add notes or URLs above first, then ask anything..."
            }
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={isStreaming}
          />
          <button
            type="submit"
            className="btn-ask"
            disabled={isStreaming || !question.trim()}
          >
            {isStreaming ? <Loader2 size={18} className="spinner" /> : <Send size={18} />}
            <span>{isStreaming ? 'Thinking...' : 'Ask'}</span>
          </button>
        </div>
      </form>

      {/* Suggested prompts */}
      <div className="suggestions-row">
        {sampleQuestions.map((sq, i) => (
          <button
            key={i}
            type="button"
            className="suggestion-pill"
            onClick={() => { setQuestion(sq); handleAsk(sq); }}
            disabled={isStreaming}
          >
            "{sq}"
          </button>
        ))}
      </div>

      {/* Answer & Clean References Footnotes View */}
      {(answerText || isStreaming) && (
        <div className="answer-panel">
          <div className="answer-header">
            <span className="answer-badge">
              <Sparkles size={16} />
              Grounded AI Response
            </span>

            {answerText && (
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
            )}
          </div>

          {/* Real-time Markdown Answer Body */}
          <div className="markdown-answer-body">
            <ReactMarkdown>{answerText}</ReactMarkdown>
            {isStreaming && <span className="typing-cursor"></span>}
          </div>

          {/* References & Footnotes List */}
          {sources.length > 0 && !isStreaming && (
            <div className="references-footer">
              <div className="references-header">
                <BookOpen size={15} color="var(--accent-secondary)" />
                <span>References & Cited Sources ({sources.length})</span>
              </div>

              <div className="references-list">
                {sources.map((src, idx) => {
                  const isExpanded = expandedSourceIdx === idx;
                  const scorePct = (src.similarity_score * 100).toFixed(1);

                  return (
                    <div key={idx} className="reference-item">
                      <div className="reference-row" onClick={() => toggleSourceExpand(idx)}>
                        <div className="reference-meta">
                          <span className="reference-index">[{idx + 1}]</span>
                          <span className="reference-icon">
                            {src.source_type === 'url' ? <Globe size={13} /> : <FileText size={13} />}
                          </span>
                          <span className="reference-title">{src.source_title}</span>
                          {src.source_url && (
                            <a
                              href={src.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="reference-link"
                              onClick={(e) => e.stopPropagation()}
                              title="Open original page"
                            >
                              <ExternalLink size={12} />
                            </a>
                          )}
                        </div>

                        <div className="reference-actions">
                          <span className="score-badge" title="Vector similarity score">
                            {scorePct}% match
                          </span>
                          <button
                            type="button"
                            className="expand-btn"
                            title={isExpanded ? "Collapse excerpt" : "Expand excerpt"}
                          >
                            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </button>
                        </div>
                      </div>

                      {/* Expandable Excerpt Drawer */}
                      {isExpanded && (
                        <div className="reference-excerpt">
                          <div className="excerpt-label">
                            <Quote size={12} /> Excerpt used by RAG pipeline:
                          </div>
                          <p className="excerpt-content">{src.content}</p>
                          {src.source_url && (
                            <div className="excerpt-url">
                              Source URL: <a href={src.source_url} target="_blank" rel="noreferrer">{src.source_url}</a>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
