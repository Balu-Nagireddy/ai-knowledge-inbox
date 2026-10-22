import React, { useState } from 'react';
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
  UploadCloud,
  Quote,
  Compass,
  ArrowRight
} from 'lucide-react';
import { queryKnowledgeStream, queryKnowledge, searchWebAndAnswer } from '../api';

export default function AskKnowledge({ itemsCount, onWebItemIngested }) {
  const [question, setQuestion] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWebSearching, setIsWebSearching] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const [sources, setSources] = useState([]);
  const [needsWebSearch, setNeedsWebSearch] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [expandedSourceIdx, setExpandedSourceIdx] = useState(null);

  const sampleQuestions = [
    "What key concepts are covered in my notes?",
    "What are the responsibilities of a DevOps Engineer?",
    "Summarize the main takeaways from the saved content."
  ];

  const handleAsk = async (queryText) => {
    const q = (queryText || question).trim();
    if (!q) return;

    setError(null);
    setIsStreaming(true);
    setAnswerText('');
    setSources([]);
    setNeedsWebSearch(false);
    setExpandedSourceIdx(null);

    let accumulatedText = "";

    try {
      await queryKnowledgeStream(q, 4, {
        onSources: (retrievedSources) => {
          setSources(retrievedSources || []);
        },
        onToken: (token) => {
          accumulatedText += token;
          setAnswerText(accumulatedText);
        },
        onDone: () => {
          setIsStreaming(false);
          const lower = accumulatedText.toLowerCase();
          if (
            lower.includes("not enough information") ||
            lower.includes("does not contain") ||
            lower.includes("inbox is currently empty") ||
            accumulatedText.length < 5
          ) {
            setNeedsWebSearch(true);
          }
        },
        onError: async (err) => {
          console.warn('Streaming error, falling back to standard query:', err);
          try {
            const data = await queryKnowledge(q, 4);
            setAnswerText(data.answer);
            setSources(data.sources || []);
            setNeedsWebSearch(Boolean(data.needs_web_search));
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

  const handleWebSearchAndIngest = async () => {
    const q = question.trim();
    if (!q) return;
    setIsWebSearching(true);
    setError(null);
    setAnswerText('Searching the live web for relevant documentation, ingesting into Knowledge Inbox, and synthesizing grounded answer with citations...');

    try {
      const data = await searchWebAndAnswer(q);
      setAnswerText(data.answer);
      setSources(data.sources || []);
      setNeedsWebSearch(Boolean(data.needs_web_search));

      if (onWebItemIngested) {
        onWebItemIngested();
      }
    } catch (err) {
      setError(err.message || 'Web search and ingestion failed');
    } finally {
      setIsWebSearching(false);
    }
  };

  const isPositiveAnswer = () => {
    if (!answerText || isStreaming || isWebSearching || needsWebSearch) return false;
    const lower = answerText.toLowerCase();
    if (
      lower.includes("not enough information") ||
      lower.includes("does not contain") ||
      lower.includes("inbox is currently empty") ||
      lower.includes("no relevant content") ||
      lower.includes("encountered a temporary issue") ||
      lower.includes("unable to complete") ||
      lower.includes("please try again") ||
      answerText.trim().length < 20
    ) {
      return false;
    }
    return true;
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
                : "Add notes, URLs, or files above first, then ask anything..."
            }
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={isStreaming || isWebSearching}
          />
          <button
            type="submit"
            className="btn-ask"
            disabled={isStreaming || isWebSearching || !question.trim()}
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
            disabled={isStreaming || isWebSearching}
          >
            "{sq}"
          </button>
        ))}
      </div>

      {/* Answer & Clean References Footnotes View */}
      {(answerText || isStreaming || isWebSearching) && (
        <div className="answer-panel">
          <div className="answer-header">
            <span className="answer-badge">
              <Sparkles size={16} />
              Grounded AI Response
            </span>

            {answerText && !isStreaming && !isWebSearching && (
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
            {(isStreaming || isWebSearching) && <span className="typing-cursor"></span>}
          </div>

          {/* Interactive Web Fallback Banner if Inbox lacked enough info */}
          {needsWebSearch && !isStreaming && (
            <div className="web-fallback-prompt">
              <div className="fallback-info">
                <div className="fallback-icon-wrap">
                  <Compass size={20} color="var(--accent-secondary)" />
                </div>
                <div>
                  <h4 className="fallback-title">Expand Knowledge via Live Web Search?</h4>
                  <p className="fallback-desc">
                    Your saved items don't have enough details on this topic. With your permission, I can search the web, ingest relevant articles directly into your Knowledge Inbox, and answer with citations.
                  </p>
                </div>
              </div>

              <button
                type="button"
                className="btn-web-action"
                onClick={handleWebSearchAndIngest}
                disabled={isWebSearching}
              >
                {isWebSearching ? (
                  <>
                    <Loader2 size={16} className="spinner" />
                    <span>Searching & Ingesting Web Articles...</span>
                  </>
                ) : (
                  <>
                    <Globe size={16} />
                    <span>Search Web & Add to Knowledge Base</span>
                    <ArrowRight size={14} />
                  </>
                )}
              </button>
            </div>
          )}

          {/* References & Footnotes List (Displayed ONLY on positive grounded answers) */}
          {sources.length > 0 && isPositiveAnswer() && (
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
                            {src.source_type === 'url' ? (
                              <Globe size={13} />
                            ) : src.source_type === 'file' ? (
                              <UploadCloud size={13} />
                            ) : (
                              <FileText size={13} />
                            )}
                          </span>
                          <span className="reference-title">{src.source_title}</span>
                          {src.source_url && src.source_type === 'url' && (
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
                              Source: <span style={{ color: 'var(--text-main)' }}>{src.source_url}</span>
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
