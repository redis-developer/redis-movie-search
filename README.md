# Video Clip Searcher (Redis hybrid search)

Describe a scene in plain English and get back the matching movie clip.
Every clip has a text description. At ingest time the description is
embedded and stored in Redis next to the clip metadata. At query time the
user's description is embedded once and Redis runs a **hybrid search** that
fuses BM25 full-text scoring with vector similarity, inside the database.

Built with **FastAPI + RedisVL** (backend) and **React + Vite** (frontend).
Originally developed as a standalone module of the
[full-stack-redis-ai-workshop](https://github.com/redis-developer/full-stack-redis-ai-workshop).

```
user description ──► HFTextVectorizer (all-MiniLM-L6-v2, 384 dims)
                              │
                              ▼
      Redis  FT.HYBRID  ─ BM25 over @content  ┐
             (video_clips index)              ├─► RRF or LINEAR fusion ─► top-K clips
                        ─ KNN over @embedding ┘
             + TAG filter @genre, NUMERIC filter @year (applied inside Redis)
```

## What is in Redis

One hash per clip, key `clip:<id>`:

| Field | Indexed as | Purpose |
|---|---|---|
| `content` | TEXT | `title. movie (year). description`, BM25 scored |
| `genre` | TAG | exact-match filter |
| `year` | NUMERIC | range filter |
| `embedding` | VECTOR HNSW, 384 float32, cosine | semantic similarity |
| `title`, `movie`, `director`, `description`, `duration_seconds`, `video_url`, `thumbnail_url` | not indexed | returned for display only; `video_url` may be a YouTube link or a direct MP4 |

Only the fields that are queried are indexed. Query embeddings are cached
for ten minutes in a RedisVL `EmbeddingsCache` (`clip_embedcache:*`) so
repeated searches skip the model.

Hybrid query: RedisVL `HybridQuery` (one `FT.HYBRID` call, Redis 8.4+ or
Redis Cloud). If the server does not support `FT.HYBRID` the engine falls
back to RedisVL `AggregateHybridQuery` (one `FT.AGGREGATE` call). The UI shows
which path was used.

## Quick start

Prerequisites: Python 3.11 to 3.13, Node 20+, and a Redis database with the
Query Engine. Redis Cloud free tier works: [redis.io/try-free](https://redis.io/try-free).

```bash
git clone https://github.com/redis-developer/redis-movie-search.git
cd redis-movie-search
cp .env.example .env          # set REDIS_URL=redis://default:<password>@<host>:<port>
```

### Option A: run locally

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m backend.ingest           # embed clips.json and build the index
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend && npm install && npm run dev    # http://localhost:5173
```

`scripts/dev.sh` does both in one go.

### Option B: Docker

```bash
docker compose up --build                    # UI on http://localhost:3000, API on :8000
```

Without `REDIS_URL` in `.env`, add `--profile local-redis` to also start a
local Redis 8.4 container. Then click **Ingest Clips** in the UI or run:

```bash
curl -X POST http://localhost:8000/api/ingest
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Redis connectivity, index status, hybrid backend in use |
| GET | `/api/genres` | distinct genre tags (`FT.AGGREGATE ... GROUPBY @genre`) |
| POST | `/api/search` | hybrid search, body below |
| POST | `/api/ingest` | embed `resources/clips.json`, write hashes, create index |
| POST | `/api/clear` | drop the index and delete `clip:*` keys |

```json
POST /api/search
{
  "query": "a dinosaur escaping during a thunderstorm",
  "num_results": 6,
  "genre": "adventure",
  "year_from": 1990,
  "year_to": 2010,
  "fusion": "RRF",
  "vector_weight": 0.7
}
```

`fusion` is `RRF` (reciprocal rank fusion, default) or `LINEAR`
(`vector_weight * vector_similarity + (1 - vector_weight) * text_score`).
Each result carries `hybrid_score`, `text_score` and `vector_similarity`.

Interactive docs: http://localhost:8000/docs

## Bringing your own clips

`resources/clips.json` is an array of objects:

```json
{
  "id": "1",
  "title": "King of the World",
  "movie": "Titanic",
  "year": 1997,
  "genre": "romance",
  "director": "James Cameron",
  "duration_seconds": 95,
  "description": "A young man stands at the bow of a massive ocean liner at sunset ...",
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "thumbnail_url": "",
  "source": "scene"
}
```

`id`, `title`, `movie`, `year`, `genre` and `description` are required. The
richer the description, the better both the keyword and the semantic match.
Re-run `python -m backend.ingest` (or `python -m backend.ingest path/to/file.json`)
after editing.

**Video sources.** `video_url` can be either:

- a **YouTube URL** (`https://www.youtube.com/watch?v=...`, `youtu.be/...`, shorts or embed links). The card shows the YouTube thumbnail and plays the video in an embedded `youtube-nocookie.com` player. The sample data uses this: 42 entries point at the scene clip (mostly the Movieclips or studio channel) and 6 fall back to the official trailer where no clean scene upload exists; the optional `source` field records which (`scene` or `trailer`).
- a **direct media URL** (MP4/WebM on S3, CloudFront, Mux, etc.). The card then uses a plain HTML5 `<video>` player and `thumbnail_url` as the poster.

`thumbnail_url` is optional for YouTube links; it is derived from the video id when empty.

## Project layout

```
redis-movie-search/
├── backend/
│   ├── config.py          REDIS_URL, index schema, defaults
│   ├── search_engine.py   RedisVL index, HybridQuery (+ aggregate fallback), ingest
│   ├── main.py            FastAPI endpoints
│   ├── ingest.py          CLI: python -m backend.ingest [file.json | --clear]
│   └── requirements.txt
├── frontend/              React + Vite + TypeScript
│   └── src/
│       ├── api/searchApi.ts
│       ├── components/    SearchBar, FilterPanel, ResultsGrid, ClipCard, StatusPanel
│       └── App.tsx
├── resources/clips.json   clip metadata + descriptions
├── scripts/dev.sh         run backend + frontend locally
├── docker-compose.yml     backend, frontend, optional local Redis 8.4
└── Dockerfile.backend / Dockerfile.frontend / nginx.conf
```

## Troubleshooting

- **`Index not found`**: run `POST /api/ingest` (or the Ingest Clips button).
- **`unknown command 'FT.HYBRID'`** in the logs: the server is older than
  Redis 8.4. The engine switches to the `FT.AGGREGATE` fallback automatically
  and the status panel shows "FT.AGGREGATE fallback".
- **Slow first request**: the embedding model downloads on first use
  (about 90 MB). In Docker it is cached in the `hf-cache` volume.
- **Dimension errors**: `EMBEDDING_DIMS` must match the model (384 for
  all-MiniLM-L6-v2). Change both together, then re-ingest.
