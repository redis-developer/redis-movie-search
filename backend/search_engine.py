"""
Hybrid video-clip search on Redis with RedisVL.

A user types a free-text description of a scene. The description is embedded
once, then Redis runs a hybrid query that fuses:

  * BM25 full-text scoring over the `content` TEXT field, and
  * cosine KNN over the `embedding` VECTOR field,

optionally narrowed by TAG (genre) and NUMERIC (year) filters that are applied
inside Redis before ranking.

On Redis >= 8.4 the query is a single FT.HYBRID command (RedisVL `HybridQuery`).
On older servers the engine transparently falls back to RedisVL's
`AggregateHybridQuery`, which emulates the fusion with FT.AGGREGATE.
"""
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from redis import Redis
from redis.exceptions import ResponseError
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.index import SearchIndex
from redisvl.query import HybridQuery
from redisvl.query.aggregate import AggregateHybridQuery
from redisvl.query.filter import FilterExpression, Num, Tag
from redisvl.utils.vectorize import HFTextVectorizer

from .config import (
    CLIPS_FILE,
    DEFAULT_FUSION,
    DEFAULT_NUM_RESULTS,
    DEFAULT_VECTOR_WEIGHT,
    EMBEDDING_CACHE_NAME,
    EMBEDDING_CACHE_TTL,
    EMBEDDING_MODEL,
    INDEX_NAME,
    INDEX_SCHEMA,
    KEY_PREFIX,
    REDIS_CONNECT_TIMEOUT,
    REDIS_SOCKET_TIMEOUT,
    REDIS_URL,
    RETURN_FIELDS,
    TEXT_FIELD,
    VECTOR_FIELD,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Short stopword list so queries like "a man on a boat" still have terms left
# for BM25 (RedisVL's "english" list needs nltk data to be present).
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "he", "her", "his", "i", "if", "in", "into", "is", "it", "its", "me",
    "my", "of", "on", "or", "she", "so", "that", "the", "their", "then", "there",
    "they", "this", "to", "was", "were", "what", "when", "where", "which", "who",
    "with", "would", "you", "your", "scene", "clip", "movie", "film",
}


def clip_search_text(clip: Dict[str, Any]) -> str:
    """The single text that is both BM25-indexed and embedded for a clip."""
    return f"{clip['title']}. {clip['movie']} ({clip['year']}). {clip['description']}"


