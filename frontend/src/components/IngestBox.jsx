import React, { useState } from 'react';
import { PlusCircle, FileText, Globe, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { ingestItem } from '../api';

export default function IngestBox({ onItemIngested }) {
  const [sourceType, setSourceType] = useState('note'); // 'note' | 'url'
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (sourceType === 'note' && !content.trim()) {
      setError('Please enter note content.');
      return;
    }
    if (sourceType === 'url') {
      if (!url.trim()) {
        setError('Please enter a target URL.');
        return;
      }
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        setError('URL must start with http:// or https://');
        return;
      }
    }

    try {
      setLoading(true);
      const res = await ingestItem({
        sourceType,
        title,
        content,
        url,
      });

      setSuccess(`Saved "${res.title}" and generated ${res.chunk_count} vector chunk(s).`);
      setTitle('');
      setContent('');
      setUrl('');
      if (onItemIngested) onItemIngested(res);
    } catch (err) {
      setError(err.message || 'Ingestion failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card">
      <div className="card-header">
        <h2 className="card-title">
          <PlusCircle size={18} color="var(--accent-primary)" />
          Ingest Knowledge
        </h2>
      </div>

      <div className="tabs-container">
        <button
          type="button"
          className={`tab-btn ${sourceType === 'note' ? 'active' : ''}`}
          onClick={() => { setSourceType('note'); setError(null); setSuccess(null); }}
        >
          <FileText size={15} />
          Plain Note
        </button>
        <button
          type="button"
          className={`tab-btn ${sourceType === 'url' ? 'active' : ''}`}
          onClick={() => { setSourceType('url'); setError(null); setSuccess(null); }}
        >
          <Globe size={15} />
          Web URL
        </button>
      </div>

      {error && (
        <div className="alert-box error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="alert-box success">
          <CheckCircle2 size={16} />
          <span>{success}</span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="input-label">Title (Optional)</label>
          <input
            type="text"
            className="text-input"
            placeholder={sourceType === 'note' ? 'e.g. Distributed Systems Memo' : 'e.g. FastAPI Documentation'}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={loading}
          />
        </div>

        {sourceType === 'note' ? (
          <div className="form-group">
            <label className="input-label">Note Content *</label>
            <textarea
              className="textarea-input"
              rows={4}
              placeholder="Paste or write thoughts, code patterns, meeting notes..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={loading}
            />
          </div>
        ) : (
          <div className="form-group">
            <label className="input-label">Web URL *</label>
            <input
              type="url"
              className="text-input"
              placeholder="https://example.com/article"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={loading}
            />
          </div>
        )}

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? (
            <>
              <Loader2 size={18} className="spinner" />
              {sourceType === 'url' ? 'Fetching & Indexing...' : 'Chunking & Embedding...'}
            </>
          ) : (
            <>
              <PlusCircle size={18} />
              Save to Inbox
            </>
          )}
        </button>
      </form>
    </div>
  );
}
