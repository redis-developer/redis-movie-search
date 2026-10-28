import { useCallback, useState } from 'react';
import { SearchBar } from './components/SearchBar';
import { FilterPanel } from './components/FilterPanel';
import { ResultsGrid } from './components/ResultsGrid';
import { StatusPanel } from './components/StatusPanel';
import type { Fusion, SearchResponse } from './api/searchApi';
import { searchClips } from './api/searchApi';
import './App.css';

const EXAMPLE_QUERIES = [
  'a dinosaur escaping during a thunderstorm',
  'two men talking in a diner late at night',
  'someone dancing down a long staircase',
  'astronauts facing a giant wave',
  'kiss in the rain',
];

function App() {
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState('');

  // Search options
  const [genre, setGenre] = useState('all');
  const [yearFrom, setYearFrom] = useState(1950);
  const [yearTo, setYearTo] = useState(2025);
  const [fusion, setFusion] = useState<Fusion>('RRF');
  const [vectorWeight, setVectorWeight] = useState(0.7);
  const [numResults, setNumResults] = useState(6);

  const runSearch = useCallback(
    async (query: string) => {
      setIsLoading(true);
      setError(null);
      setLastQuery(query);
      try {
        const res = await searchClips({
          query,
          num_results: numResults,
          genre: genre !== 'all' ? genre : undefined,
          year_from: yearFrom > 1950 ? yearFrom : undefined,
          year_to: yearTo < 2025 ? yearTo : undefined,
          fusion,
          vector_weight: vectorWeight,
        });
        setResponse(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Search failed');
        setResponse(null);
      } finally {
        setIsLoading(false);
      }
    },
    [genre, yearFrom, yearTo, fusion, vectorWeight, numResults],
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Video Clip Searcher</h1>
        <p className="app-subtitle">
          Describe a scene. Redis hybrid search (BM25 + vector) finds the clip.
        </p>
      </header>

      <main className="app-main">
        <StatusPanel />

        <SearchBar onSearch={runSearch} isLoading={isLoading} />

        <div className="example-queries">
          {EXAMPLE_QUERIES.map((q) => (
            <button key={q} className="example-chip" onClick={() => runSearch(q)} disabled={isLoading}>
              {q}
            </button>
          ))}
        </div>

        <FilterPanel
          genre={genre}
          yearFrom={yearFrom}
          yearTo={yearTo}
          fusion={fusion}
          vectorWeight={vectorWeight}
          numResults={numResults}
          onGenreChange={setGenre}
          onYearFromChange={setYearFrom}
          onYearToChange={setYearTo}
          onFusionChange={setFusion}
          onVectorWeightChange={setVectorWeight}
          onNumResultsChange={setNumResults}
        />

        {error && <div className="error-banner">{error}</div>}

        <ResultsGrid response={response} isLoading={isLoading} hasSearched={lastQuery !== ''} />
      </main>
    </div>
  );
}

export default App;