class VideoClipSearchEngine:
    """Hybrid (text + vector) search over movie clip descriptions."""

    def __init__(self) -> None:
        logger.info("Connecting to Redis at %s", _redact(REDIS_URL))
        # One client for the process: redis-py pools connections internally.
        self.client = Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            retry_on_timeout=True,
        )
        self.index = SearchIndex.from_dict(INDEX_SCHEMA, redis_client=self.client)

        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        self.vectorizer = HFTextVectorizer(
            model=EMBEDDING_MODEL,
            cache=EmbeddingsCache(
                name=EMBEDDING_CACHE_NAME,
                ttl=EMBEDDING_CACHE_TTL,
                redis_client=self.client,
            ),
        )
        # None = not probed yet; True = FT.HYBRID works; False = use aggregate fallback
        self._ft_hybrid_supported: Optional[bool] = None
        logger.info("VideoClipSearchEngine ready")

    # ------------------------------------------------------------------ status

    def check_connection(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception as exc:  # noqa: BLE001
            logger.error("Redis ping failed: %s", exc)
            return False

    def index_exists(self) -> bool:
        try:
            return self.index.exists()
        except Exception:  # noqa: BLE001
            return False

    def index_info(self) -> Dict[str, Any]:
        try:
            info = self.index.info()
            return {
                "name": info.get("index_name", INDEX_NAME),
                "num_docs": int(info.get("num_docs", 0)),
                "indexing": info.get("indexing", 0),
                "hybrid_backend": self.hybrid_backend_name(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def hybrid_backend_name(self) -> str:
        if self._ft_hybrid_supported is None:
            return "unknown (no search run yet)"
        return "FT.HYBRID" if self._ft_hybrid_supported else "FT.AGGREGATE fallback"

    def genres(self) -> List[str]:
        """Distinct genre tags, grouped server-side with FT.AGGREGATE."""
        try:
            from redis.commands.search.aggregation import AggregateRequest
            from redis.commands.search import reducers

            req = AggregateRequest("*").group_by("@genre", reducers.count().alias("count"))
            res = self.client.ft(INDEX_NAME).aggregate(req)
            rows = getattr(res, "rows", [])
            genres = []
            for row in rows:
                row = [v.decode() if isinstance(v, bytes) else v for v in row]
                mapping = dict(zip(row[::2], row[1::2]))
                if mapping.get("genre"):
                    genres.append(mapping["genre"])
            return sorted(genres)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list genres: %s", exc)
            return []

    # ------------------------------------------------------------------ search

    def hybrid_search(
        self,
        query: str,
        num_results: int = DEFAULT_NUM_RESULTS,
        genre: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        fusion: str = DEFAULT_FUSION,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    ) -> Dict[str, Any]:
        """
        Embed the description and run a hybrid text + vector query in Redis.

        fusion:
          "RRF"    - reciprocal rank fusion of the BM25 and KNN rankings
          "LINEAR" - weighted sum: vector_weight * vsim + (1 - vector_weight) * text
        """
        fusion = fusion.upper()
        if fusion not in ("RRF", "LINEAR"):
            raise ValueError("fusion must be 'RRF' or 'LINEAR'")

        logger.info(
            "Hybrid search: query=%r k=%d genre=%s years=%s-%s fusion=%s w=%.2f",
            query, num_results, genre, year_from, year_to, fusion, vector_weight,
        )
        embedding = self.vectorizer.embed(query)
        filters = self._build_filter(genre, year_from, year_to)

        if self._ft_hybrid_supported is not False:
            try:
                hits = self._ft_hybrid(query, embedding, num_results, filters, fusion, vector_weight)
                self._ft_hybrid_supported = True
                return self._format(hits, "FT.HYBRID", fusion)
            except ResponseError as exc:
                if not _is_unsupported_command(exc):
                    raise
                logger.warning("FT.HYBRID not available (%s); using FT.AGGREGATE fallback", exc)
                self._ft_hybrid_supported = False
            except (ImportError, AttributeError) as exc:
                # redis-py < 7.1 has no hybrid_search()
                logger.warning("HybridQuery unsupported by client (%s); using fallback", exc)
                self._ft_hybrid_supported = False

        hits = self._aggregate_hybrid(query, embedding, num_results, filters, vector_weight)
        return self._format(hits, "FT.AGGREGATE fallback", "LINEAR")

    def _ft_hybrid(
        self,
        query: str,
        embedding: List[float],
        num_results: int,
        filters: Optional[FilterExpression],
        fusion: str,
        vector_weight: float,
    ) -> List[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {}
        if fusion == "LINEAR":
            # RedisVL's linear_alpha weights the TEXT score; beta = 1 - alpha goes to vsim.
            kwargs["linear_alpha"] = max(0.001, min(0.999, 1.0 - vector_weight))
        hq = HybridQuery(
            text=query,
            text_field_name=TEXT_FIELD,
            text_scorer="BM25STD",
            vector=embedding,
            vector_field_name=VECTOR_FIELD,
            vector_search_method="KNN",
            combination_method=fusion,
            yield_text_score_as="text_score",
            yield_vsim_score_as="vector_similarity",
            yield_combined_score_as="hybrid_score",
            filter_expression=filters,
            num_results=num_results,
            return_fields=RETURN_FIELDS,
            stopwords=STOPWORDS,
            **kwargs,
        )
        return self.index.query(hq)

    def _aggregate_hybrid(
        self,
        query: str,
        embedding: List[float],
        num_results: int,
        filters: Optional[FilterExpression],
        vector_weight: float,
    ) -> List[Dict[str, Any]]:
        aq = AggregateHybridQuery(
            text=query,
            text_field_name=TEXT_FIELD,
            text_scorer="BM25STD",
            vector=embedding,
            vector_field_name=VECTOR_FIELD,
            alpha=vector_weight,  # hybrid_score = alpha*vsim + (1-alpha)*text
            filter_expression=filters,
            num_results=num_results,
            return_fields=RETURN_FIELDS,
            stopwords=STOPWORDS,
        )
        return self.index.query(aq)

    @staticmethod
    def _build_filter(
        genre: Optional[str], year_from: Optional[int], year_to: Optional[int]
    ) -> Optional[FilterExpression]:
        expr: Optional[FilterExpression] = None
        if genre and genre.lower() != "all":
            expr = Tag("genre") == genre.lower()
        if year_from is not None:
            expr = _and(expr, Num("year") >= year_from)
        if year_to is not None:
            expr = _and(expr, Num("year") <= year_to)
        return expr

    @staticmethod
    def _format(hits: List[Dict[str, Any]], backend: str, fusion: str) -> Dict[str, Any]:
        results = []
        for rank, hit in enumerate(hits, start=1):
            item: Dict[str, Any] = {
                "rank": rank,
                "id": _strip_prefix(hit.get("id", "")),
                "title": hit.get("title", "Untitled clip"),
                "movie": hit.get("movie", ""),
                "year": _to_int(hit.get("year")),
                "genre": hit.get("genre", ""),
                "director": hit.get("director", ""),
                "duration_seconds": _to_int(hit.get("duration_seconds")),
                "description": hit.get("description", ""),
                "video_url": hit.get("video_url") or None,
                "thumbnail_url": hit.get("thumbnail_url") or None,
                "hybrid_score": _to_float(hit.get("hybrid_score")),
                "text_score": _to_float(hit.get("text_score")),
                "vector_similarity": _to_float(hit.get("vector_similarity")),
            }
            results.append(item)
        return {"results": results, "backend": backend, "fusion": fusion}

    # ------------------------------------------------------------------ ingest

    def ingest_clips(self, path: Optional[Path] = None) -> int:
        """
        Embed every clip description and load the clips into Redis as hashes,
        then (re)create the search index. Returns the number of clips loaded.
        """
        path = Path(path or CLIPS_FILE)
        clips = json.loads(path.read_text())
        if not isinstance(clips, list) or not clips:
            raise ValueError(f"{path} must contain a non-empty JSON array of clips")

        texts = [clip_search_text(c) for c in clips]
        logger.info("Embedding %d clip descriptions with %s", len(texts), EMBEDDING_MODEL)
        embeddings = self.vectorizer.embed_many(texts, batch_size=32, as_buffer=True, skip_cache=True)

        records = []
        for clip, text, emb in zip(clips, texts, embeddings):
            records.append(
                {
                    "id": str(clip["id"]),
                    "title": clip["title"],
                    "movie": clip["movie"],
                    "year": int(clip["year"]),
                    "genre": str(clip["genre"]).lower(),
                    "director": clip.get("director", ""),
                    "duration_seconds": int(clip.get("duration_seconds", 0)),
                    "description": clip["description"],
                    "video_url": clip.get("video_url", ""),
                    "thumbnail_url": clip.get("thumbnail_url", ""),
                    TEXT_FIELD: text,
                    VECTOR_FIELD: emb,
                }
            )

        logger.info("Creating index %s (prefix %s)", INDEX_NAME, KEY_PREFIX)
        self.index.create(overwrite=True, drop=False)
        # load() writes the hashes in pipelined batches
        keys = self.index.load(records, id_field="id", batch_size=50)
        logger.info("Loaded %d clips into Redis", len(keys))
        return len(keys)

    def clear(self) -> int:
        """Drop the index and delete every clip:* hash. Returns keys deleted."""
        if self.index.exists():
            self.index.delete(drop=False)
        deleted = 0
        batch: List[bytes] = []
        for key in self.client.scan_iter(match=f"{KEY_PREFIX}*", count=200):
            batch.append(key)
            if len(batch) >= 200:
                deleted += self.client.delete(*batch)
                batch = []
        if batch:
            deleted += self.client.delete(*batch)
        logger.info("Cleared index and %d clip keys", deleted)
        return deleted


# ---------------------------------------------------------------------- helpers

def _and(expr: Optional[FilterExpression], new: FilterExpression) -> FilterExpression:
    return new if expr is None else expr & new


def _is_unsupported_command(exc: ResponseError) -> bool:
    msg = str(exc).lower()
    return "unknown command" in msg or "ft.hybrid" in msg or "unknown subcommand" in msg


def _strip_prefix(key: Any) -> str:
    key = key.decode() if isinstance(key, bytes) else str(key)
    return key[len(KEY_PREFIX):] if key.startswith(KEY_PREFIX) else key


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return round(float(value), 4) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _redact(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


# Process-wide singleton
_engine: Optional[VideoClipSearchEngine] = None


def get_search_engine() -> VideoClipSearchEngine:
    global _engine
    if _engine is None:
        _engine = VideoClipSearchEngine()
    return _engine
