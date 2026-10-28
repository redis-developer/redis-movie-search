"""
Configuration for the Video Clip Searcher backend.

Index design follows the Redis Query Engine guidance:
  * only fields that are queried are indexed (content TEXT, genre TAG,
    year NUMERIC, embedding VECTOR); display-only fields (title, movie,
    description, video_url, ...) live in the same hash but are not indexed.
  * TAG for exact-match filters, NUMERIC for ranges, TEXT for BM25.
  * HNSW vector field whose dims / metric match the embedding model.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Redis connection (Redis Cloud or Redis 8.x). FT.HYBRID needs Redis >= 8.4.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_CONNECT_TIMEOUT = float(os.getenv("REDIS_CONNECT_TIMEOUT", "2.0"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "10.0"))

# Where the clip metadata lives
RESOURCES_DIR = Path(os.getenv("RESOURCES_DIR", Path(__file__).resolve().parent.parent / "resources"))
CLIPS_FILE = RESOURCES_DIR / "clips.json"

# Index configuration
INDEX_NAME = "video_clips"
KEY_PREFIX = "clip:"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "384"))
EMBEDDING_CACHE_NAME = "clip_embedcache"
EMBEDDING_CACHE_TTL = 600  # seconds; query embeddings are reused for 10 minutes

# Fields indexed for search vs. stored only for display
TEXT_FIELD = "content"          # title + movie + description, BM25 scored
VECTOR_FIELD = "embedding"      # embedding of the same text
RETURN_FIELDS = [
    "id",            # stored in the hash; FT.HYBRID LOAD does not return the key itself
    "title",
    "movie",
    "year",
    "genre",
    "director",
    "duration_seconds",
    "description",
    "video_url",
    "thumbnail_url",
]

# Search defaults
DEFAULT_NUM_RESULTS = 6
MAX_NUM_RESULTS = 24
DEFAULT_FUSION = "RRF"          # RRF (rank fusion) or LINEAR (weighted scores)
DEFAULT_VECTOR_WEIGHT = 0.7     # LINEAR only: 1.0 = pure vector, 0.0 = pure text

INDEX_SCHEMA = {
    "index": {
        "name": INDEX_NAME,
        "prefix": KEY_PREFIX,
        "storage_type": "hash",
    },
    "fields": [
        {"name": TEXT_FIELD, "type": "text"},
        {"name": "genre", "type": "tag"},
        {"name": "year", "type": "numeric"},
        {
            "name": VECTOR_FIELD,
            "type": "vector",
            "attrs": {
                "algorithm": "hnsw",
                "dims": EMBEDDING_DIMS,
                "distance_metric": "cosine",
                "datatype": "float32",
                "m": 16,
                "ef_construction": 200,
            },
        },
    ],
}
