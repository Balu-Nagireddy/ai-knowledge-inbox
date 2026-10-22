import React, { useState, useRef } from 'react';
import { PlusCircle, FileText, Globe, UploadCloud, Loader2, AlertCircle, CheckCircle2, FileUp, X } from 'lucide-react';
import { ingestItem, uploadFileItem } from '../api';

export default function IngestBox({ onItemIngested }) {
  const [sourceType, setSourceType] = useState('note'); // 'note' | 'url' | 'file'
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [url, setUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
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
      if (!selectedFile) {
        setError('Please choose a file to upload (.pdf, .docx, .md, .txt).');
        return;
      }
    }

    try {
      setLoading(true);
      let res;
      if (sourceType === 'file') {
        res = await uploadFileItem({
          file: selectedFile,
          title: title || selectedFile.name,
        });
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        res = await ingestItem({
          sourceType,
          title,
          content,
          url,
        });
      }

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
            <label className="input-label">Document File (.pdf, .docx, .md, .txt) *</label>
            <div
              className={`file-dropzone ${isDragging ? 'dragging' : ''} ${selectedFile ? 'has-file' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".pdf,.docx,.doc,.md,.txt"
                onChange={handleFileChange}
              />

              {selectedFile ? (
                <div className="selected-file-pill">
                  <FileUp size={18} color="var(--accent-secondary)" />
                  <div className="file-info-text">
                    <span className="file-name">{selectedFile.name}</span>
                    <span className="file-size">{(selectedFile.size / 1024).toFixed(1)} KB</span>
                  </div>
                  <button
                    type="button"
                    className="clear-file-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <div className="dropzone-prompt">
                  <UploadCloud size={32} className="dropzone-icon" />
                  <p className="dropzone-main-text">Click or drag & drop document here</p>
                  <p className="dropzone-sub-text">Supports PDF, Word (.docx), Markdown (.md), and Text (.txt)</p>
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
                ? 'Parsing & Indexing File...'
                : sourceType === 'url'
                ? 'Fetching & Indexing...'
                : 'Chunking & Embedding...'}
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
