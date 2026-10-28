import type { SearchResponse } from '../api/searchApi';
import { ClipCard } from './ClipCard';
import '../styles/ResultsGrid.css';

interface ResultsGridProps {
  response: SearchResponse | null;
  isLoading: boolean;
  hasSearched: boolean;
}

export function ResultsGrid({ response, isLoading, hasSearched }: ResultsGridProps) {
  if (isLoading) {
    return (
      <div className="results-loading">
        <div className="loading-spinner" />
        <p>Embedding your description and searching Redis...</p>
      </div>
    );
  }

  if (!hasSearched || !response) {
    return (
      <div className="results-empty">
        <div className="empty-icon">🎬</div>
        <h3>Find a clip by describing it</h3>
        <p>Type what happens in the scene. No need to remember the movie title.</p>
      </div>
    );
  }

  if (response.results.length === 0) {
    return (
      <div className="results-empty">
        <div className="empty-icon">🔍</div>
        <h3>No clips matched</h3>
        <p>Try a different description or loosen the genre and year filters.</p>
      </div>
    );
  }

  return (
    <div className="results-container">
      <div className="results-header">
        <span className="results-count">
          {response.count} clip{response.count === 1 ? '' : 's'} for “{response.query}”
        </span>
        <span className="results-type">
          {response.backend} · {response.fusion} · {response.took_ms} ms
        </span>
      </div>
      <div className="results-grid">
        {response.results.map((clip, index) => (
          <ClipCard key={`${clip.id || clip.title}-${clip.rank}`} clip={clip} index={index} />
        ))}
      </div>
    </div>
  );
}
