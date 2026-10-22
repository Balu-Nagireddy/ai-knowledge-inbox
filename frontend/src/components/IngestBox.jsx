import React, { useState, useRef } from 'react';
import { PlusCircle, FileText, Globe, UploadCloud, Loader2, AlertCircle, CheckCircle2, FileUp, X, Files } from 'lucide-react';
import { ingestItem, uploadFileItem, uploadFilesBatch } from '../api';

export default function IngestBox({ onItemIngested }) {
  const [sourceType, setSourceType] = useState('note'); // 'note' | 'url' | 'file'
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [url, setUrl] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setSelectedFiles((prev) => {
        const existingNames = new Set(prev.map((f) => f.name));
        return [...prev, ...newFiles.filter((f) => !existingNames.has(f.name))];
      });
      setError(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setSelectedFiles((prev) => {
        const existingNames = new Set(prev.map((f) => f.name));
        return [...prev, ...newFiles.filter((f) => !existingNames.has(f.name))];
      });
      setError(null);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const removeFile = (idx, e) => {
    if (e) e.stopPropagation();
    setSelectedFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearAllFiles = (e) => {
    if (e) e.stopPropagation();
    setSelectedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

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
    if (sourceType === 'file') {
      if (selectedFiles.length === 0) {
        setError('Please choose at least one document file to upload (.pdf, .docx, .md, .txt).');
        return;
      }
    }

    try {
      setLoading(true);
      if (sourceType === 'file') {
        if (selectedFiles.length === 1) {
          const res = await uploadFileItem({
            file: selectedFiles[0],
            title: title || selectedFiles[0].name,
          });
          setSuccess(`Saved "${res.title}" and generated ${res.chunk_count} vector chunk(s).`);
          if (onItemIngested) onItemIngested(res);
        } else {
          const batchRes = await uploadFilesBatch({ files: selectedFiles });
          setSuccess(`Batch uploaded ${batchRes.total_files} documents with ${batchRes.total_chunks} total vector chunk(s).`);
          if (onItemIngested) onItemIngested();
        }
        setSelectedFiles([]);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        const res = await ingestItem({
          sourceType,
          title,
          content,
          url,
        });
        setSuccess(`Saved "${res.title}" and generated ${res.chunk_count} vector chunk(s).`);
        if (onItemIngested) onItemIngested(res);
      }

      setTitle('');
      setContent('');
      setUrl('');
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
        <button
          type="button"
          className={`tab-btn ${sourceType === 'file' ? 'active' : ''}`}
          onClick={() => { setSourceType('file'); setError(null); setSuccess(null); }}
        >
          <UploadCloud size={15} />
          Upload File
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
            placeholder={
              sourceType === 'note'
                ? 'e.g. Distributed Systems Memo'
                : sourceType === 'url'
                ? 'e.g. FastAPI Documentation'
                : 'e.g. DevOps Playbook (defaults to filename)'
            }
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={loading}
          />
        </div>

        {sourceType === 'note' && (
          <div className="form-group">
            <label className="input-label">Note Content *</label>
            <textarea
              className="textarea-input"
              rows={4}
              placeholder="Paste or write thoughts, meeting notes, code snippets..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={loading}
            />
          </div>
        )}

        {sourceType === 'url' && (
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

        {sourceType === 'file' && (
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <label className="input-label" style={{ marginBottom: 0 }}>
                Document Files (.pdf, .docx, .md, .txt) *
              </label>
              {selectedFiles.length > 0 && (
                <button
                  type="button"
                  className="clear-file-btn"
                  style={{ color: 'var(--text-muted)', fontSize: '0.78rem', background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={clearAllFiles}
                >
                  Clear all ({selectedFiles.length})
                </button>
              )}
            </div>

            <div
              className={`file-dropzone ${isDragging ? 'dragging' : ''} ${selectedFiles.length > 0 ? 'has-file' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                multiple
                accept=".pdf,.docx,.doc,.md,.txt"
                onChange={handleFileChange}
              />

              {selectedFiles.length > 0 ? (
                <div className="selected-files-container" onClick={(e) => e.stopPropagation()}>
                  <div className="files-summary-bar">
                    <span className="files-count-badge">
                      <Files size={14} />
                      {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                    </span>
                    <button
                      type="button"
                      className="add-more-files-btn"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      + Add more
                    </button>
                  </div>

                  <div className="files-chips-list">
                    {selectedFiles.map((f, idx) => (
                      <div key={idx} className="selected-file-pill">
                        <FileUp size={16} color="var(--accent-secondary)" />
                        <div className="file-info-text">
                          <span className="file-name" title={f.name}>{f.name}</span>
                          <span className="file-size">{(f.size / 1024).toFixed(1)} KB</span>
                        </div>
                        <button
                          type="button"
                          className="clear-file-btn"
                          onClick={(e) => removeFile(idx, e)}
                          title="Remove file"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="dropzone-prompt">
                  <UploadCloud size={34} className="dropzone-icon" />
                  <p className="dropzone-main-text">Click or drag & drop files here</p>
                  <p className="dropzone-sub-text">Select single or multiple files (PDF, Word, Markdown, Text)</p>
                </div>
              )}
            </div>
          </div>
        )}

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? (
            <>
              <Loader2 size={18} className="spinner" />
              {sourceType === 'file'
                ? `Indexing ${selectedFiles.length} File${selectedFiles.length > 1 ? 's' : ''}...`
                : sourceType === 'url'
                ? 'Fetching & Indexing...'
                : 'Chunking & Embedding...'}
            </>
          ) : (
            <>
              <PlusCircle size={18} />
              {sourceType === 'file' && selectedFiles.length > 1
                ? `Save ${selectedFiles.length} Files to Inbox`
                : 'Save to Inbox'}
            </>
          )}
        </button>
      </form>
    </div>
  );
}
