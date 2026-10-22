import React from 'react';
import { Database, FileText, Globe, Trash2, ExternalLink, RefreshCw, Layers } from 'lucide-react';

export default function KnowledgeInbox({ items, loading, onRefresh, onDeleteItem }) {
  const formatDate = (isoString) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="glass-card">
      <div className="card-header">
        <h2 className="card-title">
          <Database size={18} color="var(--accent-secondary)" />
          Saved Knowledge ({items.length})
        </h2>
        <button
          type="button"
          className="btn-icon-danger"
          style={{ color: 'var(--text-muted)' }}
          onClick={onRefresh}
          title="Refresh List"
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? 'spinner' : ''} />
        </button>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <Database size={36} className="empty-state-icon" />
          <p className="empty-state-text">Your inbox is empty.</p>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginTop: '4px' }}>
            Add a note or paste a URL above to start building your knowledge base.
          </p>
        </div>
      ) : (
        <div className="items-list">
          {items.map((item) => (
            <div key={item.id} className="item-card">
              <div className="item-header">
                <span className={`item-badge ${item.source_type}`}>
                  {item.source_type === 'url' ? <Globe size={11} /> : <FileText size={11} />}
                  {item.source_type}
                </span>

                <button
                  type="button"
                  className="btn-icon-danger"
                  onClick={() => onDeleteItem(item.id)}
                  title="Delete item"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              <div className="item-title">
                {item.title}
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ marginLeft: '6px', color: 'var(--accent-secondary)', display: 'inline-flex', verticalAlign: 'middle' }}
                  >
                    <ExternalLink size={13} />
                  </a>
                )}
              </div>

              <p className="item-snippet">{item.raw_content}</p>

              <div className="item-meta">
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <Layers size={12} color="var(--accent-primary)" />
                  {item.chunk_count} chunk{item.chunk_count !== 1 ? 's' : ''}
                </span>
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
