import { useEffect, useState } from 'react';
import type { Fusion } from '../api/searchApi';
import { fetchGenres } from '../api/searchApi';
import '../styles/FilterPanel.css';

interface FilterPanelProps {
  genre: string;
  yearFrom: number;
  yearTo: number;
  fusion: Fusion;
  vectorWeight: number;
  numResults: number;
  onGenreChange: (genre: string) => void;
  onYearFromChange: (year: number) => void;
  onYearToChange: (year: number) => void;
  onFusionChange: (fusion: Fusion) => void;
  onVectorWeightChange: (weight: number) => void;
  onNumResultsChange: (num: number) => void;
}

const FALLBACK_GENRES = ['action', 'adventure', 'animation', 'comedy', 'crime', 'drama', 'horror', 'romance', 'scifi'];

export function FilterPanel({
  genre,
  yearFrom,
  yearTo,
  fusion,
  vectorWeight,
  numResults,
  onGenreChange,
  onYearFromChange,
  onYearToChange,
  onFusionChange,
  onVectorWeightChange,
  onNumResultsChange,
}: FilterPanelProps) {
  const [genres, setGenres] = useState<string[]>(FALLBACK_GENRES);

  useEffect(() => {
    fetchGenres()
      .then((res) => {
        if (res.genres.length > 0) setGenres(res.genres);
      })
      .catch(() => {
        /* keep fallback list */
      });
  }, []);

  return (
    <div className="filter-panel">
      <div className="filters-row">
        <div className="filter-group">
          <label className="filter-label">Genre (TAG filter)</label>
          <select className="filter-select" value={genre} onChange={(e) => onGenreChange(e.target.value)}>
            <option value="all">All</option>
            {genres.map((g) => (
              <option key={g} value={g}>
                {g.charAt(0).toUpperCase() + g.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label className="filter-label">
            Years (NUMERIC filter): <span className="filter-value">{yearFrom} – {yearTo}</span>
          </label>
          <div className="slider-labels">
            <span>From</span>
            <input
              type="range"
              className="filter-slider"
              min="1950"
              max="2025"
              value={yearFrom}
              onChange={(e) => onYearFromChange(Math.min(Number(e.target.value), yearTo))}
            />
          </div>
          <div className="slider-labels">
            <span>To</span>
            <input
              type="range"
              className="filter-slider"
              min="1950"
              max="2025"
              value={yearTo}
              onChange={(e) => onYearToChange(Math.max(Number(e.target.value), yearFrom))}
            />
          </div>
        </div>

        <div className="filter-group">
          <label className="filter-label">Fusion method</label>
          <select className="filter-select" value={fusion} onChange={(e) => onFusionChange(e.target.value as Fusion)}>
            <option value="RRF">RRF (reciprocal rank fusion)</option>
            <option value="LINEAR">LINEAR (weighted scores)</option>
          </select>
        </div>

        {fusion === 'LINEAR' && (
          <div className="filter-group">
            <label className="filter-label">
              Vector weight: <span className="filter-value">{vectorWeight.toFixed(2)}</span>
            </label>
            <div className="slider-labels">
              <span>Text</span>
              <input
                type="range"
                className="filter-slider alpha-slider"
                min="0"
                max="1"
                step="0.05"
                value={vectorWeight}
                onChange={(e) => onVectorWeightChange(Number(e.target.value))}
              />
              <span>Vector</span>
            </div>
          </div>
        )}

        <div className="filter-group">
          <label className="filter-label">
            Results: <span className="filter-value">{numResults}</span>
          </label>
          <input
            type="range"
            className="filter-slider"
            min="1"
            max="24"
            value={numResults}
            onChange={(e) => onNumResultsChange(Number(e.target.value))}
          />
        </div>
      </div>
    </div>
  );
}
