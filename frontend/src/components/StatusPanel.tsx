import { useEffect, useState } from 'react';
import type { HealthResponse } from '../api/searchApi';
import { checkHealth, ingestClips } from '../api/searchApi';
import '../styles/StatusPanel.css';

export function StatusPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchHealth = async () => {
    setIsChecking(true);
    try {
      setHealth(await checkHealth());
    } catch (err) {
      setHealth(null);
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to check health' });
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    checkHealth()
      .then((res) => {
        if (!cancelled) setHealth(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setHealth(null);
        setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to check health' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleIngest = async () => {
    setIsIngesting(true);
    setMessage(null);
    try {
      const result = await ingestClips();
      setMessage({ type: 'success', text: `Embedded and indexed ${result.clips_loaded} clips` });
      await fetchHealth();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Ingest failed' });
    } finally {
      setIsIngesting(false);
    }
  };

  const statusClass = !health
    ? 'disconnected'
    : health.status === 'healthy'
      ? 'healthy'
      : health.redis_connected
        ? 'warning'
        : 'disconnected';

  const statusText = !health
    ? 'Unable to reach API'
    : health.status === 'healthy'
      ? 'Ready'
      : health.redis_connected
        ? 'Index not built'
        : 'Redis disconnected';

  const numDocs = health?.index_info?.num_docs;
  const backend = health?.index_info?.hybrid_backend;

  return (
    <div className="status-panel">
      <div className="status-section">
        <div className="status-indicator">
          <div className={`status-dot ${statusClass}`} />
          <span className="status-text">{statusText}</span>
        </div>

        <div className="status-details">
          <div className="detail-item">
            <span className="detail-label">Redis:</span>
            <span className={`detail-value ${health?.redis_connected ? 'connected' : 'disconnected'}`}>
              {health?.redis_connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Index:</span>
            <span className={`detail-value ${health?.index_exists ? 'connected' : 'disconnected'}`}>
              {health?.index_exists ? 'video_clips' : 'Not found'}
            </span>
          </div>
          {numDocs !== undefined && (
            <div className="detail-item">
              <span className="detail-label">Clips:</span>
              <span className="detail-value">{String(numDocs)}</span>
            </div>
          )}
          {backend !== undefined && (
            <div className="detail-item">
              <span className="detail-label">Hybrid:</span>
              <span className="detail-value">{String(backend)}</span>
            </div>
          )}
        </div>
      </div>

      <div className="status-actions">
        <button className="action-button refresh-button" onClick={fetchHealth} disabled={isChecking} title="Check status">
          {isChecking ? (
            <span className="button-spinner" />
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="button-icon">
              <path d="M21 12a9 9 0 11-2.5-6.2" strokeLinecap="round" />
              <path d="M21 3v6h-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          <span>Check Health</span>
        </button>

        <button
          className="action-button load-button"
          onClick={handleIngest}
          disabled={isIngesting || !health?.redis_connected}
          title={health?.redis_connected ? 'Embed clips.json and build the index' : 'Connect to Redis first'}
        >
          {isIngesting ? (
            <>
              <span className="button-spinner" />
              <span>Embedding...</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="button-icon">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="17,8 12,3 7,8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span>Ingest Clips</span>
            </>
          )}
        </button>
      </div>

      {message && (
        <div className={`status-message ${message.type}`}>
          {message.type === 'success' ? '✓' : '✗'} {message.text}
        </div>
      )}
    </div>
  );
}
